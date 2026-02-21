"""mise tools for use with the MiseAgent.

Each tool is decorated with ``@tool`` so it can be bound directly to a
LangChain/LangGraph ReAct agent.

mise operations are delegated to the ``mise`` CLI, which must be installed.
See https://mise.jdx.dev for installation instructions.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Annotated

from langchain_core.tools import tool

from src.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _require_mise() -> str:
    """Return the absolute path to the ``mise`` binary, or raise."""
    path = shutil.which("mise")
    if not path:
        raise RuntimeError(
            "'mise' command not found. "
            "Install mise from https://mise.jdx.dev or run: "
            "curl https://mise.run | sh"
        )
    return path


def _run_mise(*args: str, cwd: str | None = None) -> str:
    """Run ``mise <args>`` and return stdout as a string.

    Args:
        *args:  Arguments forwarded to ``mise``.
        cwd:    Working directory for the command.

    Returns:
        Decoded stdout string.

    Raises:
        RuntimeError: If the command exits with a non-zero status.
    """
    mise = _require_mise()
    cmd = [mise, *args]
    logger.debug("mise {} (cwd={})", " ".join(args), cwd)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"mise command failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


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
    output = _run_mise("search", query)
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
    output = _run_mise(*args)
    return output.strip() if output.strip() else f"No remote versions found for '{tool_name}'."


@tool
def trust_config(
    project_dir: Annotated[str, "Path to the project directory whose mise.toml should be trusted"],
) -> str:
    """Trust the mise configuration file in the given directory using ``mise trust``.

    mise requires explicit trust before executing tasks or applying tool versions
    from a project's mise.toml. Run this once per project to avoid permission errors.
    """
    logger.debug("trust_config: project_dir={!r}", project_dir)
    output = _run_mise("trust", cwd=project_dir)
    return output.strip() if output.strip() else f"Trusted mise config in '{project_dir}'."


@tool
def use_tool(
    tool_name: Annotated[str, "Tool name to install and activate, e.g. 'node', 'python'"],
    version: Annotated[str, "Version to use, e.g. '20', '3.11', 'latest'"] = "latest",
    project_dir: Annotated[str, "Project directory to configure (writes to mise.toml). Use '.' for current directory"] = ".",
    global_: Annotated[bool, "If True, configure globally (~/.config/mise/config.toml) instead of per-project"] = False,
) -> str:
    """Install a tool at the specified version and add it to the project or global mise config.

    Runs ``mise use [--global] <tool>@<version>``, which installs the tool if
    needed and writes the version pin to mise.toml (or the global config).
    """
    logger.debug("use_tool: tool={!r} version={!r} dir={!r} global={}", tool_name, version, project_dir, global_)
    tool_spec = f"{tool_name}@{version}"
    args = ["use"]
    if global_:
        args.append("--global")
    args.append(tool_spec)
    cwd = None if global_ else project_dir
    output = _run_mise(*args, cwd=cwd)
    scope = "globally" if global_ else f"in '{project_dir}'"
    return f"Configured {tool_spec} {scope}.\n{output}".strip()


# Exported list for easy import in agent.py
MISE_TOOLS = [
    search_tool,
    list_remote_versions,
    trust_config,
    use_tool,
]
