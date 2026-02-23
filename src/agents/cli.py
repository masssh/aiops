"""Shared CLI runner for individual agent entry points.

Each agent's ``agent.py`` can expose a ``__main__`` block like::

    if __name__ == "__main__":
        from src.agents.cli import run_agent_cli

        def _add_args(parser):
            parser.add_argument("--repository-path", ...)

        def _build_kwargs(args):
            return {"repository_path": args.repository_path}

        run_agent_cli(MiseAgent, add_arguments=_add_args, build_kwargs=_build_kwargs)

This keeps agent-specific CLI arguments local to each agent without
polluting the generic ``main.py`` dispatcher.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from typing import TYPE_CHECKING, Callable

from src.core.logging import extract_content_blocks, get_logger, pjson

if TYPE_CHECKING:
    from src.agents.base import BaseAgent

logger = get_logger(__name__)


def _interactive_loop(agent: "BaseAgent") -> None:
    """Run a simple REPL for the given agent."""
    logger.info("Agent '{}' ready. Type 'quit' or 'exit' to leave.", agent.name)
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            logger.info("Session ended.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "q"}:
            logger.info("Goodbye.")
            break

        try:
            logger.info("Agent: {}", agent.run(user_input))
        except Exception as exc:
            logger.error("Agent error: {}", exc)


def run_agent_cli(
    agent_class: type,
    *,
    add_arguments: Callable[[argparse.ArgumentParser], None] | None = None,
    build_kwargs: Callable[[argparse.Namespace], dict] | None = None,
) -> None:
    """Generic CLI entry point for a single agent.

    Args:
        agent_class:    The agent class to instantiate and run.
        add_arguments:  Optional callable ``(parser) -> None`` that adds
                        agent-specific arguments to the parser.
        build_kwargs:   Optional callable ``(args) -> dict`` that converts
                        the parsed args into extra constructor kwargs for the
                        agent (beyond ``verbose`` and ``session_id``).
    """
    from dotenv import load_dotenv

    load_dotenv(override=False)

    from src.core.logging import enable_debug_for_agent, setup_logging

    parser = argparse.ArgumentParser(
        description=getattr(agent_class, "description", agent_class.__name__),
    )
    parser.add_argument("--query", "-q", default=None, help="One-shot query, then exit.")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging.")
    parser.add_argument(
        "--session-id",
        default=None,
        help="Session ID for Langfuse tracing (auto-generated if omitted).",
    )

    if add_arguments is not None:
        add_arguments(parser)

    args = parser.parse_args()

    setup_logging()
    if args.debug:
        enable_debug_for_agent(agent_class.name)

    kwargs: dict = {
        "verbose": args.debug,
        "session_id": args.session_id or str(uuid.uuid4()),
    }
    if build_kwargs is not None:
        kwargs.update(build_kwargs(args))

    logger.info("Starting {} with kwargs:\n{}", agent_class.__name__, pjson(kwargs))
    agent = agent_class(**kwargs)

    if args.query:
        try:
            result = agent.run(args.query)
            logger.info("Result:\n{}", extract_content_blocks(result))
        except Exception as exc:
            logger.error("Fatal: {}", exc)
            sys.exit(1)
    else:
        _interactive_loop(agent)
