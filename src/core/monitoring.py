"""Langfuse v3 monitoring integration.

Initialises the global Langfuse client once and exposes helpers used by agents.

Usage::

    from src.core import monitoring

    if monitoring.is_enabled():
        # tracing is active
    handler = monitoring.get_callback_handler()  # None when disabled
"""

from __future__ import annotations

from src.core.logging import get_logger

logger = get_logger(__name__)

# None = not yet determined, True/False = result of _setup()
_enabled: bool | None = None


def _setup() -> bool:
    global _enabled
    if _enabled is not None:
        return _enabled

    from src.core.config import settings

    if not settings.langfuse_enabled:
        logger.debug("Langfuse tracing disabled (no API keys configured).")
        _enabled = False
        return False

    try:
        from langfuse import Langfuse  # type: ignore[import-untyped]

        Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info("Langfuse tracing enabled – host={}", settings.langfuse_host)
        _enabled = True
    except Exception as exc:
        logger.warning("Failed to initialise Langfuse client: {}", exc)
        _enabled = False

    return _enabled


def is_enabled() -> bool:
    """Return True if Langfuse is configured and the client initialised successfully."""
    return _setup()


def get_callback_handler() -> object | None:
    """Return a LangChain ``CallbackHandler``, or ``None`` when Langfuse is disabled."""
    if not _setup():
        return None
    from langfuse.langchain import CallbackHandler  # type: ignore[import-untyped]

    return CallbackHandler()
