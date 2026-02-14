"""
Centralized logging configuration for all agents using loguru.

This module provides a common logging setup that reads configuration from
environment variables (.env file) to control log levels for both file and
console outputs.

Environment Variables:
    LOG_LEVEL_FILE: Log level for file output (default: INFO)
    LOG_LEVEL_CONSOLE: Log level for console output (default: INFO)
    LOG_DIR: Directory to store log files (default: <project_root>/logs)
    Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Store logger IDs for cleanup
_logger_ids = {}
# Track if default handler has been removed
_default_handler_removed = False


def get_project_root() -> Path:
    """
    Find the project root directory by looking for pyproject.toml.

    Returns:
        Path to the project root directory
    """
    current_path = Path(__file__).resolve()

    # Traverse up the directory tree to find pyproject.toml
    for parent in [current_path] + list(current_path.parents):
        if (parent / "pyproject.toml").exists():
            return parent

    # Fallback to current working directory if pyproject.toml not found
    return Path.cwd()


def setup_agent_logger(
    agent_name: str,
    log_dir: str | None = None
):
    """
    Set up a dedicated logger for an agent with both file and console output.

    Args:
        agent_name: Name of the agent (used for logger name and log filename)
        log_dir: Directory to store log files (default: reads from LOG_DIR env var or <project_root>/logs)

    Returns:
        Configured logger instance (loguru logger)

    Example:
        >>> logger = setup_agent_logger("github_agent")
        >>> logger.info("Processing repository")
        >>> logger.debug("Detailed debug information")
    """
    # Get log directory from environment variable or use project root default
    if log_dir is None:
        log_dir_env = os.getenv("LOG_DIR")
        if log_dir_env:
            log_dir = log_dir_env
        else:
            # Default to project_root/logs
            project_root = get_project_root()
            log_dir = str(project_root / "logs")

    # Create logs directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Get log levels from environment variables
    file_level_str = os.getenv("LOG_LEVEL_FILE", "INFO").upper()
    console_level_str = os.getenv("LOG_LEVEL_CONSOLE", "INFO").upper()

    # Remove default handler on first setup
    global _default_handler_removed
    if not _default_handler_removed:
        logger.remove()
        _default_handler_removed = True

    # Remove any existing handlers for this agent
    if agent_name in _logger_ids:
        for logger_id in _logger_ids[agent_name]:
            logger.remove(logger_id)
        _logger_ids[agent_name] = []
    else:
        _logger_ids[agent_name] = []

    # File handler with timestamp and detailed format
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_path / f"{agent_name}_{timestamp}.log"

    file_handler_id = logger.add(
        log_file,
        level=file_level_str,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{extra[agent_name]}</cyan> | <level>{message}</level>",
        encoding="utf-8",
        enqueue=True,  # Thread-safe logging
        backtrace=True,  # Better error tracing
        diagnose=True,  # Detailed exception information
        filter=lambda record: record["extra"].get("agent_name") == agent_name
    )
    _logger_ids[agent_name].append(file_handler_id)

    # Console handler with colorized output and simplified format
    console_handler_id = logger.add(
        sys.stdout,
        level=console_level_str,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        colorize=True,
        enqueue=True,
        filter=lambda record: record["extra"].get("agent_name") == agent_name
    )
    _logger_ids[agent_name].append(console_handler_id)

    # Bind agent_name to logger context
    agent_logger = logger.bind(agent_name=agent_name)

    agent_logger.info(f"{agent_name} logger initialized. Log file: {log_file}")
    agent_logger.debug(f"Log levels - File: {file_level_str}, Console: {console_level_str}")

    return agent_logger
