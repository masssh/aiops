"""Shared subprocess execution utility.

Provides ``run_command`` — a thin wrapper around ``subprocess.run`` that:
- Resolves the binary via ``shutil.which``
- Logs the full command and its output at INFO level, prefixed with the
  current agent name (set via ``set_current_agent``)
- Raises ``RuntimeError`` on non-zero exit codes
"""

from __future__ import annotations

import shutil
import subprocess
from contextvars import ContextVar, Token

from src.core.logging import get_logger

logger = get_logger(__name__)

_current_agent: ContextVar[str] = ContextVar("current_agent", default="unknown")


def set_current_agent(name: str) -> Token:
    """Set the active agent name for the current execution context.

    Call this before invoking a graph so that ``run_command`` can include
    the agent name in its log lines.  Use the returned token to restore the
    previous value when the invocation is done::

        token = set_current_agent("mise")
        try:
            graph.invoke(...)
        finally:
            _current_agent.reset(token)
    """
    return _current_agent.set(name)


def run_command(binary: str, *args: str, cwd: str | None = None) -> str:
    """Resolve *binary*, run it with *args*, and return stdout.

    Args:
        binary: Command name (resolved via ``shutil.which``) or absolute path.
        *args:  Arguments forwarded to the command.
        cwd:    Working directory for the subprocess.

    Returns:
        Decoded stdout string.

    Raises:
        RuntimeError: If the binary is not found or the command exits with a
                      non-zero status code.
    """
    path = shutil.which(binary)
    if not path:
        raise RuntimeError(
            f"'{binary}' command not found. Please ensure it is installed and on PATH."
        )
    agent = _current_agent.get()
    cmd = [path, *args]
    logger.info("[{}] $ {} (cwd={})", agent, " ".join(cmd), cwd or ".")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if result.stdout:
        logger.info("[{}] stdout: {}", agent, result.stdout.rstrip())
    if result.stderr:
        logger.info("[{}] stderr: {}", agent, result.stderr.rstrip())
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout
