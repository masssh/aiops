import logging
from typing import Optional, List
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from src.models.state import OverallState
from src.agents.base_command_agent import BaseCommandAgent

logger = logging.getLogger(__name__)


class HelloAgent(BaseCommandAgent):
    """A simple agent that says hello using a configurable LLM provider."""

    def get_tools(self) -> List[BaseTool]:
        """Return list of tools (hello agent has no tools)."""
        return []

    def get_system_message(self) -> SystemMessage:
        """Return system message describing agent capabilities."""
        return SystemMessage(content=(
            "You are a friendly greeting assistant.\n\n"
            "Your role is to provide warm, welcoming greetings and introductions.\n"
            "You can respond to various greeting requests and customize your responses "
            "based on the user's instructions."
        ))

    def get_default_prompt(self) -> str:
        """Return default greeting prompt."""
        return f"Say 'Hello World from {self.provider.title()} Agent!'"


def hello_agent(state: OverallState, config: Optional[RunnableConfig] = None) -> OverallState:
    """
    A simple agent that says hello using a configurable LLM provider.

    Can be configured via RunnableConfig:
        config = {
            "configurable": {
                "provider": "ollama",
                "model": "qwen2.5-coder:7b",
                "prompt": "Your custom greeting instructions...",
                "project_root": "/path/to/project",  # Optional: project root directory
                "max_iterations": 20,  # Optional: override default iteration limit
                "log_dir": "logs",  # Optional: directory for log files
                "verbose": False  # Optional: whether to print out LLM response text
            }
        }
    """
    agent = HelloAgent("hello_agent", state, config)
    return agent.run()