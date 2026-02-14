import os
import logging
from typing import Optional, List
from langchain_core.tools import tool, BaseTool
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from src.models.state import OverallState
from src.agents.base_command_agent import BaseCommandAgent
from src.utils.command import run_command

logger = logging.getLogger(__name__)

# ============================================================================
# Java Environment Operations
# ============================================================================

@tool
def detect_required_java_version(project_path: str) -> str:
    """
    Detect the Java version required by the Gradle project.
    Checks build.gradle, gradle.properties, and gradle-wrapper.properties.

    Args:
        project_path: Path to the Gradle project

    Returns:
        String describing the required Java version or an error message
    """
    logger.info(f"Detecting required Java version for {project_path}")

    import re
    from pathlib import Path

    required_version = None
    source = None

    # Check gradle.properties
    gradle_props_path = Path(project_path) / "gradle.properties"
    if gradle_props_path.exists():
        with open(gradle_props_path, 'r') as f:
            content = f.read()
            # Look for patterns like: javaVersion=17, java.version=17, targetCompatibility=17
            match = re.search(r'(?:java\.?[Vv]ersion|targetCompatibility)\s*=\s*([0-9]+)', content)
            if match:
                required_version = match.group(1)
                source = "gradle.properties"

    # Check build.gradle (Groovy)
    if not required_version:
        build_gradle_path = Path(project_path) / "build.gradle"
        if build_gradle_path.exists():
            with open(build_gradle_path, 'r') as f:
                content = f.read()
                # Look for patterns like: sourceCompatibility = '17', targetCompatibility = JavaVersion.VERSION_17
                match = re.search(r'(?:source|target)Compatibility\s*=\s*["\']?(?:JavaVersion\.VERSION_)?([0-9]+)', content)
                if match:
                    required_version = match.group(1)
                    source = "build.gradle"

    # Check build.gradle.kts (Kotlin)
    if not required_version:
        build_gradle_kts_path = Path(project_path) / "build.gradle.kts"
        if build_gradle_kts_path.exists():
            with open(build_gradle_kts_path, 'r') as f:
                content = f.read()
                match = re.search(r'(?:source|target)Compatibility\s*=\s*JavaVersion\.VERSION_([0-9]+)', content)
                if match:
                    required_version = match.group(1)
                    source = "build.gradle.kts"

    # Check gradle-wrapper.properties for Gradle version, then infer Java requirements
    if not required_version:
        wrapper_props_path = Path(project_path) / "gradle" / "wrapper" / "gradle-wrapper.properties"
        if wrapper_props_path.exists():
            with open(wrapper_props_path, 'r') as f:
                content = f.read()
                match = re.search(r'distributionUrl=.*gradle-([0-9]+\.[0-9]+)', content)
                if match:
                    gradle_version = match.group(1)
                    # Gradle 8.5+ requires Java 17+, Gradle 7.x requires Java 11+
                    major_version = int(gradle_version.split('.')[0])
                    if major_version >= 8:
                        required_version = "17"
                        source = f"gradle-wrapper.properties (Gradle {gradle_version} requires Java 17+)"
                    elif major_version >= 7:
                        required_version = "11"
                        source = f"gradle-wrapper.properties (Gradle {gradle_version} requires Java 11+)"

    if required_version:
        return f"Required Java version: {required_version} (detected from {source})"
    else:
        return "Could not determine required Java version from project configuration. Manual inspection may be needed."

@tool
def detect_current_java_version(project_path: str) -> str:
    """
    Detect the Java version currently active in the environment.

    Args:
        project_path: Path to the Gradle project
    """
    logger.info(f"Detecting current Java version in {project_path}")
    return run_command(["java", "-version"], cwd=project_path)

@tool
def setup_mise_java(project_path: str, java_version: str) -> str:
    """
    Set up Java version using mise for the project.

    Args:
        project_path: Path to the Gradle project
        java_version: Java version to use (e.g., "17", "21", "corretto-17")
    """
    logger.info(f"Setting up Java {java_version} using mise in {project_path}")
    # Use mise to set local Java version
    result = run_command(["mise", "use", f"java@{java_version}"], cwd=project_path)
    # Verify the installation
    verify_result = run_command(["mise", "current", "java"], cwd=project_path)
    return f"{result}\n\nVerification:\n{verify_result}"

