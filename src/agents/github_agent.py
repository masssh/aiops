import subprocess
import os
import logging
from typing import Optional
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from src.models.state import OverallState
from src.utils.llm import get_llm, Provider
from src.utils.logging import setup_agent_logger

logger = logging.getLogger(__name__)

class GitHubAgentLogic:
    """Execution logic for Git and GitHub operations using git and gh CLI."""

    def _run_command(self, cmd: list[str], cwd: Optional[str] = None) -> str:
        """Execute a shell command and return the output or error message."""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, check=True)
            return result.stdout.strip() if result.stdout.strip() else "Command executed successfully."
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr.strip() else str(e)
            return f"Error: {error_msg}"

github_agent_logic = GitHubAgentLogic()

# ============================================================================
# Authentication & Account Management
# ============================================================================

@tool
def gh_auth_switch(account: str) -> str:
    """Switch gh CLI authentication to the specified GitHub account."""
    logger.info(f"Switching GitHub account to: {account}")
    return github_agent_logic._run_command(["gh", "auth", "switch", "--user", account])

@tool
def gh_auth_status() -> str:
    """Check the current GitHub authentication status."""
    logger.info("Checking GitHub authentication status")
    return github_agent_logic._run_command(["gh", "auth", "status"])

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
    return github_agent_logic._run_command(["gh", "repo", "clone", repo_id, full_path])

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
    return github_agent_logic._run_command(["git", "clone", url, full_path])

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
    return github_agent_logic._run_command(cmd)

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
    return github_agent_logic._run_command(cmd, cwd=cwd)

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
    return github_agent_logic._run_command(["git", "status"], cwd=repo_path)

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
    return github_agent_logic._run_command(cmd, cwd=repo_path)

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
    return github_agent_logic._run_command(cmd, cwd=repo_path)

@tool
def git_add(repo_path: str, files: str = ".") -> str:
    """
    Add files to the staging area.

    Args:
        repo_path: Path to the Git repository
        files: Files or patterns to add (default: "." for all)
    """
    logger.info(f"Adding files: {files} in {repo_path}")
    return github_agent_logic._run_command(["git", "add", files], cwd=repo_path)

@tool
def git_commit(repo_path: str, message: str) -> str:
    """
    Create a Git commit with the staged changes.

    Args:
        repo_path: Path to the Git repository
        message: Commit message
    """
    logger.info(f"Creating commit in {repo_path}")
    return github_agent_logic._run_command(["git", "commit", "-m", message], cwd=repo_path)

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
    return github_agent_logic._run_command(cmd, cwd=repo_path)

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
    result = github_agent_logic._run_command(cmd, cwd=repo_path)

    if checkout and "Error" not in result:
        checkout_cmd = ["git", "checkout", branch_name]
        checkout_result = github_agent_logic._run_command(checkout_cmd, cwd=repo_path)
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
    return github_agent_logic._run_command(["git", "checkout", branch_name], cwd=repo_path)

