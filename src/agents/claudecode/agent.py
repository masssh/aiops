"""Claude Code task delegation agent.

This agent bridges the existing LangGraph/Gemini system with Claude Code,
delegating implementation and analysis tasks to the Claude Code CLI via the
Agent SDK.  The orchestrating LLM (Gemini / OpenAI) decides *what* to delegate
and synthesises the final answer; Claude Code does the heavy lifting on the
local filesystem.

Example::

    from src.agents.claudecode.agent import ClaudeCodeAgent

    agent = ClaudeCodeAgent(cwd="/path/to/project")
    response = agent.run("Add type hints to all functions in src/utils.py")
    print(response)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from src.agents.base import BaseAgent
from src.agents.claudecode.tools import create_claudecode_tools
from src.core.llm import create_llm
from src.core.logging import extract_content_blocks, get_logger
from src.core.process import _current_agent, set_current_agent

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = get_logger(__name__)

_SYSTEM_PROMPT = """\
You are an AI assistant that delegates coding and file-system tasks to Claude Code,
a specialised coding agent with direct access to the local project.

You have one tool available: `delegate_to_claude_code`.  Use it to hand off any task
that involves reading, writing, or analysing files in the project directory.

Guidelines:
- Formulate a clear, self-contained task description before delegating.
- If the user's request requires multiple independent steps, you may call the tool
  several times in sequence and combine the results.
- Summarise the outcome concisely once all delegated tasks are complete.
- If a delegated task fails, report the error and suggest a corrective action.
"""


class ClaudeCodeAgent(BaseAgent):
    """Agent that delegates tasks to Claude Code via the Agent SDK.

    One instance targets one working directory.  Claude Code is invoked as a
    subprocess for each tool call and operates within ``cwd``.
    """

    name: str = "claudecode"
    description: str = (
        "Delegate coding and file-system tasks to Claude Code (Anthropic CLI)."
    )

    def __init__(
        self,
        *,
        cwd: str | None = None,
        allowed_tools: list[str] | None = None,
        permission_mode: str = "default",
        max_turns: int | None = None,
        verbose: bool = False,
        session_id: str | None = None,
    ) -> None:
        super().__init__(verbose=verbose, session_id=session_id)
        self.cwd = str(Path(cwd).resolve()) if cwd else str(Path.cwd())
        self.allowed_tools = allowed_tools
        self.permission_mode = permission_mode
        self.max_turns = max_turns

    # ------------------------------------------------------------------
    # BaseAgent overrides
    # ------------------------------------------------------------------

    def _build_graph(self) -> "CompiledStateGraph":
        # The graph is constructed with the resolved cwd, so this is safe
        # to call once and cache (the default BaseAgent behaviour).
        tools = create_claudecode_tools(
            cwd=self.cwd,
            allowed_tools=self.allowed_tools,
            permission_mode=self.permission_mode,
            max_turns=self.max_turns,
        )
        return self._build_react_graph(tools)

    def _run(self, message: str, **kwargs: Any) -> str:
        """Run the agent inside a new event loop to support async tools."""
        return asyncio.run(self._arun(message, **kwargs))

    # ------------------------------------------------------------------
    # Async core
    # ------------------------------------------------------------------

    async def _arun(self, message: str, **kwargs: Any) -> str:
        """Invoke the compiled graph asynchronously."""
        self._logger.info("Agent '{}' received: {!r}", self.name, message[:120])

        graph = self._get_graph()
        config = self._build_config(**kwargs)

        token = set_current_agent(self.name)
        try:
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=message)]},
                config=config,
            )
        finally:
            _current_agent.reset(token)

        final_message = result["messages"][-1]
        response: str = (
            final_message.content
            if isinstance(final_message.content, str)
            else str(final_message.content)
        )
        self._logger.info(
            "Agent '{}' replied: {}", self.name, extract_content_blocks(response)[:120]
        )
        self._log_token_usage(result["messages"])
        return response

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_react_graph(self, tools: list) -> "CompiledStateGraph":
        """Build a ReAct graph with the Claude Code delegation tool."""
        llm = create_llm(verbose=self.verbose)
        llm_with_tools = llm.bind_tools(tools)
        tool_node = ToolNode(tools)

        def call_model(state: MessagesState) -> dict:  # type: ignore[type-arg]
            messages = state["messages"]
            if not any(isinstance(m, SystemMessage) for m in messages):
                messages = [SystemMessage(content=_SYSTEM_PROMPT)] + messages
            logger.debug("Calling LLM with {} messages", len(messages))
            response = llm_with_tools.invoke(messages)
            return {"messages": [response]}

        def should_continue(state: MessagesState) -> str:
            last = state["messages"][-1]
            if hasattr(last, "tool_calls") and last.tool_calls:
                logger.debug(
                    "Routing to tools: {}", [tc["name"] for tc in last.tool_calls]
                )
                return "tools"
            return END

        graph = StateGraph(MessagesState)
        graph.add_node("claudecode_agent", call_model)
        graph.add_node("tools", tool_node)

        graph.add_edge(START, "claudecode_agent")
        graph.add_conditional_edges(
            "claudecode_agent",
            should_continue,
            {"tools": "tools", END: END},
        )
        graph.add_edge("tools", "claudecode_agent")

        return graph.compile()


if __name__ == "__main__":
    from src.agents.cli import run_agent_cli

    def _add_arguments(parser):
        parser.add_argument(
            "--cwd",
            default=None,
            metavar="PATH",
            help="Working directory for Claude Code (defaults to current directory).",
        )
        parser.add_argument(
            "--permission-mode",
            default="default",
            choices=["default", "acceptEdits", "dontAsk"],
            help="How Claude Code handles permission prompts (default: 'default').",
        )
        parser.add_argument(
            "--max-turns",
            type=int,
            default=None,
            metavar="N",
            help="Maximum Claude Code agent turns per delegation (default: unlimited).",
        )

    def _build_kwargs(args):
        return {
            "cwd": args.cwd,
            "permission_mode": args.permission_mode,
            "max_turns": args.max_turns,
        }

    run_agent_cli(
        ClaudeCodeAgent,
        add_arguments=_add_arguments,
        build_kwargs=_build_kwargs,
    )
