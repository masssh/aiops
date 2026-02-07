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
                    "path": "workspace/test-repo", 
                    "account": "test-account"
                }
            ]
        },
        "results": {}
    }
    
    # Mock only the command runner so we don't actually hit GitHub
    with patch("src.agents.github_agent.manager._run_command") as mock_run:
        mock_run.return_value = "Success (Mocked Output)"
        
        # We also mock directory checks to simulate a new clone
        with patch("os.path.exists", return_value=False):
            with patch("os.makedirs"):
                final_state = github_agent(state)
            
    # Verification
    assert final_state == state
    
    # The LLM should have decided to call both tools
    # 1. switch_github_auth
    # 2. clone_or_update_repo
    
    # We check if the mocked run_command was called with appropriate keywords
    called_commands = [call[0][0] for call in mock_run.call_args_list]
    
    auth_called = any("auth" in cmd and "test-account" in cmd for cmd in called_commands)
    clone_called = any("clone" in cmd and "test-owner/test-repo" in cmd for cmd in called_commands)
    
    assert auth_called, f"LLM did not call switch_github_auth. Commands called: {called_commands}"
    assert clone_called, f"LLM did not call clone_or_update_repo. Commands called: {called_commands}"