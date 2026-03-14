"""mise environment configuration agent (Claude Code implementation).

Delegates mise operations to the ``claude`` CLI using the ``mise`` skill
defined in ``.claude/skills/mise/SKILL.md``.

Example::

    from src.agents.mise.agent import MiseAgent

    agent = MiseAgent(project_path="./workspace/repos/my-project")
    response = agent.run("Search for available Node.js versions and use 20 in this project")
    print(response)
"""

from __future__ import annotations

from pathlib import Path

from src.agents.claude_base import ClaudeCodeBaseAgent


class MiseAgent(ClaudeCodeBaseAgent):
    """Agent specialised for mise environment configuration.

    Runs inside the project directory so that ``mise use`` commands pin versions
    to the correct ``mise.toml``.  The skill has access to ``Bash`` only.
    """

    name: str = "mise"
    description: str = "Search, list, trust, and configure tool versions via mise."

    def __init__(
        self,
        *,
        project_path: str,
        verbose: bool = False,
        session_id: str | None = None,
    ) -> None:
        super().__init__(verbose=verbose, session_id=session_id)
        self.project_path = str(Path(project_path).resolve())

    @property
    def skill_name(self) -> str:
        return "mise"

    @property
    def claude_allowed_tools(self) -> list[str]:
        return ["Bash"]

    def _get_cwd(self) -> str:
        return self.project_path


if __name__ == "__main__":
    from src.agents.cli import run_agent_cli

    def _add_arguments(parser):
        parser.add_argument(
            "--project-path",
            required=True,
            metavar="PATH",
            help="Path to the project directory for mise commands.",
        )

    def _build_kwargs(args):
        return {"project_path": args.project_path}

    run_agent_cli(MiseAgent, add_arguments=_add_arguments, build_kwargs=_build_kwargs)
