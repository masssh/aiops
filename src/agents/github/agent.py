"""GitHub operations agent.

This agent wraps a LangGraph ReAct agent equipped with Git tools for
cloning repositories and checking out branches.

Example::

    from src.agents.github import GitHubAgent

    agent = GitHubAgent()
    response = agent.run("Clone https://github.com/octocat/Hello-World into /tmp/hello")
    print(response)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from src.agents.base import BaseAgent
from src.agents.github.tools import GITHUB_TOOLS
from src.core.llm import create_llm
from src.core.logging import get_logger

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a Git assistant that can clone repositories and checkout branches.
You have access to two tools: clone_repository and checkout_branch.

Guidelines:
- Always prefer using tools over guessing.
- For clone_repository, you need the repository URL and an optional destination path.
- For checkout_branch, you need the local repository path and the branch name.
- If required parameters are missing, ask the user to supply them.
"""


class GitHubAgent(BaseAgent):
    """Agent specialised for GitHub operations."""

    name: str = "github"
    description: str = "Clone Git repositories and checkout branches locally."

    def _build_graph(self) -> "CompiledStateGraph":
        """Build a LangGraph ReAct agent with GitHub tools."""
        llm = create_llm(verbose=self.verbose)
        llm_with_tools = llm.bind_tools(GITHUB_TOOLS)

        tool_node = ToolNode(GITHUB_TOOLS)

        # ----------------------------------------------------------------
        # Nodes
        # ----------------------------------------------------------------

        def call_model(state: MessagesState) -> dict:  # type: ignore[type-arg]
            messages = state["messages"]
            # Prepend system prompt on first call
            if not any(isinstance(m, SystemMessage) for m in messages):
                messages = [SystemMessage(content=_SYSTEM_PROMPT)] + messages
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
        graph.add_node("agent", call_model)
        graph.add_node("tools", tool_node)

        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
        graph.add_edge("tools", "agent")  # tools always return to agent

        return graph.compile()
