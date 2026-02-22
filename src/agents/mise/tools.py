"""mise tools for use with the MiseAgent.

Each tool is decorated with ``@tool`` so it can be bound directly to a
LangChain/LangGraph ReAct agent.

mise operations are delegated to the ``mise`` CLI, which must be installed.
See https://mise.jdx.dev for installation instructions.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.tools import tool

from src.core.logging import get_logger
from src.core.process import run_command

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def search_tool(
    query: Annotated[str, "Tool name or keyword to search for, e.g. 'node', 'python', 'terraform'"],
) -> str:
    """Search for available tools in the mise registry using ``mise search``.

    Returns a list of matching tool names that can be installed via mise.
    """
    logger.debug("search_tool: query={!r}", query)
    output = run_command("mise", "search", query)
    return output.strip() if output.strip() else f"No tools found matching '{query}'."


@tool
def list_remote_versions(
    tool_name: Annotated[str, "Tool name to list remote versions for, e.g. 'node', 'python'"],
    filter_prefix: Annotated[str, "Optional version prefix to filter results, e.g. '20', '3.11'"] = "",
) -> str:
    """List available remote versions for a tool using ``mise ls-remote``.

    Returns the available versions that can be installed. Optionally filter
    by a version prefix (e.g. '20' to show only Node.js 20.x releases).
    """
    logger.debug("list_remote_versions: tool={!r} filter={!r}", tool_name, filter_prefix)
    args = ["ls-remote", tool_name]
    if filter_prefix:
        args.append(filter_prefix)
    output = run_command("mise", *args)
    return output.strip() if output.strip() else f"No remote versions found for '{tool_name}'."


@tool
def trust_config(
    project_dir: Annotated[str, "Path to the project directory whose mise.toml should be trusted"] = ".",
) -> str:
    """Trust the mise configuration file in the given directory using ``mise trust``.

    mise requires explicit trust before executing tasks or applying tool versions
    from a project's mise.toml. Run this once per project to avoid permission errors.
    """
    logger.debug("trust_config: project_dir={!r}", project_dir)
    output = run_command("mise", "trust", cwd=project_dir)
    return output.strip() if output.strip() else f"Trusted mise config in '{project_dir}'."


@tool
def use_tool(
    tool_name: Annotated[str, "Tool name to install and activate, e.g. 'node', 'python'"],
    version: Annotated[str, "Version to use, e.g. '20', '3.11', 'latest'"] = "latest",
    project_dir: Annotated[str, "Project directory to configure (writes to mise.toml)"] = ".",
) -> str:
    """Install a tool at the specified version and add it to the project mise config.

    Runs ``mise use --path <project_dir> <tool>@<version>``, which installs the
    tool if needed and writes the version pin to mise.toml in the given directory.
    """
    logger.debug("use_tool: tool={!r} version={!r} dir={!r}", tool_name, version, project_dir)
    tool_spec = f"{tool_name}@{version}"
    output = run_command("mise", "use", "--path", ".", tool_spec, cwd=project_dir)
    return f"Configured {tool_spec} in '{project_dir}'.\n{output}".strip()


def create_mise_tools(project_path: str) -> list:
    """Create mise tools pinned to *project_path*.

    ``trust_config`` and ``use_tool`` are created without a ``project_dir``
    parameter so the LLM always operates in the configured project directory.

    Args:
        project_path: Path to the project directory to operate in.

    Returns:
        List of LangChain tools ready to be bound to an agent.
    """

    @tool
    def _search_tool(
        query: Annotated[str, "Tool name or keyword to search for, e.g. 'node', 'python', 'terraform'"],
    ) -> str:
        """Search for available tools in the mise registry using ``mise search``.

        Returns a list of matching tool names that can be installed via mise.
        """
        logger.debug("search_tool: query={!r}", query)
        output = run_command("mise", "search", query)
        return output.strip() if output.strip() else f"No tools found matching '{query}'."

    @tool
    def _list_remote_versions(
        tool_name: Annotated[str, "Tool name to list remote versions for, e.g. 'node', 'python'"],
        filter_prefix: Annotated[str, "Optional version prefix to filter results, e.g. '20', '3.11'"] = "",
    ) -> str:
        """List available remote versions for a tool using ``mise ls-remote``.

        Returns the available versions that can be installed. Optionally filter
        by a version prefix (e.g. '20' to show only Node.js 20.x releases).
        """
        logger.debug("list_remote_versions: tool={!r} filter={!r}", tool_name, filter_prefix)
        args = ["ls-remote", tool_name]
        if filter_prefix:
            args.append(filter_prefix)
        output = run_command("mise", *args)
        return output.strip() if output.strip() else f"No remote versions found for '{tool_name}'."

    @tool
    def _trust_config() -> str:
        """Trust the mise configuration file using ``mise trust``.

        Runs in the project directory configured for this agent.
        mise requires explicit trust before executing tasks or applying tool
        versions from a project's mise.toml.
        """
        logger.debug("trust_config: cwd={!r}", project_path)
        output = run_command("mise", "trust", cwd=project_path)
        return output.strip() if output.strip() else f"Trusted mise config in '{project_path}'."

    @tool
    def _use_tool(
        tool_name: Annotated[str, "Tool name to install and activate, e.g. 'node', 'python'"],
        version: Annotated[str, "Version to use, e.g. '20', '3.11', 'latest'"] = "latest",
    ) -> str:
        """Install a tool at the specified version and add it to the project mise config.

        Runs ``mise use --path <project_path> <tool>@<version>`` in the project
        directory, installing the tool if needed and writing the version pin to
        mise.toml.
        """
        logger.debug("use_tool: tool={!r} version={!r} path={!r}", tool_name, version, project_path)
        tool_spec = f"{tool_name}@{version}"
        output = run_command("mise", "use", "--path", ".", tool_spec, cwd=project_path)
        return f"Configured {tool_spec} in '{project_path}'.\n{output}".strip()

    return [_search_tool, _list_remote_versions, _trust_config, _use_tool]
