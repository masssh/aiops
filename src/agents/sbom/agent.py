"""SBOM analysis agent (Claude Code implementation).

Delegates SBOM operations to the ``claude`` CLI using the ``sbom`` skill
defined in ``.claude/skills/sbom/SKILL.md``.

Example::

    from src.agents.sbom.agent import SBOMAgent

    agent = SBOMAgent(project_path="./workspace/repos/my-project")
    response = agent.run("Generate the SBOM and list all components")
    print(response)
"""

from __future__ import annotations

from pathlib import Path

from src.agents.claude_base import ClaudeCodeBaseAgent


class SBOMAgent(ClaudeCodeBaseAgent):
    """Agent specialised for SBOM generation and analysis via cdxgen.

    Passes the project path, repo name, and output directory as context so
    the skill knows where to write artefacts.  The skill has access to
    ``Bash`` (for cdxgen), ``Read`` (to inspect SBOM JSON), and ``Glob``.
    """

    name: str = "sbom"
    description: str = (
        "Generate and analyse Software Bill of Materials (SBOM) for a repository using cdxgen."
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
        return "sbom"

    @property
    def claude_allowed_tools(self) -> list[str]:
        return ["Bash", "Read", "Glob"]

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

    def _add_arguments(parser):
        parser.add_argument(
            "--project-path",
            required=True,
            metavar="PATH",
            help="Path to the repository directory to analyse.",
        )

    def _build_kwargs(args):
        return {"project_path": args.project_path}

    run_agent_cli(SBOMAgent, add_arguments=_add_arguments, build_kwargs=_build_kwargs)
