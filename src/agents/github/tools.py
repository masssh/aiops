"""GitHub tools for use with the GitHubAgent.

Each tool is decorated with ``@tool`` so it can be bound directly to a
LangChain/LangGraph ReAct agent.

Git operations are delegated to the ``git`` CLI, which must be installed.
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

def _require_git() -> str:
    """Return the absolute path to the ``git`` binary, or raise."""
    path = shutil.which("git")
    if not path:
        raise RuntimeError("'git' command not found. Please install Git.")
    return path


def _run_git(*args: str, cwd: str | None = None) -> str:
    """Run ``git <args>`` and return stdout as a string.

    Args:
        *args:  Arguments forwarded to ``git``.
        cwd:    Working directory for the command.

    Returns:
        Decoded stdout string.

    Raises:
        RuntimeError: If the command exits with a non-zero status.
    """
    git = _require_git()
    cmd = [git, *args]
    logger.debug("git {} (cwd={})", " ".join(args), cwd)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git command failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def clone_repository(
    url: Annotated[str, "Repository URL to clone, e.g. 'https://github.com/owner/repo.git'"],
    destination: Annotated[str, "Local directory path to clone into"] = "",
) -> str:
    """Clone a remote Git repository to a local directory."""
    logger.debug("clone_repository: url={} destination={!r}", url, destination)
    args = ["clone", url]
    if destination:
        args.append(destination)
    output = _run_git(*args)
    target = destination if destination else url.rstrip("/").split("/")[-1].removesuffix(".git")
    return f"Cloned {url} into '{target}'.\n{output}".strip()


@tool
def checkout_branch(
    repo_path: Annotated[str, "Local path to the Git repository"],
    branch: Annotated[str, "Branch name to checkout"],
) -> str:
    """Checkout a branch in a local Git repository."""
    logger.debug("checkout_branch: repo_path={} branch={}", repo_path, branch)
    output = _run_git("checkout", branch, cwd=repo_path)
    return f"Checked out branch '{branch}' in '{repo_path}'.\n{output}".strip()


# Exported list for easy import in agent.py
GITHUB_TOOLS = [
    clone_repository,
    checkout_branch,
]
