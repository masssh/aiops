import pytest
from unittest.mock import patch
from loguru import logger
from src.agents.github_agent import (
    github_agent,
    git_status,
    git_branch_create,
    git_commit,
    gh_pr_create,
    gh_issue_create,
)
from src.models.state import OverallState


def test_github_agent_repository_sync():
    """
    Tests the github_agent's default behavior: repository cloning and syncing.
    Uses Ollama provider with qwen3:8b.
    Mocks shell command execution to avoid side effects.
    """
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

    with patch("src.agents.github_agent.github_agent_logic._run_command") as mock_run:
        mock_run.return_value = "Success (Mocked Output)"

        with patch("os.path.exists", return_value=False):
            with patch("os.makedirs"):
                config = {
                    "configurable": {
                        "provider": "ollama",
                        "model": "qwen3:8b",
                        "prompt": "Clone and sync all repositories."
                    }
                }
                try:
                    final_state = github_agent(state, config=config)
                    assert final_state == state

                    called_commands = [call[0][0] for call in mock_run.call_args_list]
                    assert len(called_commands) > 0, f"LLM did not call any tools. Commands called: {called_commands}"
                    logger.info(f"✓ Repository sync test passed. Commands called: {called_commands}")

                except Exception as e:
                    error_msg = str(e)
                    if "Ollama" in error_msg or "connection" in error_msg.lower():
                        pytest.skip(f"Skipping Ollama test: {error_msg}")
                    else:
                        pytest.fail(f"Ollama test failed: {e}")


def test_github_agent_custom_workflow():
    """
    Tests the github_agent with a custom workflow involving multiple Git operations:
    - Check repository status
    - Create a new branch
    - Make changes and commit
    - Create a pull request
    """
    state: OverallState = {
        "products_config": {},
        "results": {}
    }

    with patch("src.agents.github_agent.github_agent_logic._run_command") as mock_run:
        mock_run.return_value = "Success (Mocked Output)"

        custom_instructions = (
            "In the repository at 'workspace/test-repo':\n"
            "1. Check the current status\n"
            "2. Create a new branch called 'feature/test-branch'\n"
            "3. Commit changes with message 'Add new feature'\n"
            "4. Create a pull request titled 'Test Feature' with body 'Testing new feature'"
        )

        config = {
            "configurable": {
                "provider": "ollama",
                "model": "qwen3:8b",
                "prompt": custom_instructions,
                "max_iterations": 10
            }
        }

        try:
            final_state = github_agent(state, config=config)
            assert final_state == state

            called_commands = [call[0][0] for call in mock_run.call_args_list]
            assert len(called_commands) > 0, "LLM should have called tools for the workflow"
            logger.info(f"✓ Custom workflow test passed. Commands called: {called_commands}")

        except Exception as e:
            error_msg = str(e)
            if "Ollama" in error_msg or "connection" in error_msg.lower():
                pytest.skip(f"Skipping Ollama test: {error_msg}")
            else:
                pytest.fail(f"Custom workflow test failed: {e}")


def test_git_status_tool():
    """Test the git_status tool directly."""
    with patch("src.agents.github_agent.github_agent_logic._run_command") as mock_run:
        mock_run.return_value = "On branch main\nnothing to commit, working tree clean"

        result = git_status.invoke({"repo_path": "/test/repo"})

        assert "On branch main" in result
        mock_run.assert_called_once_with(["git", "status"], cwd="/test/repo")


def test_git_branch_create_tool():
    """Test the git_branch_create tool directly."""
    with patch("src.agents.github_agent.github_agent_logic._run_command") as mock_run:
        mock_run.return_value = "Switched to a new branch 'feature-x'"

        result = git_branch_create.invoke({
            "repo_path": "/test/repo",
            "branch_name": "feature-x",
            "checkout": True
        })

        assert "feature-x" in result or "Success" in result
        # Should be called at least once for branch creation
        assert mock_run.call_count >= 1


def test_git_commit_tool():
    """Test the git_commit tool directly."""
    with patch("src.agents.github_agent.github_agent_logic._run_command") as mock_run:
        mock_run.return_value = "[main abc123] Test commit"

        result = git_commit.invoke({
            "repo_path": "/test/repo",
            "message": "Test commit"
        })

        assert "abc123" in result or "Success" in result
        mock_run.assert_called_once_with(
            ["git", "commit", "-m", "Test commit"],
            cwd="/test/repo"
        )


def test_gh_pr_create_tool():
    """Test the gh_pr_create tool directly."""
    with patch("src.agents.github_agent.github_agent_logic._run_command") as mock_run:
        mock_run.return_value = "https://github.com/owner/repo/pull/123"

        result = gh_pr_create.invoke({
            "repo_path": "/test/repo",
            "title": "Test PR",
            "body": "This is a test PR",
            "base": "main",
            "head": "feature-branch"
        })

        assert "github.com" in result or "Success" in result
        # Verify the command was called with correct arguments
        assert mock_run.call_count == 1
        called_cmd = mock_run.call_args[0][0]
        assert "gh" in called_cmd
        assert "pr" in called_cmd
        assert "create" in called_cmd


def test_gh_issue_create_tool():
    """Test the gh_issue_create tool directly."""
    with patch("src.agents.github_agent.github_agent_logic._run_command") as mock_run:
        mock_run.return_value = "https://github.com/owner/repo/issues/456"

        result = gh_issue_create.invoke({
            "repo_path": "/test/repo",
            "title": "Test Issue",
            "body": "This is a test issue"
        })

        assert "github.com" in result or "Success" in result or "456" in result
        mock_run.assert_called_once()
        called_cmd = mock_run.call_args[0][0]
        assert "gh" in called_cmd
        assert "issue" in called_cmd
        assert "create" in called_cmd
