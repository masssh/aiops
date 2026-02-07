import pytest
import os
from unittest.mock import MagicMock, patch
from src.agents.github_agent import github_agent
from src.models.state import OverallState

def test_github_agent_real_llm_execution():
    """
    Tests the github_agent using a real LLM call.
    Mocks only the shell command execution to avoid side effects.
    """
    if not os.getenv("GOOGLE_API_KEY"):
        pytest.skip("GOOGLE_API_KEY not found. Skipping real LLM test.")

    # Setup state with a dummy repository configuration
    state: OverallState = {
        "products_config": {
            "repositories": [
                {
                    "id": "test-owner/test-repo", 
                    "url": "https://github.com/test-owner/test-repo.git",
                    "path": "workspace/test-repo", 
                    "account": "test-account"
                }
            ]
        },
        "results": {}
    }
    
    # Mock only the command runner so we don't actually hit GitHub
    with patch("src.agents.github_agent.github_agent_logic._run_command") as mock_run:
        mock_run.return_value = "Success (Mocked Output)"
        
        # We also mock directory checks to simulate a new clone
        with patch("os.path.exists", return_value=False):
            with patch("os.makedirs"):
                # Pass prompt via configurable
                config = {"configurable": {"github_agent_prompt": "Force sync everything even if it exists."}}
                final_state = github_agent(state, config=config)
            
    # Verification
    assert final_state == state
    
    # The LLM should have decided to call both tools
    # 1. switch_github_auth
    # 2. clone_or_update_repo
    
    called_commands = [call[0][0] for call in mock_run.call_args_list]
    
    auth_called = any("auth" in cmd and "test-account" in cmd for cmd in called_commands)
    # Check for git clone with URL
    clone_called = any("clone" in cmd and "https://github.com/test-owner/test-repo.git" in cmd for cmd in called_commands)
    
    assert auth_called, f"LLM did not call switch_github_auth. Commands called: {called_commands}"
    assert clone_called, f"LLM did not call clone_or_update_repo with URL. Commands called: {called_commands}"

def test_github_agent_custom_prompt_filtering():
    """
    Tests if the LLM respects a custom prompt that tells it to filter repositories.
    """
    if not os.getenv("GOOGLE_API_KEY"):
        pytest.skip("GOOGLE_API_KEY not found. Skipping real LLM test.")

    # LLM instruction to skip this specific account
    custom_instruction = "If the account is 'skip-user', do NOT call any tools for that repository."
    
    state: OverallState = {
        "products_config": {
            "repositories": [
                {
                    "id": "test-owner/repo-to-skip", 
                    "path": "workspace/skip-repo", 
                    "account": "skip-user"
                }
            ]
        },
        "results": {}
    }
    
    config = {"configurable": {"github_agent_prompt": custom_instruction}}
    
    with patch("src.agents.github_agent.github_agent_logic._run_command") as mock_run:
        with patch("os.path.exists", return_value=False):
            with patch("os.makedirs"):
                github_agent(state, config=config)
            
    # LLM should have followed the instruction and NOT called the tools
    assert mock_run.call_count == 0, f"LLM ignored skip instruction. Commands called: {[call[0][0] for call in mock_run.call_args_list]}"
