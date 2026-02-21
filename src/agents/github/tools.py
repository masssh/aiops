"""GitHub tools for use with the GitHubAgent.

Each tool is decorated with ``@tool`` so it can be bound directly to a
LangChain/LangGraph ReAct agent.

All operations are delegated to the ``gh`` CLI, which must be installed and
authenticated in advance::

    gh auth login

No API tokens need to be stored in ``.env``; authentication is managed
entirely by the ``gh`` credential store.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
from typing import Annotated

from langchain_core.tools import tool

from src.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _require_gh() -> str:
    """Return the absolute path to the ``gh`` binary, or raise."""
    path = shutil.which("gh")
    if not path:
        raise RuntimeError(
            "'gh' command not found. Install GitHub CLI: https://cli.github.com"
        )
    return path


def _run_gh(*args: str, input_text: str | None = None) -> str:
    """Run ``gh <args>`` and return stdout as a string.

    Args:
        *args:       Arguments forwarded to ``gh`` (do NOT include the binary itself).
        input_text:  Optional text piped to stdin (e.g. for ``--input -``).

    Returns:
        Decoded stdout string.

    Raises:
        RuntimeError: If the command exits with a non-zero status.
    """
    gh = _require_gh()
    cmd = [gh, *args]
    logger.debug("gh {}", " ".join(args))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        input=input_text,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"gh command failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


def _gh_json(*args: str, input_text: str | None = None) -> object:
    """Run ``gh`` and parse the JSON output."""
    raw = _run_gh(*args, input_text=input_text)
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def get_repository(
    owner_repo: Annotated[str, "Repository in 'owner/repo' format, e.g. 'octocat/Hello-World'"],
) -> str:
    """Get metadata for a GitHub repository (description, stars, language, etc.)."""
    logger.debug("get_repository: {}", owner_repo)
    data = _gh_json(
        "repo", "view", owner_repo,
        "--json", "name,nameWithOwner,description,primaryLanguage,stargazerCount,"
                  "forkCount,openIssues,defaultBranchRef,url",
    )
    assert isinstance(data, dict)
    lang = (data.get("primaryLanguage") or {}).get("name", "unknown")
    branch = (data.get("defaultBranchRef") or {}).get("name", "unknown")
    open_issues = (data.get("openIssues") or {}).get("totalCount", "?")
    return (
        f"Repository: {data.get('nameWithOwner')}\n"
        f"Description: {data.get('description')}\n"
        f"Language: {lang}\n"
        f"Stars: {data.get('stargazerCount')}\n"
        f"Forks: {data.get('forkCount')}\n"
        f"Open Issues: {open_issues}\n"
        f"Default Branch: {branch}\n"
        f"URL: {data.get('url')}"
    )


@tool
def list_issues(
    owner_repo: Annotated[str, "Repository in 'owner/repo' format"],
    state: Annotated[str, "Issue state: 'open', 'closed', or 'all'"] = "open",
    limit: Annotated[int, "Maximum number of issues to return (1-50)"] = 10,
) -> str:
    """List issues in a GitHub repository."""
    logger.debug("list_issues: {} state={} limit={}", owner_repo, state, limit)
    data = _gh_json(
        "issue", "list",
        "--repo", owner_repo,
        "--state", state,
        "--limit", str(limit),
        "--json", "number,title,state,labels,url",
    )
    assert isinstance(data, list)
    if not data:
        return f"No {state} issues found in {owner_repo}."
    lines = [f"Issues ({state}) in {owner_repo}:"]
    for issue in data:
        label_names = ", ".join(l["name"] for l in issue.get("labels", [])) or "none"
        lines.append(
            f"  #{issue['number']} [{issue['state']}] {issue['title']} "
            f"(labels: {label_names})"
        )
    return "\n".join(lines)


@tool
def create_issue(
    owner_repo: Annotated[str, "Repository in 'owner/repo' format"],
    title: Annotated[str, "Issue title"],
    body: Annotated[str, "Issue body / description in markdown"] = "",
    labels: Annotated[str, "Comma-separated label names to apply (optional)"] = "",
) -> str:
    """Create a new issue in a GitHub repository."""
    logger.debug("create_issue: {} title={!r}", owner_repo, title)
    args = [
        "issue", "create",
        "--repo", owner_repo,
        "--title", title,
        "--body", body,
    ]
    for label in (l.strip() for l in labels.split(",") if l.strip()):
        args += ["--label", label]
    url = _run_gh(*args).strip()
    return f"Issue created: {url}"


@tool
def list_pull_requests(
    owner_repo: Annotated[str, "Repository in 'owner/repo' format"],
    state: Annotated[str, "PR state: 'open', 'closed', or 'merged'"] = "open",
    limit: Annotated[int, "Maximum number of PRs to return (1-50)"] = 10,
) -> str:
    """List pull requests in a GitHub repository."""
    logger.debug("list_pull_requests: {} state={} limit={}", owner_repo, state, limit)
    data = _gh_json(
        "pr", "list",
        "--repo", owner_repo,
        "--state", state,
        "--limit", str(limit),
        "--json", "number,title,state,author,baseRefName,url",
    )
    assert isinstance(data, list)
    if not data:
        return f"No {state} pull requests found in {owner_repo}."
    lines = [f"Pull Requests ({state}) in {owner_repo}:"]
    for pr in data:
        author = (pr.get("author") or {}).get("login", "?")
        lines.append(
            f"  #{pr['number']} [{pr['state']}] {pr['title']} "
            f"({author}) → {pr['baseRefName']}"
        )
    return "\n".join(lines)


@tool
def search_issues(
    query: Annotated[
        str,
        "GitHub search query string, e.g. 'repo:owner/repo is:issue label:bug'. "
        "Supports full GitHub search syntax.",
    ],
    limit: Annotated[int, "Maximum number of results (1-30)"] = 10,
) -> str:
    """Search GitHub issues and pull requests using GitHub's search API."""
    logger.debug("search_issues: query={!r} limit={}", query, limit)
    data = _gh_json(
        "search", "issues", query,
        "--limit", str(limit),
        "--json", "number,title,state,repository,isPullRequest,url",
    )
    assert isinstance(data, list)
    if not data:
        return f"No results found for: {query!r}"
    lines = [f"Search results for {query!r}:"]
    for item in data:
        kind = "PR" if item.get("isPullRequest") else "Issue"
        repo_name = (item.get("repository") or {}).get("nameWithOwner", "?")
        lines.append(
            f"  [{kind}] {repo_name}#{item['number']} "
            f"[{item['state']}] {item['title']}"
        )
    return "\n".join(lines)


