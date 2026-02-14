import os
from typing import Any, Literal
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from dotenv import load_dotenv

load_dotenv()

Provider = Literal["gemini", "openai", "anthropic", "ollama"]

def get_llm(
    provider: Provider = "gemini",
    model: str | None = None,
    temperature: float = 0,
    timeout: float | None = None,
    stop: list[str] | None = None
):
    """
    Initializes and returns an LLM based on the specified provider.

    Args:
        provider: The LLM provider to use (gemini, openai, anthropic, ollama)
        model: The model name. If None, uses provider-specific defaults.
        temperature: Temperature for generation (0-1)
        timeout: Request timeout in seconds (OpenAI, Anthropic only)
        stop: Stop sequences for generation (OpenAI, Anthropic only)

    Returns:
        An initialized LLM instance

    Raises:
        ValueError: If required API key is not found or provider is invalid
    """
    if provider == "gemini":
        if not os.getenv("GOOGLE_API_KEY"):
            raise ValueError("GOOGLE_API_KEY not found in environment variables.")

        return ChatGoogleGenerativeAI(
            model=model or "gemini-flash-latest",
            temperature=temperature
        )

    elif provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY not found in environment variables.")

        openai_kwargs: dict[str, Any] = {
            "model": model or "gpt-4o",
            "temperature": temperature,
        }
        if timeout is not None:
            openai_kwargs["timeout"] = timeout
        if stop is not None:
            openai_kwargs["stop"] = stop

        return ChatOpenAI(**openai_kwargs)

    elif provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise ValueError("ANTHROPIC_API_KEY not found in environment variables.")

        return ChatAnthropic(
            model_name=model or "claude-sonnet-4-5-20250929",
            temperature=temperature,
            timeout=timeout,
            stop=stop
        )

    elif provider == "ollama":
        # Ollama runs locally and doesn't require an API key
        return ChatOllama(
            model=model or "llama3.3",
            temperature=temperature
        )

    else:
        raise ValueError(f"Invalid provider: {provider}. Must be one of: gemini, openai, anthropic, ollama")