@tool
def git_log(repo_path: str, max_count: int = 10) -> str:
    """
    Show Git commit history.

    Args:
        repo_path: Path to the Git repository
        max_count: Maximum number of commits to show (default: 10)
    """
    logger.info(f"Getting git log in {repo_path}")
    return github_agent_logic._run_command(
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
    return github_agent_logic._run_command(cmd, cwd=repo_path)

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
    return github_agent_logic._run_command(
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
    return github_agent_logic._run_command(["gh", "pr", "view", pr_number], cwd=repo_path)

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
    return github_agent_logic._run_command(
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
    return github_agent_logic._run_command(
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
    return github_agent_logic._run_command(["gh", "pr", "checkout", pr_number], cwd=repo_path)

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
    return github_agent_logic._run_command(
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
    return github_agent_logic._run_command(
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
    return github_agent_logic._run_command(["gh", "issue", "view", issue_number], cwd=repo_path)

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
    return github_agent_logic._run_command(cmd, cwd=repo_path)

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
    return github_agent_logic._run_command(
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
    return github_agent_logic._run_command(
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
    return github_agent_logic._run_command(
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
    return github_agent_logic._run_command(["gh", "release", "view", tag], cwd=repo_path)

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

from langchain_core.runnables import RunnableConfig

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
                "github_agent_prompt": "Your custom instructions...",
                "project_root": "/path/to/project",  # Optional: project root directory
                "max_iterations": 20,  # Optional: override default iteration limit
                "log_dir": "logs",  # Optional: directory for log files
                "verbose": False  # Optional: whether to print out LLM response text
            }
        }
    """
    # Get configuration
    configurable = config.get("configurable", {}) if config else {}
    custom_prompt = configurable.get("github_agent_prompt")
    provider: Provider = configurable.get("provider", "ollama")
    model: str | None = configurable.get("model", None)
    project_root: str = configurable.get("project_root", os.getcwd())
    max_iterations: int = configurable.get("max_iterations", 20)
    log_dir: str = configurable.get("log_dir", "logs")
    verbose: bool = configurable.get("verbose", False)

    # Set up dedicated logger for this agent execution
    agent_logger = setup_agent_logger("github_agent", log_dir)

    # Calculate workspace directory absolute path
    workspace_dir = os.path.abspath(os.path.join(project_root, "workspace"))

    agent_logger.info("="*80)
    agent_logger.info("GitHub Agent started")
    agent_logger.info(f"Provider: {provider}, Model: {model}")
    agent_logger.info(f"Verbose: {verbose}")
    agent_logger.info(f"Project root: {project_root}")
    agent_logger.info(f"Workspace directory: {workspace_dir}")
    agent_logger.info(f"Max iterations: {max_iterations}")
    agent_logger.info("="*80)

    # Initialize LLM with all Git/GitHub tools
    llm = get_llm(provider=provider, model=model, verbose=verbose)
    llm_with_tools = llm.bind_tools(ALL_GITHUB_TOOLS)

    # Extract context from state
    repositories = state.get("products_config", {}).get("repositories", [])

    # System message defining the agent's capabilities
    system_msg = SystemMessage(content=(
        "You are a comprehensive Git and GitHub automation assistant with access to the following capabilities:\n\n"
        "**IMPORTANT: Workspace Directory Convention**\n"
        f"- ALL repositories MUST be cloned to: {workspace_dir}\n"
        f"- When cloning repositories, use this absolute path format: {workspace_dir}/repo-name\n"
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

    # Build user prompt
    if custom_prompt:
        # Custom prompt provided by the caller
        user_prompt = custom_prompt
        if repositories:
            repo_info = "\n".join([str(r) for r in repositories])
            user_prompt += f"\n\nRepository Configuration:\n{repo_info}"
        agent_logger.info(f"Using custom prompt: {custom_prompt[:100]}...")
    else:
        # Default behavior: repository sync
        if repositories:
            repo_info = "\n".join([str(r) for r in repositories])
            user_prompt = (
                "Please ensure all repositories are cloned and up to date:\n\n"
                f"{repo_info}\n\n"
                "For each repository:\n"
                "1. If an 'account' is specified, switch to that account using gh_auth_switch\n"
                "2. Clone the repository if it doesn't exist (use gh_repo_clone or git_clone)\n"
                "3. If already cloned, pull the latest changes using git_pull"
            )
            agent_logger.info(f"Repository sync mode: {len(repositories)} repositories to process")
        else:
            # No repositories in state, agent is being used for custom tasks
            user_prompt = "Ready to assist with Git and GitHub operations."
            agent_logger.info("No repositories specified, ready for custom operations")

    agent_logger.debug(f"Full user prompt:\n{user_prompt}")
    messages = [system_msg, HumanMessage(content=user_prompt)]

    # Tool execution loop
    for iteration in range(max_iterations):
        agent_logger.info(f"\n{'='*80}")
        agent_logger.info(f"Iteration {iteration + 1}/{max_iterations}")
        agent_logger.info(f"{'='*80}")

        # Invoke LLM to decide next action
        agent_logger.debug("Invoking LLM to determine next action...")
        ai_msg = llm_with_tools.invoke(messages)
        messages.append(ai_msg)

        # Log LLM's response content (if any)
        if hasattr(ai_msg, 'content') and ai_msg.content:
            agent_logger.debug(f"LLM response content: {ai_msg.content}")

        if not ai_msg.tool_calls:
            # LLM decided it's done
            agent_logger.info("LLM has completed its task (no more tool calls)")
            if hasattr(ai_msg, 'content') and ai_msg.content:
                agent_logger.info(f"Final message: {ai_msg.content}")
            logger.info(f"GitHub agent completed after {iteration + 1} iterations")
            break

        # Log LLM's decision
        agent_logger.info(f"LLM decided to execute {len(ai_msg.tool_calls)} tool(s):")
        for idx, tool_call in enumerate(ai_msg.tool_calls, 1):
            agent_logger.info(f"  {idx}. {tool_call['name']}")

        # Execute all tool calls from this iteration
        for tool_call in ai_msg.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]

            agent_logger.info(f"\n--- Executing tool: {tool_name} ---")
            agent_logger.debug(f"Tool arguments: {tool_args}")

            # Find and invoke the appropriate tool
            tool_function = None
            for tool in ALL_GITHUB_TOOLS:
                if tool.name == tool_name:
                    tool_function = tool
                    break

            if tool_function:
                try:
                    agent_logger.debug(f"Invoking {tool_name}...")
                    result = tool_function.invoke(tool_args)
                    agent_logger.info(f"Tool execution successful")
                    agent_logger.debug(f"Tool result: {result}")
                except Exception as e:
                    result = f"Error executing {tool_name}: {str(e)}"
                    agent_logger.error(f"Tool execution failed: {str(e)}")
                    logger.error(result)
            else:
                result = f"Error: Tool '{tool_name}' not found in available tools."
                agent_logger.error(result)
                logger.error(result)

            messages.append(ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"]
            ))

    agent_logger.info("\n" + "="*80)
    agent_logger.info("GitHub Agent execution completed")
    agent_logger.info("="*80)

    return state