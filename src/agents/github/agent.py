"""GitHub operations agent (Claude Code implementation).

Delegates Git operations to the ``claude`` CLI using the ``github`` skill
defined in ``.claude/skills/github/SKILL.md``.

Example::

    from src.agents.github.agent import GitHubAgent

    agent = GitHubAgent()
    response = agent.run("Clone https://github.com/octocat/Hello-World into /tmp/hello")
    print(response)
"""

from __future__ import annotations

from src.agents.claude_base import ClaudeCodeBaseAgent


class GitHubAgent(ClaudeCodeBaseAgent):
    """Agent specialised for GitHub operations.

    Uses the ``github`` skill to clone repositories and checkout branches via
    the ``claude`` CLI.  The skill has access to ``Bash`` only (git commands).
    """

    name: str = "github"
    description: str = "Clone Git repositories and checkout branches locally."

    @property
    def skill_name(self) -> str:
        return "github"

    @property
    def claude_allowed_tools(self) -> list[str]:
        return ["Bash"]


if __name__ == "__main__":
    from src.agents.cli import run_agent_cli

    run_agent_cli(GitHubAgent)
