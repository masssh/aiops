"""SCIP code intelligence agent.

Generates SCIP indexes from source code, stores them in Neo4j, and
enables graph-based code analysis including community / cluster detection.

Workflow
========
1. ``generate_scip_index``    — run the language-appropriate SCIP indexer
2. ``load_scip_to_neo4j``     — parse ``.scip`` binary and populate Neo4j
3. ``find_graph_communities``  — Louvain community detection on symbol graph
4. ``get_community_symbols``   — inspect a specific community
5. ``run_cypher_query``        — ad-hoc Cypher exploration

Prerequisites
=============
- A SCIP indexer installed for the target language:
  - Python:     ``pip install scip-python``
  - TypeScript: ``npm install -g @sourcegraph/scip-typescript``
  - Java:       ``scip-java`` CLI or Gradle plugin
- Neo4j running and accessible (add to ``docker-compose.yml``, see docs)
- ``NEO4J_URI``, ``NEO4J_USERNAME``, ``NEO4J_PASSWORD`` set in ``.env``

Example::

    from src.agents.scip.agent import ScipAgent

    agent = ScipAgent(project_path="./workspace/repos/my-project")
    result = agent.run("Index this project and find code communities")
    print(result)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from src.agents.base import BaseAgent
from src.agents.scip.tools import create_scip_tools
from src.core.llm import create_llm
from src.core.logging import get_logger

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = get_logger(__name__)

_SYSTEM_PROMPT_TEMPLATE = """\
You are a code intelligence analyst specialised in SCIP-based source code indexing
and graph-database analysis.

You have access to the following tools:
- generate_scip_index:       Run the SCIP indexer for the project and produce index.scip.
- load_scip_to_neo4j:        Parse index.scip and store all symbols, relationships, and
                             method-level CALLS edges in Neo4j.
- find_graph_communities:    Apply Louvain community detection to the method call graph.
                             Noise callables (toString / __init__ / constructor etc.) are
                             excluded before clustering. Writes community_id to Symbol nodes.
- get_community_symbols:     List the symbols in a specific community.
- extract_graph_entrypoints: Identify root callables (in_degree=0 in the call graph) —
                             methods that are not called by any other code in the repo and
                             must therefore be triggered externally. Returns a flat list
                             with file path, out_degree, and community_id for each root
                             callable. Use the file path and method name to interpret the
                             semantic role (HTTP handler, CLI entry point, scheduled job,
                             AI tool, etc.).
- run_cypher_query:          Execute a read-only Cypher query against the Neo4j graph.

Typical workflow:
1. Call generate_scip_index (no arguments) to index the project.
2. Call load_scip_to_neo4j (no arguments) to populate Neo4j and build the call graph.
3. Call find_graph_communities to cluster methods into logical modules.
4. Call extract_graph_entrypoints to identify where execution enters the codebase.
5. Call get_community_symbols for communities of interest.
6. Use run_cypher_query for deeper graph exploration.

Guidelines:
- Do NOT call generate_scip_index if the user says the index already exists.
- Do NOT pass explicit output paths unless the user requests a custom location.
- When interpreting entrypoints, look at the file path and method name together:
  files named *Controller, *Resource, *Handler suggest HTTP endpoints;
  *Application with a main() suggests a lifecycle entry; *Tools or *Service may
  indicate AI tool registrations or service interfaces. Adapt to the language and
  framework of the project.
- After entrypoint extraction, summarise the public API surface of the codebase.
- All operations run against: {project_path}
"""


class ScipAgent(BaseAgent):
    """SCIP code intelligence agent combining SCIP indexing and Neo4j graph analysis.

    Indexes a repository using language-specific SCIP indexers, stores the
    resulting symbol graph in Neo4j, and applies community-detection algorithms
    to identify logical code clusters.

    Args:
        project_path: Path to the repository directory to analyse.
        verbose:      Enable verbose LangGraph logging.
        session_id:   Optional session ID for Langfuse tracing.

    Example::

        agent = ScipAgent(project_path="./workspace/repos/my-project")
        result = agent.run("Index this project and detect code communities")
    """

    name: str = "scip"
    description: str = (
        "Generate SCIP code-intelligence indexes, store them in Neo4j, "
        "and detect logical code communities using graph analysis."
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
            "ScipAgent initialised: project_path={} repo_name={}",
            self.project_path,
            self.repo_name,
        )

    def _build_graph(self) -> "CompiledStateGraph":
        """Build the ReAct graph for SCIP indexing and graph analysis."""
        tools = create_scip_tools(self.project_path, self.repo_name)
        llm = create_llm(verbose=self.verbose)
        llm_with_tools = llm.bind_tools(tools)
        tool_node = ToolNode(tools)

        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(project_path=self.project_path)

        def call_model(state: MessagesState) -> dict[str, Any]:
            messages = state["messages"]
            if not any(isinstance(m, SystemMessage) for m in messages):
                messages = [SystemMessage(content=system_prompt)] + messages
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
        graph.add_node("scip_agent", call_model)
        graph.add_node("tools", tool_node)

        graph.add_edge(START, "scip_agent")
        graph.add_conditional_edges(
            "scip_agent", should_continue, {"tools": "tools", END: END}
        )
        graph.add_edge("tools", "scip_agent")

        return graph.compile()


if __name__ == "__main__":
    from src.agents.cli import run_agent_cli

    def _add_arguments(parser: Any) -> None:  # type: ignore[override]
        parser.add_argument(
            "--project-path",
            required=True,
            metavar="PATH",
            help="Path to the repository directory to index.",
        )

    def _build_kwargs(args: Any) -> dict[str, Any]:
        return {"project_path": args.project_path}

    run_agent_cli(ScipAgent, add_arguments=_add_arguments, build_kwargs=_build_kwargs)
