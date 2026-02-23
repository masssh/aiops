"""Loguru-based structured logging configuration.

Usage:
    from src.core.logging import get_logger, setup_logging

    setup_logging()  # call once at startup
    logger = get_logger(__name__)
    logger.info("Hello, world!")
"""

from __future__ import annotations

import ast
import json
import logging
import sys
from typing import TYPE_CHECKING, Any
from uuid import UUID

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


# Maximum characters to show for tool output before truncating.
_MAX_OUTPUT_LEN = 500

# Only these scalar types are safe to emit as-is in log lines.
_SAFE_SCALAR_TYPES = (str, int, float, bool, type(None))


def _sanitize_value(value: Any, depth: int = 0) -> tuple[bool, Any]:
    """Recursively decide whether *value* is safe to log.

    Returns ``(keep, sanitized)`` where *keep* is False when the value
    should be dropped entirely.

    Rules:
    - Scalars (str / int / float / bool / None): always keep.
    - list: keep only if every element is a safe scalar; drop the whole
      list otherwise to avoid leaking partially-opaque objects.
    - dict: recurse up to *depth* 2; keep key/value pairs whose value
      passes this check, drop the rest silently.
    - Anything else (class instances, callables, …): drop.
    """
    if isinstance(value, _SAFE_SCALAR_TYPES):
        return True, value
    if depth >= 2:
        return False, None
    if isinstance(value, list):
        if all(isinstance(v, _SAFE_SCALAR_TYPES) for v in value):
            return True, value
        return False, None
    if isinstance(value, dict):
        filtered = {}
        for k, v in value.items():
            keep, sv = _sanitize_value(v, depth + 1)
            if keep:
                filtered[k] = sv
        return (True, filtered) if filtered else (False, None)
    # Class instances, ToolRuntime, AsyncCallbackManager, etc. — drop.
    return False, None


def _filter_tool_args(raw: Any) -> dict[str, Any]:
    """Return a log-safe dict extracted from *raw* tool arguments.

    Accepts whatever came out of ``input_str`` parsing (dict, str, …) and
    produces a flat dict containing only JSON-primitive values.  Complex
    objects injected by LangGraph (ToolRuntime, config, stream_writer, …)
    are silently dropped regardless of their key name.

    When *raw* is a bare scalar (e.g. an MCP tool called with a single
    positional string), it is preserved under the key ``"input"`` rather
    than being discarded.
    """
    if isinstance(raw, dict):
        result = {}
        for key, value in raw.items():
            keep, sv = _sanitize_value(value)
            if keep:
                result[key] = sv
        return result
    if isinstance(raw, _SAFE_SCALAR_TYPES) and raw is not None:
        return {"input": raw}
    return {}


def _try_json_pretty(text: str) -> str:
    """If *text* is a JSON string, return it pretty-printed; otherwise return as-is."""
    try:
        return pjson(json.loads(text))
    except (json.JSONDecodeError, TypeError, ValueError):
        return text


def extract_content_blocks(value: Any) -> str:
    """Extract plain text from a LangChain content-blocks structure.

    Accepts:
    - A string repr of a list (e.g. the return value of ``agent.run()``)
    - An actual list of content blocks ``[{"type": "text", "text": "…"}, …]``
    - A ``ToolMessage``-like object (with ``.content``)
    - A plain string

    Returns the concatenated text from all ``{"type": "text"}`` blocks,
    or the original value stringified when no blocks are found.
    """
    # String that may be a Python list repr (agent.run() returns this format)
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                value = parsed
        except (ValueError, SyntaxError):
            return value

    # Unwrap ToolMessage-like objects
    content = getattr(value, "content", value)

    if isinstance(content, list):
        texts = [
            block["text"]
            for block in content
            if isinstance(block, dict) and block.get("type") == "text" and "text" in block
        ]
        if texts:
            return "\n".join(texts)

    if isinstance(content, str):
        return content

    return str(content)


def _extract_tool_output(output: Any) -> str:
    """Extract human-readable text from a LangChain tool output.

    Handles:
    - ``ToolMessage`` / objects with a ``.content`` attribute
    - Content-blocks lists ``[{"type": "text", "text": "…"}, …]``
    - Plain strings
    - Dicts / lists  (formatted with ``pjson``)
    """
    # Unwrap ToolMessage-like objects
    content = getattr(output, "content", output)

    # Content-blocks format used by Claude / Gemini tool responses
    if isinstance(content, list):
        texts = [
            block["text"]
            for block in content
            if isinstance(block, dict) and block.get("type") == "text" and "text" in block
        ]
        if texts:
            return "\n".join(texts)

    if isinstance(content, str):
        return content

    if isinstance(content, (dict, list)):
        return pjson(content)

    return str(content)


def pjson(obj: Any) -> str:
    """Serialise *obj* to a pretty-printed JSON string suitable for log output.

    Non-serialisable values (class instances, bytes, …) fall back to their
    ``str()`` representation via ``default=str``, so this never raises.

    Example::
        logger.info("kwargs:\\n{}", pjson(kwargs))
    """
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)


def _parse_input_str(input_str: str) -> Any:
    """Parse *input_str* into a Python object with a three-stage fallback.

    1. ``json.loads``      — standard JSON (most common case).
    2. ``ast.literal_eval`` — Python-repr dicts/lists of primitives
                              (used by LangGraph when args include
                              non-JSON-serialisable objects).
    3. Empty dict          — give up silently; never let raw garbage through.
    """
    try:
        return json.loads(input_str)
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        parsed = ast.literal_eval(input_str)
        if isinstance(parsed, (dict, list, str, int, float, bool, type(None))):
            return parsed
    except (ValueError, SyntaxError):
        pass
    return {}


class ToolLoggingCallbackHandler(BaseCallbackHandler):
    """LangChain callback that logs every tool invocation at INFO level."""

    def __init__(self, agent_name: str = "unknown") -> None:
        super().__init__()
        self._agent_name = agent_name

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        **kwargs: Any,
    ) -> None:
        model = (
            serialized.get("kwargs", {}).get("model")
            or serialized.get("kwargs", {}).get("model_name")
            or serialized.get("name", "unknown")
        )
        get_logger("tools").debug("[{}] LLM call: {}", self._agent_name, model)

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "unknown")
        # LangChain v0.2+ passes the actual inputs dict via kwargs["inputs"].
        # Fall back to parsing input_str only when it is absent.
        raw = kwargs.get("inputs")
        if not isinstance(raw, dict):
            raw = _parse_input_str(input_str)
        args = _filter_tool_args(raw)
        get_logger("tools").info(
            "[{}] Tool call: {} | args:\n{}", self._agent_name, tool_name, pjson(args)
        )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        output_str = _try_json_pretty(_extract_tool_output(output))
        if len(output_str) > _MAX_OUTPUT_LEN:
            output_str = output_str[:_MAX_OUTPUT_LEN] + "\n... [truncated]"
        get_logger("tools").info("[{}] Tool result:\n{}", self._agent_name, output_str)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        get_logger("tools").error(
            "[{}] Tool error:\n{}",
            self._agent_name,
            pjson({"error": type(error).__name__, "detail": str(error)}),
        )


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
