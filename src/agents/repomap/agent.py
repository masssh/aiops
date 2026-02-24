"""RepoMap agent: repository structure map using Tree-sitter and PageRank.

This agent generates a token-optimised repository map that shows the directory
structure with classes and functions for the most important files, determined
by PageRank on the import dependency graph.  The map is written to
``agent_output/repos/{repo_name}/repomap.txt``.

Example::

    from src.agents.repomap.agent import RepomapAgent

    agent = RepomapAgent(project_path="./workspace/repos/my-project")
    result = agent.run("Map this repository")
    print(result)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from src.agents.base import BaseAgent
from src.agents.repomap.tools import create_repomap_tools
from src.core.llm import create_llm
from src.core.logging import get_logger

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = get_logger(__name__)

_SYSTEM_PROMPT_TEMPLATE = """\
You are a repository structure analyst. Your task is to generate a clear,
token-optimised map of a code repository.

Use the generate_repomap tool to analyse the repository and write a structured
overview to disk.  The map shows the directory tree with the most important files
expanded to display their top-level classes and functions, ranked by PageRank on
the import dependency graph.

Guidelines:
- Call generate_repomap without arguments to map the entire project directory.
- Adjust top_n if the user requests more or fewer expanded files.
- Do NOT pass an explicit output_path unless the user requests a custom location.
- After the tool call, summarise what the map reveals about the codebase structure.
- All operations run against the project directory: {project_path}
"""


class RepomapAgent(BaseAgent):
    """Repository map agent combining Tree-sitter AST parsing and PageRank scoring.

    Generates a token-optimised repository map that shows the directory structure
    with top-level class and function symbols for the highest-ranked Python files,
    where importance is determined by PageRank on the import dependency graph.
    The map is written to ``agent_output/repos/{repo_name}/repomap.txt``.

    Args:
        project_path: Path to the repository directory to analyse.
        verbose:      Enable verbose LangGraph logging.
        session_id:   Optional session ID for Langfuse tracing.

    Example::

        agent = RepomapAgent(project_path="./workspace/repos/my-project")
        result = agent.run("Map this repository")
    """

    name: str = "repomap"
    description: str = (
        "Generate a token-optimised repository map combining Tree-sitter AST "
        "parsing and PageRank-based importance scoring."
    )

    def __init__(
        self,
        *,
        project_path: str,
        verbose: bool = False,
        session_id: str | None = None,
    ) -> None:
        super().__init__(verbose=verbose, session_id=session_id)
        self.project_path = project_path
        self.repo_name: str = Path(project_path).name
        logger.debug(
            "RepomapAgent initialised: project_path={} repo_name={}",
            self.project_path,
            self.repo_name,
        )

    def _build_graph(self) -> "CompiledStateGraph":
        """Build the ReAct graph for repository mapping.

        Returns:
            Compiled LangGraph ``StateGraph`` with ``repomap_agent`` and
            ``tools`` nodes wired in a standard ReAct loop.
        """
        tools = create_repomap_tools(self.project_path)
        llm = create_llm(verbose=self.verbose)
        llm_with_tools = llm.bind_tools(tools)

        tool_node = ToolNode(tools)
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(project_path=self.project_path)

        # ----------------------------------------------------------------
        # Nodes
        # ----------------------------------------------------------------

        def call_model(state: MessagesState) -> dict[str, Any]:
            messages = state["messages"]
            if not any(isinstance(m, SystemMessage) for m in messages):
                messages = [SystemMessage(content=system_prompt)] + messages
            logger.debug("Calling LLM with {} messages", len(messages))
            response = llm_with_tools.invoke(messages)
            return {"messages": [response]}

        def should_continue(state: MessagesState) -> str:
            """Route to tool execution or end depending on last message."""
            last = state["messages"][-1]
            if hasattr(last, "tool_calls") and last.tool_calls:
                logger.debug(
                    "Routing to tools: {}", [tc["name"] for tc in last.tool_calls]
                )
                return "tools"
            return END

        # ----------------------------------------------------------------
        # Graph definition
        # ----------------------------------------------------------------

        graph = StateGraph(MessagesState)
        graph.add_node("repomap_agent", call_model)
        graph.add_node("tools", tool_node)

        graph.add_edge(START, "repomap_agent")
        graph.add_conditional_edges(
            "repomap_agent", should_continue, {"tools": "tools", END: END}
        )
        graph.add_edge("tools", "repomap_agent")

        return graph.compile()


if __name__ == "__main__":
    from src.agents.cli import run_agent_cli

    def _add_arguments(parser: Any) -> None:  # type: ignore[override]
        parser.add_argument(
            "--project-path",
            required=True,
            metavar="PATH",
            help="Path to the repository directory to map.",
        )

    def _build_kwargs(args: Any) -> dict[str, Any]:
        return {"project_path": args.project_path}

    run_agent_cli(RepomapAgent, add_arguments=_add_arguments, build_kwargs=_build_kwargs)
