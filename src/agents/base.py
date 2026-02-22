"""Base agent class shared by all domain agents.

Every concrete agent should subclass ``BaseAgent`` and implement:
- ``name``  (class attribute) – unique snake_case identifier, e.g. ``"github"``
- ``description`` (class attribute) – one-line description of the agent's purpose
- ``_build_graph()`` – return a compiled LangGraph ``CompiledGraph``
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any

from langchain_core.messages import HumanMessage

from src.core import monitoring
from src.core.logging import ToolLoggingCallbackHandler, get_logger

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


class BaseAgent(abc.ABC):
    """Abstract base for all agents in this system."""

    #: Unique snake_case agent identifier (override in subclasses)
    name: str = "base"
    #: Human-readable description of what this agent does
    description: str = "Base agent"

    def __init__(self, *, verbose: bool = False, session_id: str | None = None) -> None:
        self.verbose = verbose
        self.session_id = session_id
        self._logger = get_logger(f"agents.{self.name}")
        self._graph: CompiledStateGraph | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, message: str, **kwargs: Any) -> str:
        """Invoke the agent with a natural-language *message* and return its reply."""
        if monitoring.is_enabled():
            return self._run_traced(message, **kwargs)
        return self._run(message, **kwargs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_traced(self, message: str, **kwargs: Any) -> str:
        """Run inside a Langfuse trace, propagating session/user attributes."""
        from langfuse import observe, propagate_attributes  # type: ignore[import-untyped]

        @observe(name=f"agent:{self.name}")
        def _inner() -> str:
            attrs: dict[str, str] = {"user_id": "cli"}
            if self.session_id:
                attrs["session_id"] = self.session_id
            with propagate_attributes(**attrs):
                return self._run(message, **kwargs)

        return _inner()

    def _run(self, message: str, **kwargs: Any) -> str:
        """Core agent execution."""
        self._logger.info("Agent '{}' received: {!r}", self.name, message[:120])

        graph = self._get_graph()
        config = self._build_config(**kwargs)
        result = graph.invoke({"messages": [HumanMessage(content=message)]}, config=config)

        final_message = result["messages"][-1]
        response: str = (
            final_message.content
            if isinstance(final_message.content, str)
            else str(final_message.content)
        )
        self._logger.info("Agent '{}' replied: {!r}", self.name, response[:120])
        return response

    def _get_graph(self) -> "CompiledStateGraph":
        if self._graph is None:
            self._logger.debug("Building LangGraph for agent '{}'", self.name)
            self._graph = self._build_graph()
        return self._graph

    def _build_config(self, **kwargs: Any) -> dict[str, Any]:
        """Assemble the ``config`` dict passed to ``graph.invoke``."""
        callbacks: list[Any] = [ToolLoggingCallbackHandler()]
        if monitoring.is_enabled():
            callbacks.append(monitoring.get_callback_handler())
        config: dict[str, Any] = {"callbacks": callbacks, **kwargs}
        return config

    @abc.abstractmethod
    def _build_graph(self) -> "CompiledStateGraph":
        """Construct and return the compiled LangGraph for this agent."""
