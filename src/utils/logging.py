"""
Centralized logging configuration for all agents.

This module provides a common logging setup that reads configuration from
environment variables (.env file) to control log levels for both file and
console outputs.

Environment Variables:
    LOG_LEVEL_FILE: Log level for file output (default: DEBUG)
    LOG_LEVEL_CONSOLE: Log level for console output (default: INFO)
    Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def setup_agent_logger(
    agent_name: str,
    log_dir: str = "logs"
) -> logging.Logger:
    """
    Set up a dedicated logger for an agent with both file and console output.

    Args:
        agent_name: Name of the agent (used for logger name and log filename)
        log_dir: Directory to store log files (default: "logs")

    Returns:
        Configured logger instance

    Example:
        >>> logger = setup_agent_logger("github_agent")
        >>> logger.info("Processing repository")
        >>> logger.debug("Detailed debug information")
    """
    # Create logs directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Get log levels from environment variables
    file_level_str = os.getenv("LOG_LEVEL_FILE", "DEBUG").upper()
    console_level_str = os.getenv("LOG_LEVEL_CONSOLE", "INFO").upper()

    # Convert string to logging level, with fallback to default if invalid
    file_level = getattr(logging, file_level_str, logging.DEBUG)
    console_level = getattr(logging, console_level_str, logging.INFO)

    # Create logger
    logger = logging.getLogger(agent_name)
    logger.setLevel(min(file_level, console_level))  # Set to the minimum level needed

    # Remove existing handlers to avoid duplicates
    logger.handlers = []

    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )

    # File handler with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_path / f"{agent_name}_{timestamp}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(file_level)
    file_handler.setFormatter(detailed_formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(console_formatter)

    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info(f"{agent_name} logger initialized. Log file: {log_file}")
    logger.debug(f"Log levels - File: {file_level_str}, Console: {console_level_str}")

    return logger