@tool
def get_file_content(
    owner_repo: Annotated[str, "Repository in 'owner/repo' format"],
    path: Annotated[str, "File path within the repository, e.g. 'README.md'"],
    ref: Annotated[str, "Branch, tag, or commit SHA (defaults to default branch)"] = "",
) -> str:
    """Get the text content of a file from a GitHub repository."""
    logger.debug("get_file_content: {}/{} ref={!r}", owner_repo, path, ref)
    endpoint = f"repos/{owner_repo}/contents/{path}"
    if ref:
        endpoint += f"?ref={ref}"
    data = _gh_json("api", endpoint)
    assert isinstance(data, (dict, list))
    # Directory listing
    if isinstance(data, list):
        names = [entry["name"] for entry in data]
        return f"'{path}' is a directory. Contents: {', '.join(names)}"
    if data.get("encoding") == "base64":
        raw = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    else:
        raw = data.get("content", "")
    if len(raw) > 8000:
        raw = raw[:8000] + "\n... (truncated)"
    return f"File: {owner_repo}/{path}\n\n{raw}"


@tool
def list_repositories(
    owner: Annotated[str, "GitHub username or organisation name"],
    limit: Annotated[int, "Maximum number of repos to return (1-30)"] = 10,
) -> str:
    """List repositories for a GitHub user or organisation."""
    logger.debug("list_repositories: owner={} limit={}", owner, limit)
    data = _gh_json(
        "repo", "list", owner,
        "--limit", str(limit),
        "--json", "nameWithOwner,description,stargazerCount,primaryLanguage,url",
    )
    assert isinstance(data, list)
    if not data:
        return f"No repositories found for {owner}."
    lines = [f"Repositories for {owner}:"]
    for repo in data:
        lang = (repo.get("primaryLanguage") or {}).get("name", "unknown")
        lines.append(
            f"  {repo['nameWithOwner']} ⭐{repo['stargazerCount']} "
            f"[{lang}] {repo.get('description') or ''}"
        )
    return "\n".join(lines)


# Exported list for easy import in agent.py
GITHUB_TOOLS = [
    get_repository,
    list_issues,
    create_issue,
    list_pull_requests,
    search_issues,
    get_file_content,
    list_repositories,
]
