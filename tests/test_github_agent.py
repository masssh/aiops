import pytest
from unittest.mock import MagicMock, patch
from src.agents.github_agent import GitHubManager, github_agent
from src.models.state import OverallState
import os

@pytest.fixture
def mock_subprocess():
    with patch("subprocess.run") as mock_run:
        yield mock_run

def test_github_manager_switch_auth(mock_subprocess):
    mock_subprocess.return_value = MagicMock(returncode=0, stdout="Successfully switched", stderr="")
    
    manager = GitHubManager()
    result = manager.switch_auth("test-user")
    
    assert result == "Successfully switched"
    mock_subprocess.assert_called_with(
        ["gh", "auth", "switch", "--user", "test-user"],
        capture_output=True,
        text=True,
        cwd=None,
        check=True
    )

def test_github_manager_clone_new(mock_subprocess):
    mock_subprocess.return_value = MagicMock(returncode=0, stdout="Cloned", stderr="")
    
    with patch("os.path.exists", side_effect=lambda p: False if ".git" in p else True):
        manager = GitHubManager()
        # Mocking os.makedirs to avoid creating real dirs
        with patch("os.makedirs"):
            result = manager.clone_or_update("owner/repo", "workspace/repo")
            
    assert result == "Cloned"
    # Check if gh repo clone was called
    mock_subprocess.assert_called_with(
        ["gh", "repo", "clone", "owner/repo", os.path.abspath("workspace/repo")],
        capture_output=True,
        text=True,
        cwd=None,
        check=True
    )

def test_github_manager_update_existing(mock_subprocess):
    mock_subprocess.return_value = MagicMock(returncode=0, stdout="Already up to date", stderr="")
    
    with patch("os.path.exists", return_value=True):
        manager = GitHubManager()
        result = manager.clone_or_update("owner/repo", "workspace/repo")
            
    assert result == "Already up to date"
    # Check if git pull was called
    mock_subprocess.assert_called_with(
        ["git", "pull"],
        capture_output=True,
        text=True,
        cwd=os.path.abspath("workspace/repo"),
        check=True
    )

def test_github_agent_node(mock_subprocess):
    mock_subprocess.return_value = MagicMock(returncode=0, stdout="Done", stderr="")
    
    state: OverallState = {
        "products_config": {
            "repositories": [
                {"id": "owner/repo1", "path": "workspace/repo1", "account": "user1"}
            ]
        },
        "results": {}
    }
    
    with patch("os.path.exists", return_value=False):
        with patch("os.makedirs"):
            final_state = github_agent(state)
            
    assert final_state == state
    # Should have called auth switch and clone
    assert mock_subprocess.call_count == 2
    calls = [call[0][0] for call in mock_subprocess.call_args_list]
    assert ["gh", "auth", "switch", "--user", "user1"] in calls
    assert ["gh", "repo", "clone", "owner/repo1", os.path.abspath("workspace/repo1")] in calls
