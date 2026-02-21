"""Langfuse monitoring integration.

This module provides a factory for ``LangfuseCallbackHandler`` that points
at the self-hosted Langfuse instance configured in ``.env``.

Usage::

    from src.core.monitoring import create_langfuse_handler

    handler = create_langfuse_handler(session_id="session-abc", user_id="user-1")
    # Pass to LangChain calls:
    chain.invoke({"input": "..."}, config={"callbacks": [handler]})
"""

from __future__ import annotations

from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)


def create_langfuse_handler(
    session_id: str | None = None,
    user_id: str | None = None,
    trace_name: str | None = None,
    **kwargs: Any,
) -> Any:
    """Create a ``LangfuseCallbackHandler`` for the self-hosted Langfuse.

    Returns ``None`` if Langfuse is not configured (missing API keys), so
    callers can use ``callbacks = [h for h in [handler] if h]``.

    Args:
        session_id:  Optional session identifier for grouping traces.
        user_id:     Optional user identifier.
        trace_name:  Optional human-readable name for the trace.
        **kwargs:    Additional keyword arguments forwarded to the handler.

    Returns:
        A ``LangfuseCallbackHandler`` instance, or ``None``.
    """
    from src.core.config import settings  # lazy import

    if not settings.langfuse_enabled:
        logger.debug(
            "Langfuse not configured (missing LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY) – "
            "tracing disabled."
        )
        return None

    try:
        from langfuse import Langfuse  # type: ignore[import-untyped]
        from langfuse.langchain import CallbackHandler  # type: ignore[import-untyped]

        # langfuse 3.x: configure the global client, then create the handler
        Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )

        handler = CallbackHandler(**kwargs)
        logger.info(
            "Langfuse tracing enabled – host={}, session={}", settings.langfuse_host, session_id
        )
        return handler
    except ImportError:
        logger.warning(
            "langfuse package not installed. Run: pip install 'langfuse>=3'"
        )
        return None
    except Exception as exc:
        logger.warning("Failed to initialise Langfuse callback handler: {}", exc)
        return None
