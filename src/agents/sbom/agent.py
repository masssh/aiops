"""SBOM analysis agent.

This agent wraps a LangGraph ReAct agent equipped with cdxgen-backed tools for
generating and analysing Software Bill of Materials (SBOM) for a repository.

Example::

    from src.agents.sbom.agent import SBOMAgent

    agent = SBOMAgent(project_path="./workspace/repos/my-project")
    response = agent.run("Generate the SBOM and list all components")
    print(response)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from src.agents.base import BaseAgent
from src.agents.sbom.tools import create_sbom_tools
from src.core.llm import create_llm
from src.core.logging import get_logger

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = get_logger(__name__)

_SYSTEM_PROMPT_BASE = """\
You are an SBOM (Software Bill of Materials) analysis assistant.
You specialise in generating and analysing CycloneDX SBOMs for software projects
using the cdxgen tool (https://cyclonedx.github.io/cdxgen).

You have access to the following tools:
- generate_sbom: Run cdxgen against the project and write the SBOM to a JSON file.
- get_sbom_metadata: Read top-level metadata from the SBOM (project name, version, timestamp, tool).
- list_components: List all dependency components recorded in the SBOM.
- search_component: Search for a specific component by name within the SBOM.

Guidelines:
- Always call generate_sbom first if no SBOM file exists yet.
- After generation, use get_sbom_metadata to confirm the SBOM is valid before analysis.
- When asked about a specific dependency, use search_component rather than listing everything.
- When listing components on a large project, use the limit parameter to avoid overwhelming output.
- All operations run against the project directory: {project_path}
"""


def _build_system_prompt(project_path: str) -> str:
    return _SYSTEM_PROMPT_BASE.format(project_path=project_path)


class SBOMAgent(BaseAgent):
    """Agent specialised for SBOM generation and analysis via cdxgen."""

    name: str = "sbom"
    description: str = "Generate and analyse Software Bill of Materials (SBOM) for a repository using cdxgen."

    def __init__(
        self,
        *,
        project_path: str,
        verbose: bool = False,
        session_id: str | None = None,
    ) -> None:
        super().__init__(verbose=verbose, session_id=session_id)
        self.project_path = project_path

    def _build_graph(self) -> "CompiledStateGraph":
        """Build a LangGraph ReAct agent with SBOM tools."""
        llm = create_llm(verbose=self.verbose)
        sbom_tools = create_sbom_tools(self.project_path)
        llm_with_tools = llm.bind_tools(sbom_tools)

        tool_node = ToolNode(sbom_tools)

        # ----------------------------------------------------------------
        # Nodes
        # ----------------------------------------------------------------

        system_prompt = _build_system_prompt(self.project_path)

        def call_model(state: MessagesState) -> dict:  # type: ignore[type-arg]
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
                logger.debug("Routing to tools: {}", [tc["name"] for tc in last.tool_calls])
                return "tools"
            return END

        # ----------------------------------------------------------------
        # Graph definition
        # ----------------------------------------------------------------

        graph = StateGraph(MessagesState)
        graph.add_node("sbom_agent", call_model)
        graph.add_node("tools", tool_node)

        graph.add_edge(START, "sbom_agent")
        graph.add_conditional_edges("sbom_agent", should_continue, {"tools": "tools", END: END})
        graph.add_edge("tools", "sbom_agent")

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

    run_agent_cli(SBOMAgent, add_arguments=_add_arguments, build_kwargs=_build_kwargs)
