"""Tools for delegating tasks to Claude Code via the Agent SDK."""

from __future__ import annotations

from typing import Annotated

from langchain_core.tools import tool


def create_claudecode_tools(
    *,
    cwd: str,
    allowed_tools: list[str] | None = None,
    permission_mode: str = "default",
    max_turns: int | None = None,
) -> list:
    """Create a list of LangChain tools that delegate work to Claude Code.

    Args:
        cwd:              Working directory for Claude Code file operations.
        allowed_tools:    Built-in Claude Code tools to enable (e.g. ``["Read", "Edit", "Bash"]``).
                          Defaults to a safe read/write set.
        permission_mode:  How Claude Code handles permission prompts.
                          ``"default"`` prompts for destructive ops;
                          ``"acceptEdits"`` auto-accepts file edits;
                          ``"dontAsk"`` suppresses all prompts.
        max_turns:        Maximum agent turns before stopping; ``None`` means unlimited.
    """
    _allowed_tools = allowed_tools or [
        "Read",
        "Write",
        "Edit",
        "Bash",
        "Glob",
        "Grep",
    ]

    @tool
    async def delegate_to_claude_code(
        task: Annotated[str, "Complete task description to execute via Claude Code"],
    ) -> str:
        """Delegate a coding task to Claude Code and return its output.

        Claude Code is an AI coding assistant with access to the local filesystem.
        It can read and write files, run shell commands, search code, and make
        precise edits. Use this tool to perform any coding, analysis, or file
        manipulation tasks on the project.
        """
        from claude_agent_sdk import (  # type: ignore[import-untyped]
            CLIConnectionError,
            CLINotFoundError,
            ClaudeAgentOptions,
            ResultMessage,
            query,
        )

        options = ClaudeAgentOptions(
            cwd=cwd,
            allowed_tools=_allowed_tools,
            permission_mode=permission_mode,
        )
        if max_turns is not None:
            options.max_turns = max_turns

        results: list[str] = []
        try:
            async for message in query(prompt=task, options=options):
                if isinstance(message, ResultMessage):
                    results.append(message.result)
        except CLINotFoundError:
            return (
                "Error: Claude Code CLI not found. "
                "Install it with: npm install -g @anthropic-ai/claude-code"
            )
        except CLIConnectionError as exc:
            return f"Error: Could not connect to Claude Code CLI: {exc}"

        return "\n".join(results) if results else "Task completed with no textual output."

    return [delegate_to_claude_code]
