import os
import logging
from typing import Optional, List
from langchain_core.tools import tool, BaseTool
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from src.models.state import OverallState
from src.agents.base_command_agent import BaseCommandAgent
from src.utils.command import run_command

logger = logging.getLogger(__name__)

# ============================================================================
# Authentication & Account Management
# ============================================================================

@tool
def gh_auth_switch(account: str) -> str:
    """Switch gh CLI authentication to the specified GitHub account."""
    logger.info(f"Switching GitHub account to: {account}")
    return run_command(["gh", "auth", "switch", "--user", account])

@tool
def gh_auth_status() -> str:
    """Check the current GitHub authentication status."""
    logger.info("Checking GitHub authentication status")
    return run_command(["gh", "auth", "status"])

# ============================================================================
# Repository Operations
# ============================================================================

@tool
def gh_repo_clone(repo_id: str, local_path: str) -> str:
    """
    Clone a GitHub repository using gh CLI.

    Args:
        repo_id: Repository identifier (e.g., 'owner/repo')
        local_path: Local path where the repository should be cloned
    """
    full_path = os.path.abspath(local_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    logger.info(f"Cloning repository: {repo_id} to {local_path}")
    return run_command(["gh", "repo", "clone", repo_id, full_path])

@tool
def git_clone(url: str, local_path: str) -> str:
    """
    Clone a Git repository using git clone.

    Args:
        url: Git repository URL
        local_path: Local path where the repository should be cloned
    """
    full_path = os.path.abspath(local_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    logger.info(f"Cloning repository from URL: {url} to {local_path}")
    return run_command(["git", "clone", url, full_path])

@tool
def gh_repo_fork(repo_id: str, clone: bool = True) -> str:
    """
    Fork a GitHub repository.

    Args:
        repo_id: Repository identifier (e.g., 'owner/repo')
        clone: Whether to clone the forked repository locally
    """
    logger.info(f"Forking repository: {repo_id}")
    cmd = ["gh", "repo", "fork", repo_id]
    if clone:
        cmd.append("--clone")
    return run_command(cmd)

@tool
def gh_repo_view(repo_id: str, cwd: Optional[str] = None) -> str:
    """
    View GitHub repository information.

    Args:
        repo_id: Repository identifier (e.g., 'owner/repo'), or leave empty to view current repo
        cwd: Working directory (for current repo)
    """
    logger.info(f"Viewing repository: {repo_id or 'current'}")
    cmd = ["gh", "repo", "view"]
    if repo_id:
        cmd.append(repo_id)
    return run_command(cmd, cwd=cwd)

# ============================================================================
# Git Basic Operations
# ============================================================================

@tool
def git_status(repo_path: str) -> str:
    """
    Get the current status of a Git repository.

    Args:
        repo_path: Path to the Git repository
    """
    logger.info(f"Getting git status for: {repo_path}")
    return run_command(["git", "status"], cwd=repo_path)

@tool
def git_pull(repo_path: str, remote: str = "origin", branch: Optional[str] = None) -> str:
    """
    Pull changes from a remote repository.

    Args:
        repo_path: Path to the Git repository
        remote: Remote name (default: origin)
        branch: Branch name (optional)
    """
    logger.info(f"Pulling from {remote} in {repo_path}")
    cmd = ["git", "pull", remote]
    if branch:
        cmd.append(branch)
    return run_command(cmd, cwd=repo_path)

@tool
def git_push(repo_path: str, remote: str = "origin", branch: Optional[str] = None, set_upstream: bool = False) -> str:
    """
    Push changes to a remote repository.

    Args:
        repo_path: Path to the Git repository
        remote: Remote name (default: origin)
        branch: Branch name (optional)
        set_upstream: Set upstream tracking (--set-upstream)
    """
    logger.info(f"Pushing to {remote} from {repo_path}")
    cmd = ["git", "push"]
    if set_upstream:
        cmd.extend(["--set-upstream", remote])
        if branch:
            cmd.append(branch)
    else:
        cmd.append(remote)
        if branch:
            cmd.append(branch)
    return run_command(cmd, cwd=repo_path)

@tool
def git_add(repo_path: str, files: str = ".") -> str:
    """
    Add files to the staging area.

    Args:
        repo_path: Path to the Git repository
        files: Files or patterns to add (default: "." for all)
    """
    logger.info(f"Adding files: {files} in {repo_path}")
    return run_command(["git", "add", files], cwd=repo_path)

@tool
def git_commit(repo_path: str, message: str) -> str:
    """
    Create a Git commit with the staged changes.

    Args:
        repo_path: Path to the Git repository
        message: Commit message
    """
    logger.info(f"Creating commit in {repo_path}")
    return run_command(["git", "commit", "-m", message], cwd=repo_path)

@tool
def git_branch_list(repo_path: str, all_branches: bool = False) -> str:
    """
    List Git branches.

    Args:
        repo_path: Path to the Git repository
        all_branches: Show all branches including remote (default: False)
    """
    logger.info(f"Listing branches in {repo_path}")
    cmd = ["git", "branch"]
    if all_branches:
        cmd.append("-a")
    return run_command(cmd, cwd=repo_path)

@tool
def git_branch_create(repo_path: str, branch_name: str, checkout: bool = True) -> str:
    """
    Create a new Git branch.

    Args:
        repo_path: Path to the Git repository
        branch_name: Name of the new branch
        checkout: Checkout the new branch immediately (default: True)
    """
    logger.info(f"Creating branch '{branch_name}' in {repo_path}")
    cmd = ["git", "branch", branch_name]
    result = run_command(cmd, cwd=repo_path)

    if checkout and "Error" not in result:
        checkout_cmd = ["git", "checkout", branch_name]
        checkout_result = run_command(checkout_cmd, cwd=repo_path)
        return f"{result}\n{checkout_result}"
    return result

@tool
def git_checkout(repo_path: str, branch_name: str) -> str:
    """
    Checkout a Git branch.

    Args:
        repo_path: Path to the Git repository
        branch_name: Branch name to checkout
    """
    logger.info(f"Checking out branch '{branch_name}' in {repo_path}")
    return run_command(["git", "checkout", branch_name], cwd=repo_path)

@tool
def git_log(repo_path: str, max_count: int = 10) -> str:
    """
    Show Git commit history.

    Args:
        repo_path: Path to the Git repository
        max_count: Maximum number of commits to show (default: 10)
    """
    logger.info(f"Getting git log in {repo_path}")
    return run_command(
        ["git", "log", f"--max-count={max_count}", "--oneline"],
        cwd=repo_path
    )

# ============================================================================
# Pull Request Operations
# ============================================================================

@tool
def gh_pr_create(repo_path: str, title: str, body: str, base: Optional[str] = None, head: Optional[str] = None) -> str:
    """
    Create a GitHub Pull Request.

    Args:
        repo_path: Path to the Git repository
        title: PR title
        body: PR description
        base: Base branch (default: repository default branch)
        head: Head branch (default: current branch)
    """
    logger.info(f"Creating PR in {repo_path}")
    cmd = ["gh", "pr", "create", "--title", title, "--body", body]
    if base:
        cmd.extend(["--base", base])
    if head:
        cmd.extend(["--head", head])
    return run_command(cmd, cwd=repo_path)

@tool
def gh_pr_list(repo_path: str, state: str = "open", limit: int = 10) -> str:
    """
    List GitHub Pull Requests.

    Args:
        repo_path: Path to the Git repository
        state: PR state: open, closed, merged, all (default: open)
        limit: Maximum number of PRs to list (default: 10)
    """
    logger.info(f"Listing PRs in {repo_path}")
    return run_command(
        ["gh", "pr", "list", "--state", state, "--limit", str(limit)],
        cwd=repo_path
    )

@tool
def gh_pr_view(pr_number: str, repo_path: Optional[str] = None) -> str:
    """
    View details of a GitHub Pull Request.

    Args:
        pr_number: PR number
        repo_path: Path to the Git repository (optional)
    """
    logger.info(f"Viewing PR #{pr_number}")
    return run_command(["gh", "pr", "view", pr_number], cwd=repo_path)

@tool
def gh_pr_merge(pr_number: str, repo_path: Optional[str] = None, merge_method: str = "merge") -> str:
    """
    Merge a GitHub Pull Request.

    Args:
        pr_number: PR number
        repo_path: Path to the Git repository (optional)
        merge_method: Merge method: merge, squash, rebase (default: merge)
    """
    logger.info(f"Merging PR #{pr_number} using {merge_method}")
    return run_command(
        ["gh", "pr", "merge", pr_number, f"--{merge_method}"],
        cwd=repo_path
    )

@tool
def gh_pr_comment(pr_number: str, body: str, repo_path: Optional[str] = None) -> str:
    """
    Add a comment to a GitHub Pull Request.

    Args:
        pr_number: PR number
        body: Comment text
        repo_path: Path to the Git repository (optional)
    """
    logger.info(f"Adding comment to PR #{pr_number}")
    return run_command(
        ["gh", "pr", "comment", pr_number, "--body", body],
        cwd=repo_path
    )

@tool
def gh_pr_checkout(pr_number: str, repo_path: Optional[str] = None) -> str:
    """
    Checkout a Pull Request locally.

    Args:
        pr_number: PR number
        repo_path: Path to the Git repository (optional)
    """
    logger.info(f"Checking out PR #{pr_number}")
    return run_command(["gh", "pr", "checkout", pr_number], cwd=repo_path)

# ============================================================================
# Issue Operations
# ============================================================================

@tool
def gh_issue_create(repo_path: str, title: str, body: str) -> str:
    """
    Create a GitHub Issue.

    Args:
        repo_path: Path to the Git repository
        title: Issue title
        body: Issue description
    """
    logger.info(f"Creating issue in {repo_path}")
    return run_command(
        ["gh", "issue", "create", "--title", title, "--body", body],
        cwd=repo_path
    )

@tool
def gh_issue_list(repo_path: str, state: str = "open", limit: int = 10) -> str:
    """
    List GitHub Issues.

    Args:
        repo_path: Path to the Git repository
        state: Issue state: open, closed, all (default: open)
        limit: Maximum number of issues to list (default: 10)
    """
    logger.info(f"Listing issues in {repo_path}")
    return run_command(
        ["gh", "issue", "list", "--state", state, "--limit", str(limit)],
        cwd=repo_path
    )

@tool
def gh_issue_view(issue_number: str, repo_path: Optional[str] = None) -> str:
    """
    View details of a GitHub Issue.

    Args:
        issue_number: Issue number
        repo_path: Path to the Git repository (optional)
    """
    logger.info(f"Viewing issue #{issue_number}")
    return run_command(["gh", "issue", "view", issue_number], cwd=repo_path)

@tool
def gh_issue_close(issue_number: str, repo_path: Optional[str] = None, comment: Optional[str] = None) -> str:
    """
    Close a GitHub Issue.

    Args:
        issue_number: Issue number
        repo_path: Path to the Git repository (optional)
        comment: Optional closing comment
    """
    logger.info(f"Closing issue #{issue_number}")
    cmd = ["gh", "issue", "close", issue_number]
    if comment:
        cmd.extend(["--comment", comment])
    return run_command(cmd, cwd=repo_path)

@tool
def gh_issue_comment(issue_number: str, body: str, repo_path: Optional[str] = None) -> str:
    """
    Add a comment to a GitHub Issue.

    Args:
        issue_number: Issue number
        body: Comment text
        repo_path: Path to the Git repository (optional)
    """
    logger.info(f"Adding comment to issue #{issue_number}")
    return run_command(
        ["gh", "issue", "comment", issue_number, "--body", body],
        cwd=repo_path
    )

# ============================================================================
# Release Operations
# ============================================================================

@tool
def gh_release_create(repo_path: str, tag: str, title: str, notes: str) -> str:
    """
    Create a GitHub Release.

    Args:
        repo_path: Path to the Git repository
        tag: Release tag name
        title: Release title
        notes: Release notes
    """
    logger.info(f"Creating release {tag} in {repo_path}")
    return run_command(
        ["gh", "release", "create", tag, "--title", title, "--notes", notes],
        cwd=repo_path
    )

@tool
def gh_release_list(repo_path: str, limit: int = 10) -> str:
    """
    List GitHub Releases.

    Args:
        repo_path: Path to the Git repository
        limit: Maximum number of releases to list (default: 10)
    """
    logger.info(f"Listing releases in {repo_path}")
    return run_command(
        ["gh", "release", "list", "--limit", str(limit)],
        cwd=repo_path
    )

@tool
def gh_release_view(tag: str, repo_path: Optional[str] = None) -> str:
    """
    View details of a GitHub Release.

    Args:
        tag: Release tag
        repo_path: Path to the Git repository (optional)
    """
    logger.info(f"Viewing release {tag}")
    return run_command(["gh", "release", "view", tag], cwd=repo_path)

# ============================================================================
# All Available Tools for the GitHub Agent
# ============================================================================

ALL_GITHUB_TOOLS = [
    # Authentication & Account
    gh_auth_switch,
    gh_auth_status,
    # Repository Operations
    gh_repo_clone,
    git_clone,
    gh_repo_fork,
    gh_repo_view,
    # Git Basic Operations
    git_status,
    git_pull,
    git_push,
    git_add,
    git_commit,
    git_branch_list,
    git_branch_create,
    git_checkout,
    git_log,
    # Pull Request Operations
    gh_pr_create,
    gh_pr_list,
    gh_pr_view,
    gh_pr_merge,
    gh_pr_comment,
    gh_pr_checkout,
    # Issue Operations
    gh_issue_create,
    gh_issue_list,
    gh_issue_view,
    gh_issue_close,
    gh_issue_comment,
    # Release Operations
    gh_release_create,
    gh_release_list,
    gh_release_view,
]

# ============================================================================
# GitHub Agent Implementation
# ============================================================================


class GitHubAgent(BaseCommandAgent):
    """LangGraph node that uses an LLM with comprehensive Git and GitHub tools."""

    def get_tools(self) -> List[BaseTool]:
        """Return list of available Git/GitHub tools."""
        return ALL_GITHUB_TOOLS

    def get_system_message(self) -> SystemMessage:
        """Return system message describing agent capabilities."""
        return SystemMessage(content=(
            "You are a comprehensive Git and GitHub automation assistant with access to the following capabilities:\n\n"
            "**IMPORTANT: Workspace Directory Convention**\n"
            f"- ALL repositories MUST be cloned to: {self.workspace_dir}\n"
            f"- When cloning repositories, use this absolute path format: {self.workspace_dir}/repo-name\n"
            "- This is a strict requirement for repository analysis workflows\n\n"
            "**Repository Management:**\n"
            "- Clone repositories (gh_repo_clone, git_clone)\n"
            "- Fork repositories (gh_repo_fork)\n"
            "- View repository information (gh_repo_view)\n\n"
            "**Git Operations:**\n"
            "- Check repository status (git_status)\n"
            "- Pull/push changes (git_pull, git_push)\n"
            "- Stage files and commit (git_add, git_commit)\n"
            "- Create and switch branches (git_branch_create, git_checkout)\n"
            "- View commit history (git_log)\n\n"
            "**Pull Requests:**\n"
            "- Create PRs (gh_pr_create)\n"
            "- List, view, and checkout PRs (gh_pr_list, gh_pr_view, gh_pr_checkout)\n"
            "- Merge PRs (gh_pr_merge)\n"
            "- Comment on PRs (gh_pr_comment)\n\n"
            "**Issues:**\n"
            "- Create and manage issues (gh_issue_create, gh_issue_close)\n"
            "- List and view issues (gh_issue_list, gh_issue_view)\n"
            "- Comment on issues (gh_issue_comment)\n\n"
            "**Releases:**\n"
            "- Create releases (gh_release_create)\n"
            "- List and view releases (gh_release_list, gh_release_view)\n\n"
            "**Authentication:**\n"
            "- Switch GitHub accounts (gh_auth_switch)\n"
            "- Check auth status (gh_auth_status)\n\n"
            "Use these tools to accomplish the requested Git/GitHub tasks efficiently."
        ))

    def get_default_prompt(self) -> str:
        """Return default prompt, potentially using repository information from state."""
        # Extract context from state
        repositories = self.state.get("products_config", {}).get("repositories", [])

        if repositories:
            repo_info = "\n".join([str(r) for r in repositories])
            prompt = (
                "Please ensure all repositories are cloned and up to date:\n\n"
                f"{repo_info}\n\n"
                "For each repository:\n"
                "1. If an 'account' is specified, switch to that account using gh_auth_switch\n"
                "2. Clone the repository if it doesn't exist (use gh_repo_clone or git_clone)\n"
                "3. If already cloned, pull the latest changes using git_pull"
            )
            self.agent_logger.info(f"Repository sync mode: {len(repositories)} repositories to process")
            return prompt
        else:
            # No repositories in state, agent is being used for custom tasks
            self.agent_logger.info("No repositories specified, ready for custom operations")
            return "Ready to assist with Git and GitHub operations."

    def get_user_prompt(self) -> str:
        """Override to add repository info to custom prompts if available."""
        if self.custom_prompt:
            # Custom prompt provided by the caller
            repositories = self.state.get("products_config", {}).get("repositories", [])
            user_prompt = self.custom_prompt
            if repositories:
                repo_info = "\n".join([str(r) for r in repositories])
                user_prompt += f"\n\nRepository Configuration:\n{repo_info}"
            self.agent_logger.info(f"Using custom prompt: {self.custom_prompt}")
            return user_prompt
        else:
            prompt = self.get_default_prompt()
            self.agent_logger.info("Using default prompt")
            return prompt


def github_agent(state: OverallState, config: Optional[RunnableConfig] = None) -> OverallState:
    """
    LangGraph node that uses an LLM with comprehensive Git and GitHub tools.

    This agent can handle various Git/GitHub operations including:
    - Repository cloning and management
    - Branch creation and switching
    - Commits and pushes
    - Pull Request creation, review, and merging
    - Issue management
    - Release management

    Can be configured via RunnableConfig:
        config = {
            "configurable": {
                "provider": "ollama",
                "model": "qwen3:8b",
                "prompt": "Your custom instructions...",
                "project_root": "/path/to/project",  # Optional: project root directory
                "max_iterations": 20,  # Optional: override default iteration limit
                "log_dir": "logs",  # Optional: directory for log files
                "verbose": False  # Optional: whether to print out LLM response text
            }
        }
    """
    agent = GitHubAgent("github_agent", state, config)
    return agent.run()