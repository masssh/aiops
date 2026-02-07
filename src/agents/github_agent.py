import subprocess
import os
import logging
from typing import Optional
from src.models.state import OverallState

logger = logging.getLogger(__name__)

class GitHubManager:
    """Handles GitHub repository operations using gh CLI and git."""
    
    def __init__(self, workspace_root: str = "workspace"):
        self.workspace_root = workspace_root
        if not os.path.exists(self.workspace_root):
            os.makedirs(self.workspace_root)

    def _run_command(self, cmd: list[str], cwd: Optional[str] = None) -> str:
        """Helper to run shell commands."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            error_msg = f"""Command '{' '.join(cmd)}' failed with exit code {e.returncode}
Stdout: {e.stdout}
Stderr: {e.stderr}"""
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def switch_auth(self, account: str) -> str:
        """Switch gh CLI authentication to the specified account."""
        logger.info(f"Switching GitHub account to: {account}")
        return self._run_command(["gh", "auth", "switch", "--user", account])

    def list_accounts(self) -> list[str]:
        """List authenticated gh CLI accounts."""
        output = self._run_command(["gh", "auth", "status"])
        # Parsing gh auth status output can be tricky as it's meant for human consumption
        # but usually it contains account names.
        return output.splitlines()

    def clone_or_update(self, repo_id: str, local_path: str) -> str:
        """Clone the repository if it doesn't exist, otherwise update it."""
        # Ensure path is relative to current directory if not absolute
        full_path = os.path.abspath(local_path)
        
        if os.path.exists(os.path.join(full_path, ".git")):
            logger.info(f"Updating repository: {repo_id} at {local_path}")
            # Using git pull to update
            return self._run_command(["git", "pull"], cwd=full_path)
        else:
            logger.info(f"Cloning repository: {repo_id} to {local_path}")
            # Ensure parent directory exists
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            return self._run_command(["gh", "repo", "clone", repo_id, full_path])

def github_agent(state: OverallState) -> OverallState:
    """
    LangGraph node that ensures all repositories in the configuration are 
    cloned and up to date.
    
    Expects state['products_config']['repositories'] to contain:
    - id: repository identifier (e.g., 'owner/repo')
    - path: local path to clone into
    - account: (optional) GitHub account to switch to before cloning
    """
    manager = GitHubManager()
    repositories = state.get("products_config", {}).get("repositories", [])
    
    for repo in repositories:
        repo_id = repo.get("id")
        path = repo.get("path")
        account = repo.get("account")
        
        if account:
            try:
                manager.switch_auth(account)
            except Exception as e:
                logger.warning(f"Failed to switch to account {account}: {e}")
        
        if repo_id and path:
            try:
                manager.clone_or_update(repo_id, path)
            except Exception as e:
                logger.error(f"Failed to sync repository {repo_id}: {e}")
                # We might want to stop or continue depending on the requirements.
                # For now, we continue to other repositories.
                
    return state