@tool
def ensure_gradlew(project_path: str) -> str:
    """
    Ensure Gradle Wrapper exists in the project. If not, create it.

    Args:
        project_path: Path to the Gradle project
    """
    logger.info(f"Ensuring Gradle Wrapper exists in {project_path}")

    gradlew_path = os.path.join(project_path, "gradlew")
    if os.path.exists(gradlew_path):
        return f"Gradle Wrapper already exists at {gradlew_path}"

    # Check if gradle wrapper directory exists
    wrapper_dir = os.path.join(project_path, "gradle", "wrapper")
    if not os.path.exists(wrapper_dir):
        return f"Error: gradle/wrapper directory not found in {project_path}. Cannot create wrapper."

    # Use gradle wrapper task to generate gradlew scripts
    logger.info("Gradle Wrapper not found. Attempting to create it using gradle wrapper task...")

    # Try using system gradle if available
    try:
        result = run_command(["gradle", "wrapper"], cwd=project_path)

        # Verify gradlew was created
        if os.path.exists(gradlew_path):
            # Make it executable
            os.chmod(gradlew_path, 0o755)
            return f"Successfully created Gradle Wrapper:\n{result}"
        else:
            return f"Gradle wrapper task executed but gradlew not found:\n{result}"
    except Exception as e:
        return f"Error creating Gradle Wrapper: {str(e)}\nPlease install gradle or manually create the wrapper."

# ============================================================================
# Gradle Wrapper Operations
# ============================================================================

@tool
def gradlew_version(project_path: str) -> str:
    """
    Check Gradle version using Gradle Wrapper.

    Args:
        project_path: Path to the Gradle project
    """
    logger.info(f"Checking Gradle version in {project_path}")
    return run_command(["./gradlew", "--version"], cwd=project_path)

@tool
def gradlew_wrapper_upgrade(project_path: str, gradle_version: Optional[str] = None) -> str:
    """
    Upgrade Gradle Wrapper to a specific version.

    Args:
        project_path: Path to the Gradle project
        gradle_version: Target Gradle version (e.g., "8.5"). If not specified, upgrades to latest.
    """
    logger.info(f"Upgrading Gradle Wrapper in {project_path}")
    cmd = ["./gradlew", "wrapper"]
    if gradle_version:
        cmd.extend(["--gradle-version", gradle_version])
    return run_command(cmd, cwd=project_path)

# ============================================================================
# Task Operations
# ============================================================================

@tool
def gradle_tasks(project_path: str, all_tasks: bool = False, group: Optional[str] = None) -> str:
    """
    List available Gradle tasks.

    Args:
        project_path: Path to the Gradle project
        all_tasks: Show all tasks including hidden ones (default: False)
        group: Filter tasks by group (e.g., "build", "verification")
    """
    logger.info(f"Listing Gradle tasks in {project_path}")
    cmd = ["./gradlew", "tasks"]
    if all_tasks:
        cmd.append("--all")
    if group:
        cmd.extend(["--group", group])
    return run_command(cmd, cwd=project_path)

@tool
def gradle_run_task(project_path: str, task_name: str, additional_args: str = "") -> str:
    """
    Run a specific Gradle task.

    Args:
        project_path: Path to the Gradle project
        task_name: Task name to execute (e.g., "build", "test", "clean")
        additional_args: Additional arguments to pass to the task as a space-separated string (e.g., "--info --stacktrace")
    """
    logger.info(f"Running Gradle task '{task_name}' in {project_path}")
    cmd = ["./gradlew", task_name]
    if additional_args:
        cmd.extend(additional_args.split())
    return run_command(cmd, cwd=project_path)

# ============================================================================
# Build Operations
# ============================================================================

@tool
def gradle_build(project_path: str, skip_tests: bool = False, parallel: bool = False) -> str:
    """
    Build the Gradle project.

    Args:
        project_path: Path to the Gradle project
        skip_tests: Skip test execution (default: False)
        parallel: Enable parallel execution (default: False)
    """
    logger.info(f"Building Gradle project in {project_path}")
    cmd = ["./gradlew", "build"]
    if skip_tests:
        cmd.append("-x")
        cmd.append("test")
    if parallel:
        cmd.append("--parallel")
    return run_command(cmd, cwd=project_path)

@tool
def gradle_clean(project_path: str) -> str:
    """
    Clean the Gradle project build outputs.

    Args:
        project_path: Path to the Gradle project
    """
    logger.info(f"Cleaning Gradle project in {project_path}")
    return run_command(["./gradlew", "clean"], cwd=project_path)

