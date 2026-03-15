"""Base class for agents that delegate all work to the Claude Code CLI.

Every concrete agent should subclass ``ClaudeCodeBaseAgent`` and implement:
- ``skill_name`` (property) – name matching the skill directory under
  ``.claude/skills/<name>/SKILL.md``
- ``claude_allowed_tools`` (property, optional) – list of Claude Code
  built-in tools the agent may use
- ``_get_cwd()`` (method, optional) – working directory for the claude
  subprocess; defaults to the project root

Optionally override:
- ``claude_max_turns`` – cap on agent reasoning steps (default: CLI default)
- ``_build_task_prompt(task)`` – augment the user task with extra context
  (e.g. project path, output directory) before handing it to the skill
- ``_get_mcp_config()`` – return an MCP server config dict to enable MCP
  tools (written to a temp file and passed via ``--mcp-config``)
"""

from __future__ import annotations

import abc
import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from src.agents.base import BaseAgent
from src.core.logging import get_logger
from src.core.process import run_command

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = get_logger(__name__)

# Resolved once at import time so every subclass shares the same value.
_PROJECT_ROOT: Path = Path(__file__).parent.parent.parent.resolve()

# Environment variables that cause the claude subprocess to think it is running
# inside a parent Claude Code session.  Unsetting them prevents interference
# with the parent process.
_UNSET_ENV: dict[str, str | None] = {
    "CLAUDECODE": None,
    "CLAUDE_CODE_ENTRYPOINT": None,
    "CLAUDE_AGENT_SDK_VERSION": None,
    "CLAUDE_CODE_ENABLE_ASK_USER_QUESTION_TOOL": None,
    "CLAUDE_CODE_EMIT_TOOL_USE_SUMMARIES": None,
    "CLAUDE_CODE_DISABLE_CRON": None,
}


class ClaudeCodeBaseAgent(BaseAgent, abc.ABC):
    """Base class for agents that execute tasks via the ``claude`` CLI.

    The LangGraph ``MessagesState`` graph built by ``_build_graph()`` is a
    single-node graph: it invokes the claude skill and returns the result as
    an ``AIMessage``.  All agent-specific reasoning happens inside claude,
    guided by the skill's SKILL.md instructions and the allowed-tools list.

    Subclasses must implement ``skill_name``.  Agents that need a specific
    working directory (e.g. a cloned repository) should override
    ``_get_cwd()``; agents that need extra context in the prompt should
    override ``_build_task_prompt()``.
    """

    # ------------------------------------------------------------------
    # Abstract / overridable configuration
    # ------------------------------------------------------------------

    @property
    @abc.abstractmethod
    def skill_name(self) -> str:
        """Skill name, matching the directory under ``.claude/skills/<name>/``."""
        ...

    @property
    def claude_allowed_tools(self) -> list[str]:
        """Claude Code built-in tools the skill is permitted to use.

        Defaults to a general read/write/execute set.  Override in subclasses
        to restrict or expand permissions.
        """
        return ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]

    @property
    def claude_max_turns(self) -> int | None:
        """Maximum agent reasoning steps.  ``None`` uses the CLI default."""
        return None

    def _get_cwd(self) -> str:
        """Working directory for the ``claude`` subprocess.

        Defaults to the aiops project root so that skills can read
        ``project.yaml``, ``.env``, etc.  Override in subclasses when the
        agent needs to operate inside a cloned repository.
        """
        return str(_PROJECT_ROOT)

    def _build_task_prompt(self, task: str) -> str:
        """Augment the user's task with agent-specific context.

        Override in subclasses to prepend information such as project path or
        output directory that the skill needs but that is not part of the
        user's original message.
        """
        return task

    def _get_mcp_config(self) -> dict | None:
        """Return an MCP server configuration dict, or ``None``.

        If a dict is returned it is written to a temporary JSON file and
        passed to claude via ``--mcp-config``.  Use this to provide MCP-based
        tools (e.g. Serena LSP) to the skill.
        """
        return None

    # ------------------------------------------------------------------
    # BaseAgent implementation
    # ------------------------------------------------------------------

    def _build_graph(self) -> "CompiledStateGraph":
        """Build a single-node LangGraph that delegates the task to claude."""

        def invoke_claude(state: MessagesState) -> dict:  # type: ignore[type-arg]
            last_human = next(
                (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
                None,
            )
            raw_task = last_human.content if last_human else ""
            task = self._build_task_prompt(str(raw_task))
            result = self._call_claude(task)
            return {"messages": [AIMessage(content=result)]}

        graph = StateGraph(MessagesState)
        graph.add_node(self.name, invoke_claude)
        graph.add_edge(START, self.name)
        graph.add_edge(self.name, END)
        return graph.compile()

    # ------------------------------------------------------------------
    # Claude invocation
    # ------------------------------------------------------------------

    def _call_claude(self, task: str) -> str:
        """Build the CLI arguments, invoke ``claude --print``, and return stdout."""
        args: list[str] = [
            "--print",
            "--dangerously-skip-permissions",
            "--no-session-persistence",
            "--allowedTools",
            ",".join(self.claude_allowed_tools),
            "--add-dir",
            str(_PROJECT_ROOT),
        ]
        if self.claude_max_turns is not None:
            args = ["--max-turns", str(self.claude_max_turns)] + args

        mcp_config = self._get_mcp_config()
        mcp_tmpfile: tempfile.NamedTemporaryFile | None = None  # type: ignore[type-arg]
        if mcp_config is not None:
            mcp_tmpfile = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            )
            json.dump(mcp_config, mcp_tmpfile)
            mcp_tmpfile.flush()
            mcp_tmpfile.close()
            args += ["--mcp-config", mcp_tmpfile.name]

        # Invoke the skill by prepending the slash-command to the task.
        prompt = f"/{self.skill_name} {task}"

        logger.debug(
            "Agent '{}' invoking claude: skill={} cwd={} tools={}",
            self.name,
            self.skill_name,
            self._get_cwd(),
            self.claude_allowed_tools,
        )
        try:
            return run_command(
                "claude",
                *args,
                cwd=self._get_cwd(),
                env=_UNSET_ENV,
                stdin_input=prompt,
                timeout=600,
            )
        except RuntimeError as exc:
            return f"Error running Claude Code: {exc}"
        finally:
            if mcp_tmpfile is not None:
                Path(mcp_tmpfile.name).unlink(missing_ok=True)
