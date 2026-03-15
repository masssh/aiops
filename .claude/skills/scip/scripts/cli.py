"""Standalone CLI for SCIP code intelligence operations.

This script lives inside the skill directory so that all skill-related code is
co-located with its SKILL.md.  It adds the aiops project root to ``sys.path``
automatically (4 levels up: scripts/ → scip/ → skills/ → .claude/ → aiops/).

Usage (from any working directory)::

    python ${CLAUDE_SKILL_DIR}/scripts/cli.py <command> \
        --project-path PATH --repo-name NAME [options]

Commands
--------
generate-index       Generate a SCIP index file using the appropriate Docker indexer.
load-to-neo4j        Parse a SCIP index and store symbols/relationships in Neo4j.
find-communities     Detect code communities via Louvain algorithm on the symbol graph.
get-community        List all symbols in a specific community.
extract-entrypoints  Extract root callables (entrypoints) from the call graph.
run-cypher           Execute an ad-hoc read-only Cypher query against Neo4j.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap: insert the aiops project root so that `src.*` imports work
# regardless of the working directory when this script is called.
# Layout: .claude/skills/scip/scripts/cli.py → parents[4] = aiops root
# ---------------------------------------------------------------------------
_AIOPS_ROOT = Path(__file__).resolve().parents[4]
if str(_AIOPS_ROOT) not in sys.path:
    sys.path.insert(0, str(_AIOPS_ROOT))


def _get_tools(project_path: str, repo_name: str) -> dict:
    from src.agents.scip.tools import create_scip_tools

    return {t.name: t for t in create_scip_tools(project_path, repo_name)}


def cmd_generate_index(args: argparse.Namespace) -> None:
    tools = _get_tools(args.project_path, args.repo_name)
    result = tools["generate_scip_index"].invoke({
        "output_path": args.output_path or "",
        "language": args.language or "",
    })
    print(result)


def cmd_load_to_neo4j(args: argparse.Namespace) -> None:
    tools = _get_tools(args.project_path, args.repo_name)
    result = tools["load_scip_to_neo4j"].invoke({
        "index_path": args.index_path or "",
        "purge_existing": not args.no_purge,
    })
    print(result)


def cmd_find_communities(args: argparse.Namespace) -> None:
    tools = _get_tools(args.project_path, args.repo_name)
    result = tools["find_graph_communities"].invoke({
        "output_path": args.output_path or "",
    })
    print(result)


def cmd_get_community(args: argparse.Namespace) -> None:
    tools = _get_tools(args.project_path, args.repo_name)
    result = tools["get_community_symbols"].invoke({
        "community_id": args.community_id,
        "limit": args.limit,
    })
    print(result)


def cmd_extract_entrypoints(args: argparse.Namespace) -> None:
    tools = _get_tools(args.project_path, args.repo_name)
    result = tools["extract_graph_entrypoints"].invoke({
        "output_path": args.output_path or "",
    })
    print(result)


def cmd_run_cypher(args: argparse.Namespace) -> None:
    tools = _get_tools(args.project_path, args.repo_name)
    result = tools["run_cypher_query"].invoke({
        "cypher": args.query,
        "params_json": args.params or "",
    })
    print(result)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python ${CLAUDE_SKILL_DIR}/scripts/cli.py",
        description="SCIP code intelligence CLI",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project-path", required=True, metavar="PATH",
                        help="Path to the repository directory.")
    common.add_argument("--repo-name", required=True, metavar="NAME",
                        help="Short repository name (used for Neo4j scoping).")

    sub = parser.add_subparsers(dest="command", required=True)

    # generate-index
    p = sub.add_parser("generate-index", parents=[common],
                       help="Generate a SCIP index via Docker.")
    p.add_argument("--output-path", default="", metavar="PATH",
                   help="Output .scip file path (default: agent_output/).")
    p.add_argument("--language", default="", metavar="LANG",
                   help="Force language: python | typescript | java (auto-detect if omitted).")
    p.set_defaults(func=cmd_generate_index)

    # load-to-neo4j
    p = sub.add_parser("load-to-neo4j", parents=[common],
                       help="Load SCIP index into Neo4j.")
    p.add_argument("--index-path", default="", metavar="PATH",
                   help="Path to the .scip file (default: agent_output/).")
    p.add_argument("--no-purge", action="store_true",
                   help="Skip purging existing data before loading.")
    p.set_defaults(func=cmd_load_to_neo4j)

    # find-communities
    p = sub.add_parser("find-communities", parents=[common],
                       help="Detect code communities (Louvain).")
    p.add_argument("--output-path", default="", metavar="PATH",
                   help="Output JSON path (default: agent_output/).")
    p.set_defaults(func=cmd_find_communities)

    # get-community
    p = sub.add_parser("get-community", parents=[common],
                       help="List symbols in a specific community.")
    p.add_argument("--community-id", required=True, type=int, metavar="ID",
                   help="Community ID from find-communities output.")
    p.add_argument("--limit", type=int, default=50, metavar="N",
                   help="Maximum number of symbols to return (default: 50).")
    p.set_defaults(func=cmd_get_community)

    # extract-entrypoints
    p = sub.add_parser("extract-entrypoints", parents=[common],
                       help="Extract root callables from the call graph.")
    p.add_argument("--output-path", default="", metavar="PATH",
                   help="Output JSON path (default: agent_output/).")
    p.set_defaults(func=cmd_extract_entrypoints)

    # run-cypher
    p = sub.add_parser("run-cypher", parents=[common],
                       help="Execute an ad-hoc Cypher query.")
    p.add_argument("--query", required=True, metavar="CYPHER",
                   help="Read-only Cypher query string.")
    p.add_argument("--params", default="", metavar="JSON",
                   help='Query parameters as JSON object, e.g. \'{"repo": "name"}\'.')
    p.set_defaults(func=cmd_run_cypher)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