@tool
def gradle_assemble(project_path: str, parallel: bool = False) -> str:
    """
    Assemble the project outputs without running tests.

    Args:
        project_path: Path to the Gradle project
        parallel: Enable parallel execution (default: False)
    """
    logger.info(f"Assembling Gradle project in {project_path}")
    cmd = ["./gradlew", "assemble"]
    if parallel:
        cmd.append("--parallel")
    return run_command(cmd, cwd=project_path)

# ============================================================================
# Test Operations
# ============================================================================

@tool
def gradle_test(project_path: str, test_filter: Optional[str] = None, parallel: bool = False) -> str:
    """
    Run tests in the Gradle project.

    Args:
        project_path: Path to the Gradle project
        test_filter: Test filter pattern (e.g., "*IntegrationTest")
        parallel: Enable parallel test execution (default: False)
    """
    logger.info(f"Running tests in {project_path}")
    cmd = ["./gradlew", "test"]
    if test_filter:
        cmd.extend(["--tests", test_filter])
    if parallel:
        cmd.append("--parallel")
    return run_command(cmd, cwd=project_path)

@tool
def gradle_check(project_path: str) -> str:
    """
    Run all verification tasks (tests, linting, etc.).

    Args:
        project_path: Path to the Gradle project
    """
    logger.info(f"Running verification tasks in {project_path}")
    return run_command(["./gradlew", "check"], cwd=project_path)

# ============================================================================
# Dependency Operations
# ============================================================================

@tool
def gradle_dependencies(project_path: str, configuration: Optional[str] = None, project_name: Optional[str] = None) -> str:
    """
    Display dependency tree for the project.

    Args:
        project_path: Path to the Gradle project
        configuration: Configuration name to display (e.g., "compileClasspath", "runtimeClasspath")
        project_name: Specific subproject name (for multi-project builds)
    """
    logger.info(f"Displaying dependencies for {project_path}")
    cmd = ["./gradlew"]
    if project_name:
        cmd.append(f":{project_name}:dependencies")
    else:
        cmd.append("dependencies")

    if configuration:
        cmd.extend(["--configuration", configuration])
    return run_command(cmd, cwd=project_path)

@tool
def gradle_dependency_insight(project_path: str, dependency: str, configuration: Optional[str] = None) -> str:
    """
    Get insight into a specific dependency.

    Args:
        project_path: Path to the Gradle project
        dependency: Dependency identifier (e.g., "org.springframework.boot:spring-boot")
        configuration: Configuration name to analyze (e.g., "compileClasspath")
    """
    logger.info(f"Getting dependency insight for '{dependency}' in {project_path}")
    cmd = ["./gradlew", "dependencyInsight", "--dependency", dependency]
    if configuration:
        cmd.extend(["--configuration", configuration])
    return run_command(cmd, cwd=project_path)

@tool
def gradle_build_environment(project_path: str) -> str:
    """
    Display build environment information including Gradle version, JVM details, and OS info.

    Args:
        project_path: Path to the Gradle project
    """
    logger.info(f"Displaying build environment for {project_path}")
    return run_command(["./gradlew", "buildEnvironment"], cwd=project_path)

# ============================================================================
# Project Information
# ============================================================================

@tool
def gradle_projects(project_path: str) -> str:
    """
    List all projects (root and subprojects) in a multi-project build.

    Args:
        project_path: Path to the Gradle project
    """
    logger.info(f"Listing projects in {project_path}")
    return run_command(["./gradlew", "projects"], cwd=project_path)

@tool
def gradle_properties(project_path: str, project_name: Optional[str] = None) -> str:
    """
    Display project properties.

    Args:
        project_path: Path to the Gradle project
        project_name: Specific subproject name (for multi-project builds)
    """
    logger.info(f"Displaying properties for {project_path}")
    cmd = ["./gradlew"]
    if project_name:
        cmd.append(f":{project_name}:properties")
    else:
        cmd.append("properties")
    return run_command(cmd, cwd=project_path)

# ============================================================================
# All Available Tools for the Gradle Agent
# ============================================================================

ALL_GRADLE_TOOLS = [
    # Java Environment Operations
    detect_required_java_version,
    detect_current_java_version,
    setup_mise_java,
    ensure_gradlew,
    # Gradle Wrapper Operations
    gradlew_version,
    gradlew_wrapper_upgrade,
    # Task Operations
    gradle_tasks,
    gradle_run_task,
    # Build Operations
    gradle_build,
    gradle_clean,
    gradle_assemble,
    # Test Operations
    gradle_test,
    gradle_check,
    # Dependency Operations
    gradle_dependencies,
    gradle_dependency_insight,
    gradle_build_environment,
    # Project Information
    gradle_projects,
    gradle_properties,
]

