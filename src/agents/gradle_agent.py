import os
import logging
from typing import Optional
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from src.models.state import OverallState
from src.utils.llm import get_llm, Provider
from src.utils.logging import setup_agent_logger
from src.utils.command import run_command

logger = logging.getLogger(__name__)

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
def gradle_run_task(project_path: str, task_name: str, args: Optional[list[str]] = None) -> str:
    """
    Run a specific Gradle task.

    Args:
        project_path: Path to the Gradle project
        task_name: Task name to execute (e.g., "build", "test", "clean")
        args: Additional arguments to pass to the task (e.g., ["--info", "--stacktrace"])
    """
    logger.info(f"Running Gradle task '{task_name}' in {project_path}")
    cmd = ["./gradlew", task_name]
    if args:
        cmd.extend(args)
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
                "gradle_agent_prompt": "Your custom instructions...",
                "project_root": "/path/to/project",  # Optional: project root directory
                "max_iterations": 20,  # Optional: override default iteration limit
                "log_dir": "logs",  # Optional: directory for log files
                "verbose": False  # Optional: whether to print out LLM response text
            }
        }
    """
    # Get configuration
    configurable = config.get("configurable", {}) if config else {}
    custom_prompt = configurable.get("gradle_agent_prompt")
    provider: Provider = configurable.get("provider", "ollama")
    model: str | None = configurable.get("model", None)
    project_root: str = configurable.get("project_root", os.getcwd())
    max_iterations: int = configurable.get("max_iterations", 20)
    log_dir: str = configurable.get("log_dir", "logs")
    verbose: bool = configurable.get("verbose", False)

    # Set up dedicated logger for this agent execution
    agent_logger = setup_agent_logger("gradle_agent", log_dir)

    # Calculate workspace directory absolute path
    workspace_dir = os.path.abspath(os.path.join(project_root, "workspace"))

    agent_logger.info("="*80)
    agent_logger.info("Gradle Agent started")
    agent_logger.info(f"Provider: {provider}, Model: {model}")
    agent_logger.info(f"Verbose: {verbose}")
    agent_logger.info(f"Project root: {project_root}")
    agent_logger.info(f"Workspace directory: {workspace_dir}")
    agent_logger.info(f"Max iterations: {max_iterations}")
    agent_logger.info("="*80)

    # Initialize LLM with all Gradle tools
    llm = get_llm(provider=provider, model=model, verbose=verbose)
    llm_with_tools = llm.bind_tools(ALL_GRADLE_TOOLS)

    # System message defining the agent's capabilities
    system_msg = SystemMessage(content=(
        "You are a comprehensive Gradle build automation assistant with access to the following capabilities:\n\n"
        "**IMPORTANT: Workspace Directory Convention**\n"
        f"- ALL Gradle projects are located in: {workspace_dir}\n"
        f"- When working with Gradle projects, use this absolute path format: {workspace_dir}/project-name\n"
        "- This is a strict requirement for build and analysis workflows\n\n"
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
        "Use these tools to accomplish the requested Gradle build tasks efficiently.\n"
        "Always ensure the Gradle Wrapper (./gradlew) exists in the project before executing commands."
    ))

    # Build user prompt
    if custom_prompt:
        # Custom prompt provided by the caller
        user_prompt = custom_prompt
        agent_logger.info(f"Using custom prompt: {custom_prompt[:100]}...")
    else:
        # Default behavior: ready for Gradle operations
        user_prompt = "Ready to assist with Gradle build operations."
        agent_logger.info("Ready for Gradle operations")

    agent_logger.debug(f"Full user prompt:\n{user_prompt}")
    messages = [system_msg, HumanMessage(content=user_prompt)]

    # Tool execution loop
    for iteration in range(max_iterations):
        agent_logger.info(f"\n{'='*80}")
        agent_logger.info(f"Iteration {iteration + 1}/{max_iterations}")
        agent_logger.info(f"{'='*80}")

        # Invoke LLM to decide next action
        agent_logger.debug("Invoking LLM to determine next action...")
        ai_msg = llm_with_tools.invoke(messages)
        messages.append(ai_msg)

        # Log LLM's response content (if any)
        if hasattr(ai_msg, 'content') and ai_msg.content:
            agent_logger.debug(f"LLM response content: {ai_msg.content}")

        if not ai_msg.tool_calls:
            # LLM decided it's done
            agent_logger.info("LLM has completed its task (no more tool calls)")
            if hasattr(ai_msg, 'content') and ai_msg.content:
                agent_logger.info(f"Final message: {ai_msg.content}")
            logger.info(f"Gradle agent completed after {iteration + 1} iterations")
            break

        # Log LLM's decision
        agent_logger.info(f"LLM decided to execute {len(ai_msg.tool_calls)} tool(s):")
        for idx, tool_call in enumerate(ai_msg.tool_calls, 1):
            agent_logger.info(f"  {idx}. {tool_call['name']}")

        # Execute all tool calls from this iteration
        for tool_call in ai_msg.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]

            agent_logger.info(f"\n--- Executing tool: {tool_name} ---")
            agent_logger.debug(f"Tool arguments: {tool_args}")

            # Find and invoke the appropriate tool
            tool_function = None
            for tool in ALL_GRADLE_TOOLS:
                if tool.name == tool_name:
                    tool_function = tool
                    break

            if tool_function:
                try:
                    agent_logger.debug(f"Invoking {tool_name}...")
                    result = tool_function.invoke(tool_args)
                    agent_logger.info(f"Tool execution successful")
                    agent_logger.debug(f"Tool result: {result}")
                except Exception as e:
                    result = f"Error executing {tool_name}: {str(e)}"
                    agent_logger.error(f"Tool execution failed: {str(e)}")
                    logger.error(result)
            else:
                result = f"Error: Tool '{tool_name}' not found in available tools."
                agent_logger.error(result)
                logger.error(result)

            messages.append(ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"]
            ))

    agent_logger.info("\n" + "="*80)
    agent_logger.info("Gradle Agent execution completed")
    agent_logger.info("="*80)

    return state
