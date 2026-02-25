"""LLM factory – creates a ChatModel for the configured provider (Gemini or OpenAI).

Usage::

    from src.core.llm import create_llm

    llm = create_llm()                        # uses LLM_PROVIDER from .env
    llm = create_llm(model="gpt-4o")          # override model
    llm = create_llm(temperature=0.2)
    llm = create_llm(verbose=True)            # enable LangChain verbose output
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel

from src.core.logging import get_logger

logger = get_logger(__name__)


def create_llm(
    *,
    model: str | None = None,
    temperature: float = 0.0,
    verbose: bool = False,
    **kwargs: Any,
) -> BaseChatModel:
    """Instantiate and return a ChatModel for the active LLM provider.

    The provider is controlled by the ``LLM_PROVIDER`` environment variable
    (default: ``"google"``).  Supported values:

    * ``"google"`` — Google Gemini via ``ChatGoogleGenerativeAI``
    * ``"openai"`` — OpenAI (or compatible) via ``ChatOpenAI``

    Args:
        model:       Model ID.  Defaults to provider-specific default
                     (``GEMINI_MODEL`` or ``OPENAI_MODEL``).
        temperature: Sampling temperature (0.0 = deterministic).
        verbose:     Enable LangChain verbose logging for this model instance.
        **kwargs:    Additional keyword arguments forwarded to the underlying
                     ChatModel class.

    Returns:
        A configured ``BaseChatModel`` instance.

    Raises:
        ValueError: If the required API key for the active provider is not set.
    """
    from src.core.config import settings  # lazy to allow patching in tests

    provider = settings.llm_provider
    effective_model = model or settings.active_model

    logger.debug(
        "Creating LLM: provider={}, model={}, temperature={}, verbose={}",
        provider,
        effective_model,
        temperature,
        verbose,
    )

    if provider == "openai":
        return _create_openai(
            model=effective_model,
            temperature=temperature,
            verbose=verbose,
            **kwargs,
        )

    # Default: Google Gemini
    return _create_gemini(
        model=effective_model,
        temperature=temperature,
        verbose=verbose,
        **kwargs,
    )


def _create_gemini(
    *,
    model: str,
    temperature: float,
    verbose: bool,
    **kwargs: Any,
) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    from src.core.config import settings

    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=settings.google_api_key,
        temperature=temperature,
        verbose=verbose,
        convert_system_message_to_human=True,  # Gemini requires this
        **kwargs,
    )


def _create_openai(
    *,
    model: str,
    temperature: float,
    verbose: bool,
    **kwargs: Any,
) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    from src.core.config import settings

    extra: dict[str, Any] = {}
    if settings.openai_base_url:
        extra["base_url"] = settings.openai_base_url

    return ChatOpenAI(
        model=model,
        api_key=settings.openai_api_key,  # type: ignore[arg-type]
        temperature=temperature,
        verbose=verbose,
        **extra,
        **kwargs,
    )