# ============================================================================
# Gradle Agent Implementation
# ============================================================================


class GradleAgent(BaseCommandAgent):
    """LangGraph node that uses an LLM with comprehensive Gradle build tool operations."""

    def get_tools(self) -> List[BaseTool]:
        """Return list of available Gradle tools."""
        return ALL_GRADLE_TOOLS

    def get_system_message(self) -> SystemMessage:
        """Return system message describing agent capabilities."""
        return SystemMessage(content=(
            "You are a comprehensive Gradle build automation assistant with access to the following capabilities:\n\n"
            "**IMPORTANT: Workspace Directory Convention**\n"
            f"- ALL Gradle projects are located in: {self.workspace_dir}\n"
            f"- When working with Gradle projects, use this absolute path format: {self.workspace_dir}/project-name\n"
            "- This is a strict requirement for build and analysis workflows\n\n"
            "**Java Environment Operations:**\n"
            "- Detect required Java version from project (detect_required_java_version)\n"
            "- Detect current active Java version (detect_current_java_version)\n"
            "- Set up Java version using mise (setup_mise_java)\n"
            "- Ensure Gradle Wrapper exists or create it (ensure_gradlew)\n\n"
            "**Build Operations:**\n"
            "- Build projects (gradle_build)\n"
            "- Clean build outputs (gradle_clean)\n"
            "- Assemble artifacts (gradle_assemble)\n\n"
            "**Test Operations:**\n"
            "- Run tests (gradle_test)\n"
            "- Run all verification tasks (gradle_check)\n\n"
            "**Task Management:**\n"
            "- List available tasks (gradle_tasks)\n"
            "- Execute specific tasks (gradle_run_task)\n\n"
            "**Dependency Analysis:**\n"
            "- Display dependency tree (gradle_dependencies)\n"
            "- Get dependency insight (gradle_dependency_insight)\n"
            "- Show build environment (gradle_build_environment)\n\n"
            "**Project Information:**\n"
            "- List all projects (gradle_projects)\n"
            "- Display project properties (gradle_properties)\n\n"
            "**Gradle Wrapper:**\n"
            "- Check Gradle version (gradlew_version)\n"
            "- Upgrade Gradle Wrapper (gradlew_wrapper_upgrade)\n\n"
            "**CRITICAL: Pre-execution Checks (MUST BE PERFORMED FIRST)**\n"
            "Before executing ANY Gradle operations, you MUST perform these checks in order:\n"
            "1. Detect required Java version: Use 'detect_required_java_version' to determine what JDK version the repository needs\n"
            "2. Check current Java version: Use 'detect_current_java_version' to see what JDK version is currently active\n"
            "3. Switch Java version if needed: If the current version doesn't match the required version, use 'setup_mise_java' to switch using mise\n"
            "4. Ensure Gradle Wrapper exists: Use 'ensure_gradlew' to verify or create the Gradle Wrapper (gradlew)\n\n"
            "Only after completing these pre-execution checks should you proceed with the actual Gradle operations.\n\n"
            "Use these tools to accomplish the requested Gradle build tasks efficiently."
        ))

    def get_default_prompt(self) -> str:
        """Return default prompt for Gradle operations."""
        return "Ready to assist with Gradle build operations."


def gradle_agent(state: OverallState, config: Optional[RunnableConfig] = None) -> OverallState:
    """
    LangGraph node that uses an LLM with comprehensive Gradle build tool operations.

    This agent can handle various Gradle operations including:
    - Build, clean, assemble, and test operations
    - Task listing and execution
    - Dependency analysis and insight
    - Project information and properties
    - Gradle Wrapper management

    Can be configured via RunnableConfig:
        config = {
            "configurable": {
                "provider": "ollama",
                "model": "qwen3:8b",
                "prompt": "Your custom instructions...",
                "project_root": "/path/to/project",  # Optional: project root directory
                "max_iterations": 20,  # Optional: override default iteration limit
                "log_dir": "logs",  # Optional: directory for log files
                "verbose": False  # Optional: whether to print out LLM response text
            }
        }
    """
    agent = GradleAgent("gradle_agent", state, config)
    return agent.run()
