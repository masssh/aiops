"""Tools for delegating tasks to the Claude Code CLI (claude --print)."""

from __future__ import annotations

from typing import Annotated

from langchain_core.tools import tool

from src.core.process import run_command


def create_claudecode_tools(
    *,
    cwd: str,
    allowed_tools: list[str] | None = None,
    max_turns: int | None = None,
) -> list:
    """Create a LangChain tool that delegates work to the ``claude`` CLI.

    Args:
        cwd:           Working directory for Claude Code file operations.
        allowed_tools: Built-in Claude Code tools to enable
                       (e.g. ``["Read", "Edit", "Bash"]``).
                       Defaults to a safe read/write set.
        max_turns:     Maximum agent turns before stopping; ``None`` means
                       the CLI default.
    """
    _allowed_tools: list[str] = allowed_tools or [
        "Read",
        "Write",
        "Edit",
        "Bash",
        "Glob",
        "Grep",
    ]

    @tool
    def delegate_to_claude_code(
        task: Annotated[str, "Complete task description to execute via Claude Code"],
    ) -> str:
        """Delegate a coding task to Claude Code and return its output.

        Claude Code is an AI coding assistant with access to the local filesystem.
        It can read and write files, run shell commands, search code, and make
        precise edits. Use this tool to perform any coding, analysis, or file
        manipulation tasks on the project.
        """
        args: list[str] = [
            "--print",
            "--allowedTools", ",".join(_allowed_tools),
            task,
        ]
        if max_turns is not None:
            args = ["--max-turns", str(max_turns)] + args

        try:
            return run_command("claude", *args, cwd=cwd)
        except RuntimeError as exc:
            return f"Error running Claude Code: {exc}"

    return [delegate_to_claude_code]
