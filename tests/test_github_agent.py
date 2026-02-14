import pytest
import os
from unittest.mock import MagicMock, patch
from src.agents.github_agent import github_agent
from src.models.state import OverallState

def test_github_agent():
    """
    Tests the github_agent using Ollama provider with qwen3:8b.
    Note: qwen2.5-coder:7b does not support tool calling in LangChain format.
    Mocks only the shell command execution to avoid side effects.
    """
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
                # Use Ollama provider with qwen3:8b (supports tool calling)
                config = {
                    "configurable": {
                        "provider": "ollama",
                        "model": "qwen3:8b",
                        "github_agent_prompt": "Clone and sync all repositories."
                    }
                }
                try:
                    final_state = github_agent(state, config=config)
                    # Verification
                    assert final_state == state

                    # Check if LLM called the tools
                    called_commands = [call[0][0] for call in mock_run.call_args_list]

                    # The LLM should have attempted to clone the repository
                    # (It may or may not call auth depending on the model's reasoning)
                    assert len(called_commands) > 0, f"LLM did not call any tools. Commands called: {called_commands}"
                    print(f"✓ Ollama test passed. Commands called: {called_commands}")

                except Exception as e:
                    error_msg = str(e)
                    if "Ollama" in error_msg or "connection" in error_msg.lower():
                        pytest.skip(f"Skipping Ollama test: {error_msg}")
                    else:
                        pytest.fail(f"Ollama test failed: {e}")


