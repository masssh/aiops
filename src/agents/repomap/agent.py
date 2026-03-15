"""RepoMap agent (Claude Code implementation).

Delegates repository mapping to the ``claude`` CLI using the ``repomap`` skill
defined in ``.claude/skills/repomap/SKILL.md``.

Example::

    from src.agents.repomap.agent import RepomapAgent

    agent = RepomapAgent(project_path="./workspace/repos/my-project")
    result = agent.run("Map this repository")
    print(result)
"""

from __future__ import annotations

from pathlib import Path

from src.agents.claude_base import ClaudeCodeBaseAgent


class RepomapAgent(ClaudeCodeBaseAgent):
    """Repository map agent.

    Generates a token-optimised repository map showing directory structure and
    top-level symbols for the most important files.  The map is written to
    ``agent_output/repos/{repo_name}/repomap.txt``.

    Args:
        project_path: Path to the repository directory to analyse.
        verbose:      Enable verbose LangGraph logging.
        session_id:   Optional session ID for Langfuse tracing.
    """

    name: str = "repomap"
    description: str = (
        "Generate a token-optimised repository map showing directory structure "
        "and top-level symbols for the most important files."
    )

    def __init__(
        self,
        *,
        project_path: str,
        verbose: bool = False,
        session_id: str | None = None,
    ) -> None:
        super().__init__(verbose=verbose, session_id=session_id)
        self.project_path = str(Path(project_path).resolve())
        self.repo_name: str = Path(project_path).name

    @property
    def skill_name(self) -> str:
        return "repomap"

    @property
    def claude_allowed_tools(self) -> list[str]:
        return ["Bash", "Read", "Glob", "Grep", "Write"]

    def _get_cwd(self) -> str:
        return self.project_path

    def _build_task_prompt(self, task: str) -> str:
        from src.core.project import get_project_config

        cfg = get_project_config()
        output_dir = cfg.repo_output_dir(self.repo_name)
        return (
            f"project_path={self.project_path}\n"
            f"repo_name={self.repo_name}\n"
            f"output_dir={output_dir}\n\n"
            f"{task}"
        )


if __name__ == "__main__":
    from src.agents.cli import run_agent_cli
    from typing import Any

    def _add_arguments(parser: Any) -> None:
        parser.add_argument(
            "--project-path",
            required=True,
            metavar="PATH",
            help="Path to the repository directory to map.",
        )

    def _build_kwargs(args: Any) -> dict[str, Any]:
        return {"project_path": args.project_path}

    run_agent_cli(RepomapAgent, add_arguments=_add_arguments, build_kwargs=_build_kwargs)
