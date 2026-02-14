"""
Base Command Agent Module

This module provides a common foundation for command-line tool agents
(e.g., GitHub Agent, Gradle Agent) that follow a similar pattern of:
1. Tool definition using @tool decorator
2. LLM-driven tool execution loop
3. Logging and configuration management

It extracts common functionality to reduce code duplication and ensure
consistency across different command agent implementations.
"""

import os
import logging
from typing import Optional, List, Callable, Any
from langchain_core.tools import BaseTool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from src.models.state import OverallState
from src.utils.llm import get_llm, Provider
from src.utils.logging import setup_agent_logger

logger = logging.getLogger(__name__)


class BaseCommandAgent:
    """
    Base class for command-line tool agents.

    Provides common functionality for:
    - Configuration management
    - Logging setup
    - Tool execution loop
    - LLM interaction pattern

    Subclasses should implement:
    - get_tools(): Return list of available tools
    - get_system_message(): Return system message describing agent capabilities
    - get_default_prompt(): Return default user prompt
    """

    def __init__(
        self,
        agent_name: str,
        state: OverallState,
        config: Optional[RunnableConfig] = None
    ):
        """
        Initialize the base command agent.

        Args:
            agent_name: Name of the agent (e.g., "github_agent", "gradle_agent")
            state: LangGraph state
            config: Runnable configuration
        """
        self.agent_name = agent_name
        self.state = state
        self.config = config or {}

        # Extract configuration
        self.configurable = self.config.get("configurable", {})
        self.custom_prompt = self.configurable.get(f"{agent_name}_prompt")
        self.provider: Provider = self.configurable.get("provider", "ollama")
        self.model: str | None = self.configurable.get("model", None)
        self.project_root: str = self.configurable.get("project_root", os.getcwd())
        self.max_iterations: int = self.configurable.get("max_iterations", 20)
        self.log_dir: str = self.configurable.get("log_dir", "logs")
        self.verbose: bool = self.configurable.get("verbose", False)

        # Calculate workspace directory absolute path
        self.workspace_dir = os.path.abspath(os.path.join(self.project_root, "workspace"))

        # Set up dedicated logger for this agent execution
        self.agent_logger = setup_agent_logger(agent_name, self.log_dir)

        self._log_initialization()

    def _log_initialization(self):
        """Log agent initialization details."""
        self.agent_logger.info("="*80)
        self.agent_logger.info(f"{self.agent_name.replace('_', ' ').title()} started")
        self.agent_logger.info(f"Provider: {self.provider}, Model: {self.model}")
        self.agent_logger.info(f"Verbose: {self.verbose}")
        self.agent_logger.info(f"Project root: {self.project_root}")
        self.agent_logger.info(f"Workspace directory: {self.workspace_dir}")
        self.agent_logger.info(f"Max iterations: {self.max_iterations}")
        self.agent_logger.info("="*80)

    def get_tools(self) -> List[BaseTool]:
        """
        Get the list of tools available to this agent.

        Must be implemented by subclasses.

        Returns:
            List of LangChain tools
        """
        raise NotImplementedError("Subclasses must implement get_tools()")

    def get_system_message(self) -> SystemMessage:
        """
        Get the system message describing agent capabilities.

        Must be implemented by subclasses.

        Returns:
            SystemMessage for the agent
        """
        raise NotImplementedError("Subclasses must implement get_system_message()")

    def get_default_prompt(self) -> str:
        """
        Get the default user prompt when no custom prompt is provided.

        Must be implemented by subclasses.

        Returns:
            Default user prompt string
        """
        raise NotImplementedError("Subclasses must implement get_default_prompt()")

    def get_user_prompt(self) -> str:
        """
        Get the user prompt to use (custom or default).

        Returns:
            User prompt string
        """
        if self.custom_prompt:
            self.agent_logger.info(f"Using custom prompt: {self.custom_prompt}")
            return self.custom_prompt
        else:
            prompt = self.get_default_prompt()
            self.agent_logger.info("Using default prompt")
            return prompt

    def execute_tool(self, tool_call: Any, tools: List[BaseTool]) -> str:
        """
        Execute a single tool call.

        Args:
            tool_call: Tool call information from LLM
            tools: List of available tools

        Returns:
            Tool execution result as string
        """
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        self.agent_logger.info(f"\n--- Executing tool: {tool_name} ---")
        self.agent_logger.info(f"Tool arguments: {tool_args}")

        # Find and invoke the appropriate tool
        tool_function = None
        for tool in tools:
            if tool.name == tool_name:
                tool_function = tool
                break

        if tool_function:
            try:
                self.agent_logger.info(f"Invoking {tool_name}...")
                result = tool_function.invoke(tool_args)
                self.agent_logger.info(f"Tool execution successful")
                self.agent_logger.info(f"Tool result: {result}")
                return str(result)
            except Exception as e:
                result = f"Error executing {tool_name}: {str(e)}"
                self.agent_logger.error(f"Tool execution failed: {str(e)}")
                logger.error(result)
                return result
        else:
            result = f"Error: Tool '{tool_name}' not found in available tools."
            self.agent_logger.error(result)
            logger.error(result)
            return result

    def run_tool_execution_loop(
        self,
        llm_with_tools: Any,
        messages: List,
        tools: List[BaseTool]
    ) -> List:
        """
        Run the main tool execution loop.

        Args:
            llm_with_tools: LLM instance with tools bound
            messages: Initial message list
            tools: List of available tools

        Returns:
            Final message list
        """
        for iteration in range(self.max_iterations):
            self.agent_logger.info(f"\n{'='*80}")
            self.agent_logger.info(f"Iteration {iteration + 1}/{self.max_iterations}")
            self.agent_logger.info(f"{'='*80}")

            # Invoke LLM to decide next action
            self.agent_logger.info("Invoking LLM to determine next action...")
            ai_msg = llm_with_tools.invoke(messages)
            messages.append(ai_msg)

            # Log LLM's response content (if any)
            if hasattr(ai_msg, 'content') and ai_msg.content:
                self.agent_logger.info(f"LLM response content: {ai_msg.content}")

            if not ai_msg.tool_calls:
                # LLM decided it's done
                self.agent_logger.info("LLM has completed its task (no more tool calls)")
                if hasattr(ai_msg, 'content') and ai_msg.content:
                    self.agent_logger.info(f"Final message: {ai_msg.content}")
                logger.info(f"{self.agent_name} completed after {iteration + 1} iterations")
                break

            # Log LLM's decision
            self.agent_logger.info(f"LLM decided to execute {len(ai_msg.tool_calls)} tool(s):")
            for idx, tool_call in enumerate(ai_msg.tool_calls, 1):
                self.agent_logger.info(f"  {idx}. {tool_call['name']}")

            # Execute all tool calls from this iteration
            for tool_call in ai_msg.tool_calls:
                result = self.execute_tool(tool_call, tools)
                messages.append(ToolMessage(
                    content=result,
                    tool_call_id=tool_call["id"]
                ))

        return messages

    def run(self) -> OverallState:
        """
        Execute the agent's main workflow.

        Returns:
            Updated state
        """
        # Get tools and messages
        tools = self.get_tools()
        system_msg = self.get_system_message()
        user_prompt = self.get_user_prompt()

        self.agent_logger.info(f"Full user prompt:\n{user_prompt}")

        # Initialize LLM with tools
        llm = get_llm(provider=self.provider, model=self.model, verbose=self.verbose)
        llm_with_tools = llm.bind_tools(tools)

        # Prepare initial messages
        messages = [system_msg, HumanMessage(content=user_prompt)]

        # Run tool execution loop
        self.run_tool_execution_loop(llm_with_tools, messages, tools)

        # Log completion
        self.agent_logger.info("\n" + "="*80)
        self.agent_logger.info(f"{self.agent_name.replace('_', ' ').title()} execution completed")
        self.agent_logger.info("="*80)

        return self.state


