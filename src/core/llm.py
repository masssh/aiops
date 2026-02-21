"""LLM factory – creates a Gemini ChatModel with shared defaults.

Usage::

    from src.core.llm import create_llm

    llm = create_llm()               # default Gemini model
    llm = create_llm(model="gemini-2.0-pro", temperature=0.2)
    llm = create_llm(verbose=True)   # enable LangChain verbose output
"""

from __future__ import annotations

from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from src.core.logging import get_logger

logger = get_logger(__name__)


def create_llm(
    *,
    model: str | None = None,
    temperature: float = 0.0,
    verbose: bool = False,
    **kwargs: Any,
) -> ChatGoogleGenerativeAI:
    """Instantiate and return a Gemini ChatModel.

    Args:
        model:       Gemini model ID.  Defaults to ``settings.gemini_model``.
        temperature: Sampling temperature (0.0 = deterministic).
        verbose:     Enable LangChain verbose logging for this model instance.
        **kwargs:    Additional keyword arguments forwarded to
                     ``ChatGoogleGenerativeAI``.

    Returns:
        A configured ``ChatGoogleGenerativeAI`` instance.

    Raises:
        ValueError: If ``GOOGLE_API_KEY`` is not set.
    """
    from src.core.config import settings  # lazy to allow patching in tests

    effective_model = model or settings.gemini_model

    if not settings.google_api_key:
        raise ValueError(
            "GOOGLE_API_KEY is not set. "
            "Copy .env.example to .env and fill in your API key."
        )

    logger.debug("Creating LLM: model={}, temperature={}, verbose={}", effective_model, temperature, verbose)

    return ChatGoogleGenerativeAI(
        model=effective_model,
        google_api_key=settings.google_api_key,
        temperature=temperature,
        verbose=verbose,
        convert_system_message_to_human=True,  # Gemini requires this
        **kwargs,
    )
