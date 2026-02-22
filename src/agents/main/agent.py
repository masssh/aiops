"""Main orchestrator agent.

Receives a user request, decomposes it into one or more GitHub agent tasks
via an LLM planner, dispatches those tasks to parallel GitHubAgent instances
using LangGraph's Send API, then synthesizes the results into a final response.

Example::

    from src.agents.main import MainAgent

    agent = MainAgent()
    response = agent.run(
        "Clone https://github.com/foo/bar into /tmp/bar "
        "and https://github.com/baz/qux into /tmp/qux"
    )
    print(response)
"""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING, Annotated, Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph.message import add_messages
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from src.agents.base import BaseAgent
from src.core.llm import create_llm
from src.core.logging import get_logger

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class MainState(TypedDict):
    """State shared across the main orchestrator graph."""

    messages: Annotated[list[BaseMessage], add_messages]
    #: Tasks planned for the GitHub agents (set by planner node)
    tasks: list[str]
    #: Results collected from parallel github_worker nodes (accumulated via operator.add)
    results: Annotated[list[str], operator.add]


# ---------------------------------------------------------------------------
# Structured output schema
# ---------------------------------------------------------------------------


class TaskPlan(BaseModel):
    """Structured task decomposition from the planner LLM."""

    tasks: list[str] = Field(
        description=(
            "List of concrete, self-contained task instructions for the GitHub agent. "
            "Each task must be a clear natural-language sentence describing a single "
            "Git operation (e.g. 'Clone https://... into /tmp/foo')."
        )
    )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_PLANNER_PROMPT = """\
You are a task planner for a multi-agent Git automation system.

The GitHub agent supports the following operations:
  - Clone a Git repository: provide the URL and an optional local destination path.
  - Checkout a branch: provide the local repository path and the branch name.

Given the user's request, decompose it into one or more concrete, self-contained task
instructions for the GitHub agent.  Each task should be an independent natural-language
sentence that the agent can execute without additional context.

Rules:
  - Output one task per distinct Git operation.
  - If multiple repositories are mentioned, produce one task per repository.
  - Never combine multiple operations into a single task.
  - If the request is a single operation, output exactly one task.
"""

_SYNTHESIZER_PROMPT = """\
You are a helpful assistant that summarizes the results of parallel Git operations.

Given the original user request and the outputs from one or more GitHub agents,
write a clear, concise summary of what was accomplished (or what errors occurred).
Keep the summary factual and brief.
"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class MainAgent(BaseAgent):
    """Orchestrator that fans out tasks to GitHub agents running in parallel."""

    name: str = "main"
    description: str = (
        "Orchestrates one or more GitHub agent tasks in parallel, then synthesises results."
    )

    def _build_graph(self) -> "CompiledStateGraph":
        llm = create_llm(verbose=self.verbose)
        planner_llm = llm.with_structured_output(TaskPlan)

        # ----------------------------------------------------------------
        # Node: planner
        # ----------------------------------------------------------------

        def planner(state: MainState) -> dict[str, Any]:
            """Ask the LLM to decompose the user request into GitHub agent tasks."""
            user_msg = next(
                (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
                None,
            )
            if user_msg is None:
                logger.warning("No human message found in state; skipping planning.")
                return {"tasks": []}

            logger.debug("Planner received: {!r}", str(user_msg.content)[:200])
            plan: TaskPlan = planner_llm.invoke(
                [SystemMessage(content=_PLANNER_PROMPT), user_msg]
            )
            logger.info(
                "Planner produced {} task(s): {}",
                len(plan.tasks),
                plan.tasks,
            )
            return {"tasks": plan.tasks}

        # ----------------------------------------------------------------
        # Node: github_worker  (one instance per task, run in parallel)
        # ----------------------------------------------------------------

        verbose = self.verbose
        session_id = self.session_id

        def github_worker(state: dict[str, Any]) -> dict[str, Any]:
            """Run a GitHubAgent for a single task and return the result."""
            # Import here to avoid circular imports at module load time
            from src.agents.github.agent import GitHubAgent

            task: str = state["task"]
            logger.info("GitHub worker → {!r}", task[:200])
            agent = GitHubAgent(verbose=verbose, session_id=session_id)
            try:
                result = agent.run(task)
            except Exception as exc:
                result = f"[error] {exc}"
                logger.error("GitHub worker failed for task {!r}: {}", task[:80], exc)
            logger.info("GitHub worker ← {!r}", result[:200])
            return {"results": [result]}

        # ----------------------------------------------------------------
        # Node: synthesizer
        # ----------------------------------------------------------------

        def synthesizer(state: MainState) -> dict[str, Any]:
            """Synthesise a final response from all collected results."""
            user_msg = next(
                (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
                None,
            )
            tasks = state.get("tasks", [])
            results = state.get("results", [])

            if not tasks:
                response = llm.invoke(
                    [HumanMessage(content="No tasks were generated from the user's request.")]
                )
                return {"messages": [response]}

            task_result_pairs = "\n\n".join(
                f"Task {i + 1}: {task}\nResult: {result}"
                for i, (task, result) in enumerate(zip(tasks, results))
            )
            synthesis_input = [
                SystemMessage(content=_SYNTHESIZER_PROMPT),
                HumanMessage(
                    content=(
                        f"User request: {user_msg.content if user_msg else '(unknown)'}\n\n"
                        f"{task_result_pairs}"
                    )
                ),
            ]
            response = llm.invoke(synthesis_input)
            logger.info("Synthesizer produced response: {!r}", str(response.content)[:200])
            return {"messages": [response]}

        # ----------------------------------------------------------------
        # Conditional edge: fan_out
        # ----------------------------------------------------------------

        def fan_out(state: MainState) -> list[Send]:
            """Dispatch each task to a parallel github_worker node via Send."""
            tasks = state.get("tasks", [])
            if not tasks:
                logger.warning("No tasks to dispatch; routing directly to synthesizer.")
                return [Send("synthesizer", state)]
            logger.info("Fanning out {} task(s) to parallel GitHub workers.", len(tasks))
            return [Send("github_worker", {"task": task}) for task in tasks]

        # ----------------------------------------------------------------
        # Graph definition
        # ----------------------------------------------------------------

        graph = StateGraph(MainState)
        graph.add_node("planner", planner)
        graph.add_node("github_worker", github_worker)
        graph.add_node("synthesizer", synthesizer)

        graph.add_edge(START, "planner")
        graph.add_conditional_edges("planner", fan_out, ["github_worker", "synthesizer"])
        graph.add_edge("github_worker", "synthesizer")
        graph.add_edge("synthesizer", END)

        return graph.compile()


if __name__ == "__main__":
    from src.agents.cli import run_agent_cli

    run_agent_cli(MainAgent)
