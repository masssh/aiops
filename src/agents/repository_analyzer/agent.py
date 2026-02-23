"""Repository analysis agent using Serena MCP.

This agent wraps a LangGraph ReAct agent that uses Serena MCP for
static code analysis — symbol lookup, reference finding, code search,
and structural exploration of a repository.

One instance of this agent is responsible for exactly one repository.

Example::

    from src.agents.repository_analyzer.agent import RepositoryAnalyzerAgent

    agent = RepositoryAnalyzerAgent(project_path="./workspace/repos/my-project")
    response = agent.run("Find all classes that implement the UserRepository interface")
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
from src.core.llm import create_llm
from src.core.logging import extract_content_blocks, get_logger
from src.core.process import _current_agent, set_current_agent

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool
    from langgraph.graph.state import CompiledStateGraph

logger = get_logger(__name__)



# Serena MCP tools that modify files, symbols, memory, or execute shell commands.
# These are excluded so the agent is strictly read-only.
_WRITE_TOOLS: frozenset[str] = frozenset({
    "create_text_file",
    "replace_content",
    "delete_lines",
    "replace_lines",
    "insert_at_line",
    "replace_symbol_body",
    "insert_after_symbol",
    "insert_before_symbol",
    "rename_symbol",
})

_SYSTEM_PROMPT_BASE = """\
You are a static code analysis assistant for the repository at: {project_path}

You use Serena, an LSP-backed code intelligence tool, to explore and analyse code.

You are operating in READ-ONLY mode. You MUST NOT modify any files or symbols.

Guidelines:
- Use available tools to answer questions about code structure, symbols, and dependencies.
- When asked to find a symbol, search broadly first, then narrow down.
- Prefer tool results over assumptions; never guess file paths or symbol names.
- If a tool returns no results, try alternative search terms or patterns.
- Summarise findings concisely and include file paths and line numbers where relevant.
"""


def _build_system_prompt(project_path: str) -> str:
    return _SYSTEM_PROMPT_BASE.format(project_path=project_path)


class RepositoryAnalyzerAgent(BaseAgent):
    """Agent for static code analysis of a single repository using Serena MCP.

    One agent instance maps to one repository. The Serena MCP server is started
    as a subprocess (stdio transport) scoped to ``project_path`` on every ``run()``
    call and torn down cleanly afterward.
    """

    name: str = "repository_analyzer"
    description: str = (
        "Perform static code analysis on a repository using Serena MCP (LSP-backed)."
    )

    def __init__(
        self,
        *,
        project_path: str,
        verbose: bool = False,
        session_id: str | None = None,
    ) -> None:
        super().__init__(verbose=verbose, session_id=session_id)
        self.project_path = Path(project_path).resolve()

    # ------------------------------------------------------------------
    # BaseAgent overrides
    # ------------------------------------------------------------------

    def _build_graph(self) -> "CompiledStateGraph":
        # Graph is built dynamically per-run inside the async MCP session context.
        raise RuntimeError(
            "RepositoryAnalyzerAgent builds its graph dynamically per MCP session; "
            "use run() directly."
        )

    def _run(self, message: str, **kwargs: Any) -> str:
        """Run the agent inside a new event loop to support async MCP session management."""
        return asyncio.run(self._arun(message, **kwargs))

    # ------------------------------------------------------------------
    # Async core
    # ------------------------------------------------------------------

    async def _arun(self, message: str, **kwargs: Any) -> str:
        """Connect to Serena MCP, build the ReAct graph, and invoke it."""
        from langchain_mcp_adapters.client import MultiServerMCPClient  # type: ignore[import-untyped]
        from langchain_mcp_adapters.tools import load_mcp_tools  # type: ignore[import-untyped]

        self._logger.info("Agent '{}' received: {!r}", self.name, message[:120])
        self._logger.debug("Starting Serena MCP server for project: {}", self.project_path)

        serena_config = {
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/oraios/serena",
                "serena",
                "start-mcp-server",
                "--project",
                str(self.project_path),
                "--context",
                "desktop-app",
                "--open-web-dashboard",
                "false",
                "--log-level",
                "WARNING",
            ],
            "transport": "stdio",
        }

        mcp_client = MultiServerMCPClient({"serena": serena_config})

        # Use a single persistent session so the Serena subprocess is started
        # once and reused for every tool call during graph execution.
        async with mcp_client.session("serena") as session:
            all_tools: list[BaseTool] = await load_mcp_tools(session)
            tools = [t for t in all_tools if t.name not in _WRITE_TOOLS]
            self._logger.debug(
                "Loaded {} tools from Serena MCP ({} write tools excluded)",
                len(tools),
                len(all_tools) - len(tools),
            )

            graph = self._build_analysis_graph(tools)
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
        self._logger.info("Agent '{}' replied: {}", self.name, extract_content_blocks(response)[:120])
        self._log_token_usage(result["messages"])
        return response

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_analysis_graph(self, tools: list["BaseTool"]) -> "CompiledStateGraph":
        """Build a ReAct graph bound to the provided Serena MCP tools."""
        llm = create_llm(verbose=self.verbose)
        llm_with_tools = llm.bind_tools(tools)
        tool_node = ToolNode(tools)

        system_prompt = _build_system_prompt(str(self.project_path))

        def call_model(state: MessagesState) -> dict:  # type: ignore[type-arg]
            messages = state["messages"]
            if not any(isinstance(m, SystemMessage) for m in messages):
                messages = [SystemMessage(content=system_prompt)] + messages
            logger.debug("Calling LLM with {} messages", len(messages))
            response = llm_with_tools.invoke(messages)
            return {"messages": [response]}

        def should_continue(state: MessagesState) -> str:
            last = state["messages"][-1]
            if hasattr(last, "tool_calls") and last.tool_calls:
                logger.debug("Routing to tools: {}", [tc["name"] for tc in last.tool_calls])
                return "tools"
            return END

        graph = StateGraph(MessagesState)
        graph.add_node("analyzer_agent", call_model)
        graph.add_node("tools", tool_node)

        graph.add_edge(START, "analyzer_agent")
        graph.add_conditional_edges(
            "analyzer_agent", should_continue, {"tools": "tools", END: END}
        )
        graph.add_edge("tools", "analyzer_agent")

        return graph.compile()


if __name__ == "__main__":
    from src.agents.cli import run_agent_cli

    def _add_arguments(parser):
        parser.add_argument(
            "--project-path",
            required=True,
            metavar="PATH",
            help="Path to the repository directory to analyse.",
        )

    def _build_kwargs(args):
        return {"project_path": args.project_path}

    run_agent_cli(
        RepositoryAnalyzerAgent, add_arguments=_add_arguments, build_kwargs=_build_kwargs
    )
