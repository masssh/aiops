"""Repository analysis agent (Claude Code implementation).

Delegates static code analysis to the ``claude`` CLI using the
``repository_analyzer`` skill defined in
``.claude/skills/repository_analyzer/SKILL.md``.

Serena (https://github.com/oraios/serena) is configured as an MCP server and
passed to claude via ``--mcp-config``, giving the skill access to LSP-backed
symbol search, reference finding, and structural exploration tools.

Example::

    from src.agents.repository_analyzer.agent import RepositoryAnalyzerAgent

    agent = RepositoryAnalyzerAgent(project_path="./workspace/repos/my-project")
    response = agent.run("Find all classes that implement the UserRepository interface")
    print(response)
"""

from __future__ import annotations

from pathlib import Path

from src.agents.claude_base import ClaudeCodeBaseAgent


class RepositoryAnalyzerAgent(ClaudeCodeBaseAgent):
    """Agent for static code analysis of a single repository using Serena MCP.

    Operates in READ-ONLY mode; write-capable Serena tools are excluded from
    the allowed-tools list.  The Serena MCP server is started by the claude
    subprocess and torn down automatically when the invocation ends.

    Args:
        project_path: Path to the repository directory to analyse.
        verbose:      Enable verbose LangGraph logging.
        session_id:   Optional session ID for Langfuse tracing.
    """

    name: str = "repository_analyzer"
    description: str = (
        "Perform static code analysis on a repository using Serena MCP (LSP-backed)."
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

    @property
    def skill_name(self) -> str:
        return "repository_analyzer"

    @property
    def claude_allowed_tools(self) -> list[str]:
        # Read-only tools + mcp__serena__* tools are granted via MCP config.
        # Bash and Read are included for fallback exploration.
        return ["Bash", "Read", "Glob", "Grep", "mcp__serena__*"]

    def _get_cwd(self) -> str:
        return self.project_path

    def _build_task_prompt(self, task: str) -> str:
        return f"project_path={self.project_path}\n\n{task}"

    def _get_mcp_config(self) -> dict | None:
        return {
            "mcpServers": {
                "serena": {
                    "command": "uvx",
                    "args": [
                        "--from",
                        "git+https://github.com/oraios/serena",
                        "serena",
                        "start-mcp-server",
                        "--project",
                        self.project_path,
                        "--context",
                        "desktop-app",
                        "--open-web-dashboard",
                        "false",
                        "--log-level",
                        "WARNING",
                    ],
                    "transport": "stdio",
                }
            }
        }


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

    run_agent_cli(
        RepositoryAnalyzerAgent, add_arguments=_add_arguments, build_kwargs=_build_kwargs
    )
