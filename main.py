"""Entry point for the aiops multi-agent system.

Usage examples:

    # Interactive session with the GitHub agent
    python main.py --agent github

    # One-shot query
    python main.py --agent github --query "List open issues in octocat/Hello-World"

    # Enable DEBUG logging for the GitHub agent
    python main.py --agent github --debug-agent github

    # Equivalent via environment variable
    DEBUG_AGENT=github python main.py --agent github
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

# ---------------------------------------------------------------------------
# Bootstrap: load .env before importing anything that reads env vars
# ---------------------------------------------------------------------------
from dotenv import load_dotenv

load_dotenv(override=False)  # load .env; existing env vars take precedence

# ---------------------------------------------------------------------------
# Logging must be initialised before any other src imports so that all
# log calls during import are captured.
# ---------------------------------------------------------------------------
from src.core.logging import enable_debug_for_agent, setup_logging  # noqa: E402

# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------
AGENT_REGISTRY: dict[str, type] = {}

def _register_agents() -> None:
    """Auto-discover and register all agents found under src/agents/.

    Each subdirectory of src/agents/ that is a Python package (has __init__.py)
    is imported. Any class that inherits from BaseAgent and declares a non-base
    ``name`` attribute is registered automatically, so no manual edits are
    needed when adding new agents.
    """
    import importlib
    import inspect
    import pkgutil

    import src.agents as agents_pkg
    from src.agents.base import BaseAgent

    for _finder, module_name, is_pkg in pkgutil.iter_modules(
        agents_pkg.__path__, agents_pkg.__name__ + "."
    ):
        if not is_pkg:
            continue  # skip plain modules such as base.py

        module = importlib.import_module(module_name)

        for _attr, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseAgent)
                and obj is not BaseAgent
                and obj.name != "base"
            ):
                AGENT_REGISTRY[obj.name] = obj


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="aiops – LangGraph multi-agent system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--agent",
        "-a",
        default="main",
        help="Agent to run (default: main). Available: %(choices)s",
    )
    parser.add_argument(
        "--query",
        "-q",
        default=None,
        help="Single query to run non-interactively, then exit.",
    )
    parser.add_argument(
        "--debug-agent",
        default=None,
        metavar="AGENT_NAME",
        help=(
            "Enable DEBUG-level logging and LangChain verbose=True for the "
            "specified agent name (e.g. 'github'). "
            "Equivalent to setting DEBUG_AGENT=<name> in the environment."
        ),
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Session ID for Langfuse tracing (auto-generated if omitted).",
    )
    return parser


# ---------------------------------------------------------------------------
# Debug mode resolution
# ---------------------------------------------------------------------------

def _resolve_debug_agent(cli_value: str | None) -> str:
    """Return the effective debug-agent name from CLI arg or env var."""
    if cli_value:
        return cli_value.strip().lower()
    return os.environ.get("DEBUG_AGENT", "").strip().lower()


# ---------------------------------------------------------------------------
# Interactive REPL
# ---------------------------------------------------------------------------

def _run_interactive(agent_instance: object, agent_name: str) -> None:
    from src.core.logging import get_logger

    logger = get_logger("main")
    print(f"\n[aiops] Agent '{agent_name}' ready. Type 'quit' or 'exit' to leave.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[aiops] Session ended.")
            break

        if not user_input:
            continue

        if user_input.lower() in {"quit", "exit", "q"}:
            print("[aiops] Goodbye.")
            break

        try:
            response = agent_instance.run(user_input)  # type: ignore[union-attr]
            print(f"\nAgent: {response}\n")
        except Exception as exc:
            logger.error("Agent error: {}", exc)
            print(f"[error] {exc}\n")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    # ---- Debug-agent resolution ----------------------------------------
    debug_agent = _resolve_debug_agent(args.debug_agent)

    # ---- Logging setup (must happen before agent imports) ---------------
    setup_logging()

    if debug_agent:
        enable_debug_for_agent(debug_agent)
        os.environ["DEBUG_AGENT"] = debug_agent  # propagate to sub-processes

    # ---- Project config validation (fast-fail) --------------------------
    from src.core.project import get_project_config
    try:
        get_project_config()
    except (FileNotFoundError, ValueError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    # ---- Agent registry -------------------------------------------------
    _register_agents()

    agent_name: str = args.agent.lower()
    if agent_name not in AGENT_REGISTRY:
        print(
            f"[error] Unknown agent '{agent_name}'. "
            f"Available: {', '.join(AGENT_REGISTRY.keys())}",
            file=sys.stderr,
        )
        return 1

    # ---- Instantiate agent ----------------------------------------------
    verbose = debug_agent == agent_name
    session_id = args.session_id or str(uuid.uuid4())

    from src.core.logging import get_logger

    logger = get_logger("main")
    logger.info(
        "Starting agent '{}' (verbose={}, session_id={})", agent_name, verbose, session_id
    )

    AgentClass = AGENT_REGISTRY[agent_name]
    agent_instance = AgentClass(verbose=verbose, session_id=session_id)

    # ---- Run: one-shot or interactive -----------------------------------
    if args.query:
        try:
            response = agent_instance.run(args.query)
            print(response)
        except Exception as exc:
            logger.error("Fatal: {}", exc)
            return 1
    else:
        _run_interactive(agent_instance, agent_name)

    return 0


if __name__ == "__main__":
    sys.exit(main())
