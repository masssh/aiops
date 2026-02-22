"""Loguru-based structured logging configuration.

Usage:
    from src.core.logging import get_logger, setup_logging

    setup_logging()  # call once at startup
    logger = get_logger(__name__)
    logger.info("Hello, world!")
"""

from __future__ import annotations

import json
import logging
import sys
from typing import TYPE_CHECKING, Any

from langchain_core.callbacks import BaseCallbackHandler
from loguru import logger

if TYPE_CHECKING:
    pass


class _InterceptHandler(logging.Handler):
    """Redirect stdlib ``logging`` records to Loguru without truncation."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
    "{level: <8} | "
    "{name}:{function}:{line} - "
    "{message}"
)

_initialized = False


def setup_logging(
    level: str | None = None,
    log_file: str | None = None,
    *,
    force: bool = False,
) -> None:
    """Configure loguru handlers.

    This should be called once at application startup (e.g. in main.py).
    Subsequent calls are no-ops unless *force=True*.

    Args:
        level:    Override the log level (falls back to ``settings.log_level``).
        log_file: Override the log file path (falls back to ``settings.log_file``).
                  Pass an empty string to disable file logging.
        force:    Re-initialise even if already configured.
    """
    global _initialized  # noqa: PLW0603
    if _initialized and not force:
        return

    from src.core.config import settings  # lazy import to avoid circular

    effective_level = (level or settings.log_level).upper()
    effective_file = log_file if log_file is not None else settings.log_file

    # Remove default handler installed by loguru
    logger.remove()

    # Console handler
    logger.add(
        sys.stderr,
        level=effective_level,
        format=_CONSOLE_FORMAT,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # File handler (rotated daily, kept for 14 days)
    if effective_file:
        logger.add(
            effective_file,
            level=effective_level,
            format=_FILE_FORMAT,
            rotation="00:00",        # rotate at midnight
            retention="14 days",
            compression="gz",
            encoding="utf-8",
            backtrace=True,
            diagnose=False,          # avoid leaking secrets to log files
        )

    # Redirect stdlib logging (used by LangChain/LangGraph etc.) to Loguru
    # so all messages pass through a single pipeline without truncation.
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    _initialized = True
    logger.debug("Logging initialised (level={}, file={})", effective_level, effective_file or "disabled")


def get_logger(name: str) -> "logger.__class__":  # type: ignore[valid-type]
    """Return a loguru logger bound with the given module name.

    Example::
        logger = get_logger(__name__)
        logger.info("starting agent")
    """
    return logger.bind(name=name)


class ToolLoggingCallbackHandler(BaseCallbackHandler):
    """LangChain callback that logs every tool invocation at INFO level."""

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "unknown")
        try:
            args: Any = json.loads(input_str)
        except (json.JSONDecodeError, TypeError):
            args = input_str
        get_logger("tools").info("Tool call: {} args={}", tool_name, args)


def enable_debug_for_agent(agent_name: str) -> None:
    """Dynamically lower the log level to DEBUG for a specific agent.

    This is called when DEBUG_AGENT env-var or --debug-agent CLI flag matches
    *agent_name*.  It reconfigures all handlers at DEBUG level so that the
    agent's verbose output is visible.

    Args:
        agent_name: The agent identifier (e.g. ``"github"``).
    """
    setup_logging(level="DEBUG", force=True)
    logger.info("Debug logging enabled for agent '{}'", agent_name)
