import subprocess
import os
import logging
from typing import List, Optional
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from src.models.state import OverallState
from src.utils.llm import get_llm, Provider

logger = logging.getLogger(__name__)

class GitHubAgent:
    """Execution logic for GitHub operations."""
    def _run_command(self, cmd: list[str], cwd: Optional[str] = None) -> str:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            return f"Error: {e.stderr}"

github_agent_logic = GitHubAgent()

@tool
def switch_github_auth(account: str) -> str:
    """Switch gh CLI authentication to the specified account."""
    logger.info(f"Switching GitHub account to: {account}")
    return github_agent_logic._run_command(["gh", "auth", "switch", "--user", account])

@tool
def clone_or_update_repo(repo_id: str, local_path: str, url: Optional[str] = None) -> str:
    """
    Clone the repository if it doesn't exist, otherwise update it using git pull.
    If 'url' is provided, it will be used for cloning. Otherwise, 'repo_id' is used with 'gh repo clone'.
    """
    full_path = os.path.abspath(local_path)
    if os.path.exists(os.path.join(full_path, ".git")):
        logger.info(f"Updating repository at {local_path}")
        return github_agent_logic._run_command(["git", "pull"], cwd=full_path)
    else:
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        if url:
            logger.info(f"Cloning repository from URL: {url} to {local_path}")
            return github_agent_logic._run_command(["git", "clone", url, full_path])
        else:
            logger.info(f"Cloning repository: {repo_id} to {local_path}")
            return github_agent_logic._run_command(["gh", "repo", "clone", repo_id, full_path])

from langchain_core.runnables import RunnableConfig

def github_agent(state: OverallState, config: RunnableConfig = None) -> OverallState:
    """
    LangGraph node that uses an LLM to ensure all repositories are
    cloned and up to date.

    Can be configured via RunnableConfig:
        config = {"configurable": {"provider": "ollama", "model": "qwen2.5-coder:7b"}}
    """
    # Get custom prompt and LLM config from config if provided
    configurable = config.get("configurable", {}) if config else {}
    custom_prompt = configurable.get("github_agent_prompt")
    provider: Provider = configurable.get("provider", "ollama")
    model: str | None = configurable.get("model", None)

    llm = get_llm(provider=provider, model=model)
    tools = [switch_github_auth, clone_or_update_repo]
    llm_with_tools = llm.bind_tools(tools)
    
    repositories = state.get("products_config", {}).get("repositories", [])
    if not repositories:
        return state

    system_msg = SystemMessage(content=(
        "You are a GitHub automation assistant. Your task is to ensure all requested "
        "repositories are cloned and up-to-date in the workspace. "
        "1. For each repository, check if an 'account' is specified. If so, call 'switch_github_auth' first. "
        "2. Then call 'clone_or_update_repo' with the repository 'id', 'path', and 'url' (if provided). "
        "Process each repository configuration completely before moving to the next one."
    ))
    
    repo_info = "\n".join([str(r) for r in repositories])
    
    if custom_prompt:
        prompt = f"{custom_prompt}\n\nRepository Configuration:\n{repo_info}"
    else:
        prompt = f"Please sync the following repositories based on their configuration:\n{repo_info}"
    
    messages = [system_msg, HumanMessage(content=prompt)]
    
    # Tool execution loop
    for _ in range(15):  # Max iterations to prevent infinite loops
        ai_msg = llm_with_tools.invoke(messages)
        messages.append(ai_msg)
        
        if not ai_msg.tool_calls:
            break
            
        for tool_call in ai_msg.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            
            if tool_name == "switch_github_auth":
                result = switch_github_auth.invoke(tool_args)
            elif tool_name == "clone_or_update_repo":
                result = clone_or_update_repo.invoke(tool_args)
            else:
                result = f"Error: Tool {tool_name} not found."
                
            messages.append(ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"]
            ))
            
    return state