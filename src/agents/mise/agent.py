"""mise environment configuration agent.

This agent wraps a LangGraph ReAct agent equipped with mise CLI tools for
searching tools, listing remote versions, trusting configs, and configuring
tool versions in projects.

Example::

    from src.agents.mise import MiseAgent

    agent = MiseAgent()
    response = agent.run("Search for available Node.js versions and use 20 in this project")
    print(response)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from src.agents.base import BaseAgent
from src.agents.mise.tools import MISE_TOOLS
from src.core.llm import create_llm
from src.core.logging import get_logger

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a mise environment configuration assistant.
mise (https://mise.jdx.dev) is a polyglot tool version manager that manages
runtime versions (Node.js, Python, Ruby, Go, etc.) on a per-project basis.

You have access to the following tools:
- search_tool: Search the mise registry for available tools by name or keyword.
- list_remote_versions: List installable versions for a specific tool.
- trust_config: Trust a project's mise.toml so mise can apply its settings.
- use_tool: Install a tool at a given version and pin it in the project or globally.

Guidelines:
- Always use tools rather than guessing version numbers or tool names.
- When the user asks to set up a tool, first confirm the tool exists via search_tool if unsure.
- Use list_remote_versions to find a suitable version before calling use_tool.
- If the user encounters permission or trust errors, suggest running trust_config for the project.
- For use_tool, prefer pinning versions per-project (global_=False) unless the user explicitly asks for a global install.
- When a version is unspecified, use 'latest' and inform the user.
- If required parameters are missing, ask the user to supply them.
"""


class MiseAgent(BaseAgent):
    """Agent specialised for mise environment configuration."""

    name: str = "mise"
    description: str = "Search, list, trust, and configure tool versions via mise."

    def _build_graph(self) -> "CompiledStateGraph":
        """Build a LangGraph ReAct agent with mise tools."""
        llm = create_llm(verbose=self.verbose)
        llm_with_tools = llm.bind_tools(MISE_TOOLS)

        tool_node = ToolNode(MISE_TOOLS)

        # ----------------------------------------------------------------
        # Nodes
        # ----------------------------------------------------------------

        def call_model(state: MessagesState) -> dict:  # type: ignore[type-arg]
            messages = state["messages"]
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
        graph.add_node("mise_agent", call_model)
        graph.add_node("tools", tool_node)

        graph.add_edge(START, "mise_agent")
        graph.add_conditional_edges("mise_agent", should_continue, {"tools": "tools", END: END})
        graph.add_edge("tools", "mise_agent")

        return graph.compile()