def create_command_agent(
    agent_name: str,
    tools: List[BaseTool],
    system_message_builder: Callable[[str], str],
    default_prompt_builder: Optional[Callable[[OverallState], str]] = None
) -> Callable[[OverallState, Optional[RunnableConfig]], OverallState]:
    """
    Factory function to create a command agent with specified tools and behavior.

    This is a convenience function that creates a complete agent function
    without requiring a full subclass.

    Args:
        agent_name: Name of the agent (e.g., "github_agent")
        tools: List of LangChain tools available to the agent
        system_message_builder: Function that takes workspace_dir and returns system message content
        default_prompt_builder: Optional function that takes state and returns default prompt

    Returns:
        Agent function compatible with LangGraph nodes

    Example:
        def build_system_message(workspace_dir: str) -> str:
            return f"You are a Gradle agent. Workspace: {workspace_dir}"

        gradle_agent = create_command_agent(
            "gradle_agent",
            ALL_GRADLE_TOOLS,
            build_system_message,
            lambda state: "Ready for Gradle operations"
        )
    """

    class DynamicCommandAgent(BaseCommandAgent):
        """Dynamically created command agent."""

        def get_tools(self) -> List[BaseTool]:
            return tools

        def get_system_message(self) -> SystemMessage:
            content = system_message_builder(self.workspace_dir)
            return SystemMessage(content=content)

        def get_default_prompt(self) -> str:
            if default_prompt_builder:
                return default_prompt_builder(self.state)
            return f"Ready to assist with {agent_name.replace('_', ' ')} operations."

    def agent_function(state: OverallState, config: Optional[RunnableConfig] = None) -> OverallState:
        """Generated agent function."""
        agent = DynamicCommandAgent(agent_name, state, config)
        return agent.run()

    return agent_function
