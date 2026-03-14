"""Claude Code task delegation agent (Claude Code implementation).

Delegates coding and file-system tasks to the ``claude`` CLI using the
``claudecode`` skill defined in ``.claude/skills/claudecode/SKILL.md``.

Example::

    from src.agents.claudecode.agent import ClaudeCodeAgent

    agent = ClaudeCodeAgent(cwd="/path/to/project")
    response = agent.run("Add type hints to all functions in src/utils.py")
    print(response)
"""

from __future__ import annotations

from pathlib import Path

from src.agents.claude_base import ClaudeCodeBaseAgent


class ClaudeCodeAgent(ClaudeCodeBaseAgent):
    """General-purpose coding agent that delegates tasks to the ``claude`` CLI.

    One instance targets one working directory.  All file operations and shell
    commands run inside ``cwd``.

    Args:
        cwd:           Working directory for Claude Code file operations.
                       Defaults to the current directory.
        allowed_tools: Built-in Claude Code tools to enable.
                       Defaults to a safe read/write/execute set.
        max_turns:     Maximum agent turns; ``None`` uses the CLI default.
        verbose:       Enable verbose LangGraph logging.
        session_id:    Optional session ID for Langfuse tracing.
    """

    name: str = "claudecode"
    description: str = (
        "Delegate coding and file-system tasks to Claude Code (Anthropic CLI)."
    )

    def __init__(
        self,
        *,
        cwd: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int | None = None,
        verbose: bool = False,
        session_id: str | None = None,
    ) -> None:
        super().__init__(verbose=verbose, session_id=session_id)
        self._cwd = str(Path(cwd).resolve()) if cwd else str(Path.cwd())
        self._allowed_tools = allowed_tools or [
            "Read",
            "Write",
            "Edit",
            "Bash",
            "Glob",
            "Grep",
        ]
        self._max_turns = max_turns

    @property
    def skill_name(self) -> str:
        return "claudecode"

    @property
    def claude_allowed_tools(self) -> list[str]:
        return self._allowed_tools

    @property
    def claude_max_turns(self) -> int | None:
        return self._max_turns

    def _get_cwd(self) -> str:
        return self._cwd


if __name__ == "__main__":
    from src.agents.cli import run_agent_cli

    def _add_arguments(parser):
        parser.add_argument(
            "--cwd",
            default=None,
            metavar="PATH",
            help="Working directory for Claude Code (defaults to current directory).",
        )
        parser.add_argument(
            "--max-turns",
            type=int,
            default=None,
            metavar="N",
            help="Maximum Claude Code agent turns per invocation (default: CLI default).",
        )

    def _build_kwargs(args):
        return {
            "cwd": args.cwd,
            "max_turns": args.max_turns,
        }

    run_agent_cli(
        ClaudeCodeAgent,
        add_arguments=_add_arguments,
        build_kwargs=_build_kwargs,
    )
