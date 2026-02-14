import os
from typing import Optional, List
from loguru import logger
from langchain_core.tools import tool, BaseTool
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from src.models.state import OverallState
from src.agents.base_command_agent import BaseCommandAgent
from src.utils.command import run_command

# ============================================================================
# Java Environment Operations
# ============================================================================

def create_gradle_tools(project_path: str) -> List[BaseTool]:
    """
    Create Gradle tools bound to a specific project path.

    Args:
        project_path: Path to the Gradle project (e.g., "workspace/springboot-microservices")

    Returns:
        List of tools configured for the specified project
    """

    @tool
    def detect_required_java_version() -> str:
        """
        Detect the Java version required by the Gradle project.
        Checks build.gradle, gradle.properties, and gradle-wrapper.properties.

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
    def detect_current_java_version() -> str:
        """
        Detect the Java version currently active in the environment.

        Returns:
            String describing the current Java version
        """
        logger.info(f"Detecting current Java version in {project_path}")
        return run_command(["java", "-version"], cwd=project_path)

    @tool
    def setup_mise_java(java_version: str) -> str:
        """
        Set up Java version using mise for the project.

        Args:
            java_version: Java version to use (e.g., "17", "21", "corretto-17")

        Returns:
            String describing the setup result and verification
        """
        logger.info(f"Setting up Java {java_version} using mise in {project_path}")
        # Use mise to set local Java version
        result = run_command(["mise", "use", f"java@{java_version}"], cwd=project_path)
        # Verify the installation
        verify_result = run_command(["mise", "current", "java"], cwd=project_path)
        return f"{result}\n\nVerification:\n{verify_result}"

    @tool
    def ensure_gradlew() -> str:
        """
        Ensure Gradle Wrapper exists in the project. If not, create it.

        Returns:
            String describing the result of ensuring Gradle Wrapper exists
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
    def gradlew_version() -> str:
        """
        Check Gradle version using Gradle Wrapper.

        Returns:
            String describing the Gradle version
        """
        logger.info(f"Checking Gradle version in {project_path}")
        return run_command(["./gradlew", "--version"], cwd=project_path)

    # ============================================================================
    # Task Operations
    # ============================================================================

    @tool
    def gradle_tasks(all_tasks: bool = False, group: Optional[str] = None) -> str:
        """
        List available Gradle tasks.

        Args:
            all_tasks: Show all tasks including hidden ones (default: False)
            group: Filter tasks by group (e.g., "build", "verification")

        Returns:
            String listing all available Gradle tasks
        """
        logger.info(f"Listing Gradle tasks in {project_path}")
        cmd = ["./gradlew", "tasks"]
        if all_tasks:
            cmd.append("--all")
        if group:
            cmd.extend(["--group", group])
        return run_command(cmd, cwd=project_path)

    @tool
    def gradle_run_task(task_name: str, additional_args: str = "") -> str:
        """
        Run a specific Gradle task.

        Args:
            task_name: Task name to execute (e.g., "build", "test", "clean")
            additional_args: Additional arguments to pass to the task as a space-separated string (e.g., "--info --stacktrace")

        Returns:
            String with the output of the task execution
        """
        logger.info(f"Running Gradle task '{task_name}' in {project_path}")
        cmd = ["./gradlew", task_name]
        if additional_args:
            cmd.extend(additional_args.split())
        return run_command(cmd, cwd=project_path)

    # ============================================================================
    # Dependency Operations
    # ============================================================================

    @tool
    def gradle_dependencies(configuration: Optional[str] = None, project_name: Optional[str] = None) -> str:
        """
        Display dependency tree for the project.

        Args:
            configuration: Configuration name to display (e.g., "compileClasspath", "runtimeClasspath")
            project_name: Specific subproject name for multi-project builds (e.g., "user-service", "api-gateway", "auth-service")

        Returns:
            String with the dependency tree
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
    def gradle_dependency_insight(dependency: str, configuration: Optional[str] = None) -> str:
        """
        Get insight into a specific dependency.

        Args:
            dependency: Dependency identifier (e.g., "org.springframework.boot:spring-boot")
            configuration: Configuration name to analyze (e.g., "compileClasspath")

        Returns:
            String with detailed dependency insight
        """
        logger.info(f"Getting dependency insight for '{dependency}' in {project_path}")
        cmd = ["./gradlew", "dependencyInsight", "--dependency", dependency]
        if configuration:
            cmd.extend(["--configuration", configuration])
        return run_command(cmd, cwd=project_path)

    # ============================================================================
    # Project Information
    # ============================================================================

    @tool
    def gradle_projects() -> str:
        """
        List all projects (root and subprojects) in a multi-project build.

        Returns:
            String listing all Gradle projects
        """
        logger.info(f"Listing projects in {project_path}")
        return run_command(["./gradlew", "projects"], cwd=project_path)

    @tool
    def gradle_properties(project_name: Optional[str] = None) -> str:
        """
        Display project properties.

        Args:
            project_name: Specific subproject name for multi-project builds (e.g., "user-service", "api-gateway", "auth-service")

        Returns:
            String with project properties
        """
        logger.info(f"Displaying properties for {project_path}")
        cmd = ["./gradlew"]
        if project_name:
            cmd.append(f":{project_name}:properties")
        else:
            cmd.append("properties")
        return run_command(cmd, cwd=project_path)

    # Return all tools
    return [
        # Java Environment Operations
        detect_required_java_version,
        detect_current_java_version,
        setup_mise_java,
        ensure_gradlew,
        # Gradle Wrapper Operations
        gradlew_version,
        # Task Operations
        gradle_tasks,
        gradle_run_task,
        # Dependency Operations
        gradle_dependencies,
        gradle_dependency_insight,
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
        """Return list of available Gradle tools bound to the project path."""
        return create_gradle_tools(self.workspace_dir)

    def get_system_message(self) -> SystemMessage:
        """Return system message describing agent capabilities."""
        return SystemMessage(content=(
            "You are a Gradle build automation assistant.\n\n"
            f"**Working Directory:** All projects are in {self.workspace_dir}\n\n"
            "**Available Tools:**\n"
            "- Java Environment: detect_required_java_version, detect_current_java_version, setup_mise_java, ensure_gradlew\n"
            "- Gradle Wrapper: gradlew_version\n"
            "- Tasks: gradle_tasks, gradle_run_task\n"
            "- Dependencies: gradle_dependencies, gradle_dependency_insight\n"
            "- Project Info: gradle_projects, gradle_properties\n\n"
            "**Pre-execution Checks (Required):**\n"
            "1. detect_required_java_version → 2. detect_current_java_version → 3. setup_mise_java (if mismatch) → 4. ensure_gradlew\n\n"
            "Only proceed with Gradle operations after completing these checks."
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
