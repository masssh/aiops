"""Shared subprocess execution utility.

Provides ``run_command`` — a thin wrapper around ``subprocess.run`` that:
- Resolves the binary via ``shutil.which``
- Logs the full command and its output at INFO level, prefixed with the
  current agent name (set via ``set_current_agent``)
- Raises ``RuntimeError`` on non-zero exit codes
"""

from __future__ import annotations

import inspect
import os
import shutil
import subprocess
import tempfile
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


def run_command(
    binary: str,
    *args: str,
    cwd: str | None = None,
    env: dict[str, str | None] | None = None,
    stdin_input: str | None = None,
    timeout: int | None = None,
) -> str:
    """Resolve *binary*, run it with *args*, and return stdout.

    Args:
        binary:      Command name (resolved via ``shutil.which``) or absolute path.
        *args:       Arguments forwarded to the command.
        cwd:         Working directory for the subprocess.
        env:         Optional environment overrides. Keys mapped to ``None`` are
                     removed from the inherited environment; other values replace or
                     add entries.
        stdin_input: Optional text to pass to the process via stdin.
        timeout:     Maximum seconds to wait for the process. ``None`` means no
                     limit. Raises ``RuntimeError`` on expiry.

    Returns:
        Decoded stdout string.

    Raises:
        RuntimeError: If the binary is not found, the command exits with a
                      non-zero status code, or the timeout is exceeded.
    """
    path = shutil.which(binary)
    if not path:
        raise RuntimeError(
            f"'{binary}' command not found. Please ensure it is installed and on PATH."
        )
    agent = _current_agent.get()
    caller = inspect.stack()[1].function
    cmd = [path, *args]
    logger.info("[{}][{}] $ {} (cwd={})", agent, caller, " ".join(cmd), cwd or ".")
    proc_env: dict[str, str] | None = None
    if env:
        proc_env = {k: v for k, v in os.environ.items() if k not in env}
        proc_env.update({k: v for k, v in env.items() if v is not None})

    # Use temp files for stdout/stderr so that child processes spawned by the
    # command (e.g. background workers started by `claude --print`) cannot keep
    # the output pipes open and block us indefinitely.  We wait only for the
    # main process to exit, then read the files.
    with (
        tempfile.TemporaryFile(mode="w+", suffix=".stdout") as out_f,
        tempfile.TemporaryFile(mode="w+", suffix=".stderr") as err_f,
    ):
        stdin_data = stdin_input.encode() if stdin_input else None
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE if stdin_data else subprocess.DEVNULL,
            stdout=out_f,
            stderr=err_f,
            cwd=cwd,
            env=proc_env,
        )
        if stdin_data:
            proc.stdin.write(stdin_data)
            proc.stdin.close()
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise RuntimeError(
                f"Command timed out after {timeout}s: {' '.join(cmd)}"
            )

        out_f.seek(0)
        err_f.seek(0)
        stdout = out_f.read()
        stderr = err_f.read()

    if stdout:
        logger.debug("[{}][{}] stdout: {}", agent, caller, stdout.rstrip())
    if stderr:
        logger.debug("[{}][{}] stderr: {}", agent, caller, stderr.rstrip())
    if returncode != 0:
        raise RuntimeError(
            f"Command failed (exit {returncode}): {stderr.strip()}"
        )
    return stdout
