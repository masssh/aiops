"""SCIP code intelligence agent (Claude Code implementation).

Delegates SCIP indexing and graph analysis to the ``claude`` CLI using the
``scip`` skill defined in ``.claude/skills/scip/SKILL.md``.

Workflow
========
1. Generate SCIP index for the project
2. Load it into Neo4j
3. Detect code communities via Louvain algorithm
4. Extract entrypoints and summarise the public API surface

Prerequisites
=============
- A SCIP indexer for the target language (scip-python, scip-typescript, scip-java)
- Neo4j running (see docker-compose.yml)
- NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD in .env

Example::

    from src.agents.scip.agent import ScipAgent

    agent = ScipAgent(project_path="./workspace/repos/my-project")
    result = agent.run("Index this project and find code communities")
    print(result)
"""

from __future__ import annotations

from pathlib import Path

from src.agents.claude_base import ClaudeCodeBaseAgent


class ScipAgent(ClaudeCodeBaseAgent):
    """SCIP code intelligence agent.

    Indexes a repository using language-specific SCIP indexers, stores the
    resulting symbol graph in Neo4j, and applies community-detection algorithms
    to identify logical code clusters.

    Args:
        project_path: Path to the repository directory to index.
        verbose:      Enable verbose LangGraph logging.
        session_id:   Optional session ID for Langfuse tracing.
    """

    name: str = "scip"
    description: str = (
        "Generate SCIP code-intelligence indexes, store them in Neo4j, "
        "and detect logical code communities using graph analysis."
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
        return "scip"

    @property
    def claude_allowed_tools(self) -> list[str]:
        return ["Bash", "Read"]

    def _get_cwd(self) -> str:
        return self.project_path

    def _build_task_prompt(self, task: str) -> str:
        return (
            f"project_path={self.project_path}\n"
            f"repo_name={self.repo_name}\n\n"
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
            help="Path to the repository directory to index.",
        )

    def _build_kwargs(args: Any) -> dict[str, Any]:
        return {"project_path": args.project_path}

    run_agent_cli(ScipAgent, add_arguments=_add_arguments, build_kwargs=_build_kwargs)
