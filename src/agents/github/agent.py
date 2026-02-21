"""GitHub operations agent.

This agent wraps a LangGraph ReAct agent equipped with the GitHub tool suite.
It can answer questions about repositories, issues, pull requests, and files.

Example::

    from src.agents.github import GitHubAgent

    agent = GitHubAgent()
    response = agent.run("List open issues in octocat/Hello-World")
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
You are a GitHub expert assistant.
You have access to a set of tools that interact with the GitHub API.
Use them to answer the user's questions accurately and concisely.

Guidelines:
- Always prefer using tools over guessing.
- When listing items, present them as a readable markdown list.
- If an operation would modify data (e.g. create an issue), confirm the key details
  before proceeding unless explicitly told to act immediately.
- If a required parameter like 'owner/repo' is not provided, ask the user to supply it.
"""


class GitHubAgent(BaseAgent):
    """Agent specialised for GitHub operations."""

    name: str = "github"
    description: str = "Interact with GitHub: repos, issues, PRs, and file contents."

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
