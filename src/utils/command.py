"""
Utility module for executing shell commands with logging.

This module provides a common command execution function that automatically
logs the command being executed and its results.
"""

import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def run_command(cmd: list[str], cwd: Optional[str] = None) -> str:
    """
    Execute a shell command and return the output or error message.

    This function automatically logs:
    - The command being executed (INFO level)
    - The working directory if specified (INFO level)
    - The command output on success (INFO level)
    - Error messages on failure (ERROR level)

    Args:
        cmd: Command and arguments as a list (e.g., ["git", "status"])
        cwd: Working directory for command execution (optional)

    Returns:
        Command output as a string, or error message prefixed with "Error: "

    Example:
        >>> result = run_command(["git", "status"], cwd="/path/to/repo")
        >>> if not result.startswith("Error:"):
        ...     print("Success:", result)
    """
    # Log the command being executed
    cmd_str = " ".join(cmd)
    logger.info(f"Executing command: {cmd_str}")
    if cwd:
        logger.info(f"Working directory: {cwd}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, check=True)
        output = result.stdout.strip() if result.stdout.strip() else "Command executed successfully."
        logger.info(f"Command output: {output}")
        return output
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr.strip() else str(e)
        logger.error(f"Command failed: {error_msg}")
        return f"Error: {error_msg}"
