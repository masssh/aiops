"""SCIP agent tools.

Provides a factory function ``create_scip_tools`` that returns LangChain tools
for the full SCIP analysis pipeline:

1. ``generate_scip_index``   — run the appropriate SCIP indexer via Docker
2. ``load_scip_to_neo4j``    — parse the ``.scip`` binary and store in Neo4j
3. ``find_graph_communities`` — Louvain community detection on the symbol graph
4. ``get_community_symbols``  — list symbols in a specific community
5. ``run_cypher_query``       — execute an arbitrary read-only Cypher query

SCIP indexers (Docker images)
==============================
Each indexer is executed with ``docker run --rm``.  The project directory is
mounted read-only as ``/project`` and the output directory as ``/output``.

Default images (override via environment variables):

+----------------------------+------------------------------------------+
| Language                   | Env var / default image                  |
+============================+==========================================+
| Python                     | SCIP_PYTHON_IMAGE                        |
|                            | sourcegraph/scip-python:latest           |
+----------------------------+------------------------------------------+
| TypeScript / JavaScript    | SCIP_TYPESCRIPT_IMAGE                    |
|                            | sourcegraph/scip-typescript:latest       |
+----------------------------+------------------------------------------+
| Java / Kotlin              | SCIP_JAVA_IMAGE                          |
|                            | sourcegraph/scip-java:latest             |
+----------------------------+------------------------------------------+

Neo4j connection
================
Settings are read from environment variables::

    NEO4J_URI      = bolt://localhost:7687
    NEO4J_USERNAME = neo4j
    NEO4J_PASSWORD = password
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool

from src.agents.scip._neo4j_store import (
    create_driver,
    extract_entrypoints,
    find_communities,
    purge_repo,
    query_neo4j,
    store_scip_index,
)
from src.agents.scip._scip_parser import parse_scip_file
from src.core.logging import get_logger
from src.core.process import run_command
from src.core.project import get_project_config

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Docker image names (overridable via environment variables)
# ---------------------------------------------------------------------------

_DEFAULT_IMAGES: dict[str, str] = {
    "python":     "sourcegraph/scip-python:latest",
    "typescript": "sourcegraph/scip-typescript:latest",
    "javascript": "sourcegraph/scip-typescript:latest",
    "java":       "sourcegraph/scip-java:latest",
}

_IMAGE_ENV_VARS: dict[str, str] = {
    "python":     "SCIP_PYTHON_IMAGE",
    "typescript": "SCIP_TYPESCRIPT_IMAGE",
    "javascript": "SCIP_TYPESCRIPT_IMAGE",
    "java":       "SCIP_JAVA_IMAGE",
}


def _docker_image(lang: str) -> str:
    """Return the Docker image for *lang*, honouring env-var overrides."""
    env_var = _IMAGE_ENV_VARS.get(lang, "")
    return os.getenv(env_var, _DEFAULT_IMAGES.get(lang, ""))


def _docker_run(
    image: str,
    project_path: str,
    output_dir: str,
    *cmd_args: str,
    project_readonly: bool = True,
    extra_volumes: tuple[str, ...] = (),
) -> None:
    """Run a SCIP indexer container with standard volume mounts.

    Mounts:
      - ``project_path`` → ``/project`` (read-only by default)
      - ``output_dir``   → ``/output``  (writable)

    The container's working directory is set to ``/project``.
    An optional ``--platform`` flag is added when ``SCIP_DOCKER_PLATFORM``
    is set (default ``linux/amd64``; useful on Apple Silicon hosts).

    Args:
        image:            Docker image name and tag.
        project_path:     Absolute path to the source repository on the host.
        output_dir:       Absolute path to the output directory on the host.
        *cmd_args:        Arguments appended after the image name.
                          Must start with the binary name (e.g. ``"scip-java"``)
                          because sourcegraph images use ``exec "$@"`` as their
                          entrypoint and the first arg is executed as a binary.
        project_readonly: Mount the project volume read-only (default True).
                          Set False for build tools (Maven/Gradle) that write
                          to ``target/`` or ``.gradle/`` inside the project.
        extra_volumes:    Additional ``host_path:container_path`` volume strings
                          inserted before the image name (e.g. for build caches).
    """
    platform = os.getenv("SCIP_DOCKER_PLATFORM", "linux/amd64")
    platform_args = ("--platform", platform) if platform else ()
    project_mount = f"{project_path}:/project" + (":ro" if project_readonly else "")
    extra_vol_args: tuple[str, ...] = ()
    for vol in extra_volumes:
        extra_vol_args += ("-v", vol)
    run_command(
        "docker", "run", "--rm",
        *platform_args,
        "-v", project_mount,
        "-v", f"{output_dir}:/output",
        *extra_vol_args,
        "-w", "/project",
        image,
        *cmd_args,
    )


# ---------------------------------------------------------------------------
# Language / indexer detection (same indicator priority as sbom/tools.py)
# ---------------------------------------------------------------------------

_LANG_INDICATORS: list[tuple[tuple[str, ...], str]] = [
    (("pom.xml", "mvnw", ".mvn"), "java"),
    (("build.gradle", "build.gradle.kts", "gradlew"), "java"),
    (("package.json",), "typescript"),
    (("pyproject.toml", "setup.py", "requirements.txt", "Pipfile"), "python"),
    (("go.mod",), "go"),
    (("Cargo.toml",), "rust"),
]


def _detect_language(root: Path) -> str:
    for indicators, lang in _LANG_INDICATORS:
        for indicator in indicators:
            if (root / indicator).exists():
                return lang
    return "unknown"


def _neo4j_driver():  # type: ignore[return]
    """Build a Neo4j driver from environment variables."""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    return create_driver(uri, user, password)


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def create_scip_tools(project_path: str, repo_name: str) -> list:
    """Create SCIP pipeline tools scoped to *project_path*.

    Args:
        project_path: Absolute or relative path to the target repository.
        repo_name:    Repository name (used to derive output paths and
                      Neo4j node scope).

    Returns:
        List of LangChain tools ready to be bound to an agent.
    """
    _project_path = str(Path(project_path).resolve())
    cfg = get_project_config()
    _repo_out = cfg.repo_output_dir(repo_name)
    _default_index = str(_repo_out / "index.scip")
    _default_communities = str(_repo_out / "communities.json")
    _default_entrypoints = str(_repo_out / "entrypoints.json")

    # ------------------------------------------------------------------
    # Tool 1: generate_scip_index
    # ------------------------------------------------------------------

    @tool
    def generate_scip_index(
        output_path: Annotated[
            str,
            "Output path for the .scip index file. "
            "Leave empty to use the default path under agent_output/.",
        ] = "",
        language: Annotated[
            str,
            "Force a specific language: 'python', 'typescript', or 'java'. "
            "Leave empty to auto-detect from project files.",
        ] = "",
    ) -> str:
        """Generate a SCIP index for the project by running a Docker container.

        The indexer image is launched with ``docker run --rm``:
        - The project directory is mounted read-only at ``/project``.
        - The output directory is mounted at ``/output``.

        Language → Docker image:
        - Python:     $SCIP_PYTHON_IMAGE     (default: sourcegraph/scip-python:latest)
        - TypeScript: $SCIP_TYPESCRIPT_IMAGE (default: sourcegraph/scip-typescript:latest)
        - Java:       $SCIP_JAVA_IMAGE       (default: sourcegraph/scip-java:latest)

        Do NOT pass an explicit output_path unless instructed by the user.
        """
        out = Path(output_path or _default_index)
        lang = language or _detect_language(Path(_project_path))
        out.parent.mkdir(parents=True, exist_ok=True)
        out_dir = str(out.parent)
        out_name = out.name  # file name inside the container's /output mount

        image = _docker_image(lang)
        if not image:
            return (
                f"Unsupported or unknown language '{lang}'.\n"
                "Supported: python, typescript, java.\n"
                "Pass --language explicitly if auto-detection is wrong."
            )

        logger.info(
            "generate_scip_index: lang={} image={} project={} out={}",
            lang, image, _project_path, out,
        )

        if lang == "python":
            _docker_run(
                image, _project_path, out_dir,
                "scip-python", "index",
                "--project-name", repo_name,
                "--output", f"/output/{out_name}",
                ".",
            )

        elif lang in ("typescript", "javascript"):
            _docker_run(
                image, _project_path, out_dir,
                "scip-typescript", "index",
                "--project-dir", "/project",
                "--output", f"/output/{out_name}",
            )

        elif lang == "java":
            # Maven/Gradle need write access to target/ and .gradle/ inside
            # the project, so mount read-write.  Cache ~/.m2 and ~/.gradle
            # on the host to avoid re-downloading dependencies each run.
            home = str(Path.home())
            _docker_run(
                image, _project_path, out_dir,
                "scip-java", "index",
                "--build-tool", "auto",
                "--output", f"/output/{out_name}",
                project_readonly=False,
                extra_volumes=(
                    f"{home}/.m2:/root/.m2",
                    f"{home}/.gradle:/root/.gradle",
                ),
            )

        else:
            return (
                f"Unsupported language '{lang}'.\n"
                "Supported: python, typescript, java.\n"
                "Override the Docker image via SCIP_PYTHON_IMAGE / "
                "SCIP_TYPESCRIPT_IMAGE / SCIP_JAVA_IMAGE env vars."
            )

        return f"SCIP index generated at '{out}'."

    # ------------------------------------------------------------------
    # Tool 2: load_scip_to_neo4j
    # ------------------------------------------------------------------

    @tool
    def load_scip_to_neo4j(
        index_path: Annotated[
            str,
            "Path to the .scip binary file. "
            "Leave empty to use the default path under agent_output/.",
        ] = "",
        purge_existing: Annotated[
            bool,
            "If True, delete existing nodes for this repo before importing. "
            "Defaults to True to ensure stale symbols and call edges are removed "
            "when code has changed between runs.",
        ] = True,
    ) -> str:
        """Parse a SCIP index file and store its symbols and relationships in Neo4j.

        Creates the following nodes and relationships:
        - (:Document {path, repo, language})
        - (:Symbol   {id, kind, kind_name, language, repo,
                      is_method, is_noise, method_name})
        - (:Symbol)-[:DEFINED_IN]->(:Document)
        - (:Symbol)-[:REFERENCED_IN]->(:Document)
        - (:Symbol)-[:RELATES_TO {kind}]->(:Symbol)
        - (:Symbol)-[:CALLS {weight}]->(:Symbol)  ← method-level call edges

        purge_existing defaults to True to prevent stale nodes and call edges
        from accumulating when the codebase has changed between runs.
        Set to False only when you are certain the code has not changed and
        want to avoid the overhead of a full re-index.

        Run generate_scip_index first if the .scip file does not yet exist.
        """
        path = index_path or _default_index
        if not Path(path).exists():
            return f"Index file not found at '{path}'. Run generate_scip_index first."

        logger.info("load_scip_to_neo4j: parsing {}", path)
        try:
            index = parse_scip_file(path)
        except (OSError, ValueError) as exc:
            return f"Failed to parse SCIP file: {exc}"

        stats = index.stats
        logger.info("SCIP index parsed: {}", stats)

        try:
            driver = _neo4j_driver()
        except Exception as exc:
            return (
                f"Cannot connect to Neo4j: {exc}\n"
                "Check NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD in .env "
                "and ensure Neo4j is running (docker compose up -d neo4j)."
            )

        try:
            if purge_existing:
                purge_result = purge_repo(driver, repo_name)
                logger.info("Purged existing data: {}", purge_result)

            stored = store_scip_index(driver, index, repo_name)
        finally:
            driver.close()

        return (
            f"SCIP index loaded into Neo4j for repo '{repo_name}'.\n"
            f"  Parsed:  {stats}\n"
            f"  Stored:  {stored}"
        )

    # ------------------------------------------------------------------
    # Tool 3: find_graph_communities
    # ------------------------------------------------------------------

    @tool
    def find_graph_communities(
        output_path: Annotated[
            str,
            "Output path for the communities JSON file. "
            "Leave empty to use the default path under agent_output/.",
        ] = "",
    ) -> str:
        """Detect clusters of tightly-coupled symbols in the Neo4j graph.

        Uses the Louvain community-detection algorithm on the RELATES_TO
        symbol graph.  Writes a ``community_id`` property back to each Symbol
        node in Neo4j and saves a JSON summary.

        Run load_scip_to_neo4j first to populate the graph.
        """
        out = output_path or _default_communities

        try:
            driver = _neo4j_driver()
        except Exception as exc:
            return f"Cannot connect to Neo4j: {exc}"

        try:
            result = find_communities(driver, repo_name, output_path=out)
        finally:
            driver.close()

        if "error" in result:
            return result["error"]

        communities = result.get("communities", [])
        lines = [
            f"Found {result['num_communities']} communities "
            f"({result['total_symbols']} symbols total).",
            f"Community summary written to '{out}'.",
            "",
            "Top communities:",
        ]
        for c in communities[:10]:
            samples = ", ".join(c["sample_symbols"])
            lines.append(f"  Community {c['id']} — {c['size']} symbols  [{samples}…]")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Tool 4: get_community_symbols
    # ------------------------------------------------------------------

    @tool
    def get_community_symbols(
        community_id: Annotated[
            int,
            "Community ID to inspect (from find_graph_communities output).",
        ],
        limit: Annotated[
            int,
            "Maximum number of symbols to return. Default 50.",
        ] = 50,
    ) -> str:
        """Return the symbols belonging to a specific community.

        Shows symbol IDs, kinds, and the source file they are defined in.
        Use find_graph_communities first to assign community IDs.
        """
        try:
            driver = _neo4j_driver()
        except Exception as exc:
            return f"Cannot connect to Neo4j: {exc}"

        try:
            rows = query_neo4j(
                driver,
                "MATCH (s:Symbol {repo: $repo, community_id: $cid}) "
                "OPTIONAL MATCH (s)-[:DEFINED_IN]->(d:Document) "
                "RETURN s.id AS id, s.kind_name AS kind, d.path AS file "
                "ORDER BY s.kind_name, s.id "
                "LIMIT $limit",
                {"repo": repo_name, "cid": community_id, "limit": limit},
            )
        finally:
            driver.close()

        if not rows:
            return (
                f"No symbols found for community {community_id}. "
                "Run find_graph_communities first, or check the community ID."
            )

        lines = [f"Community {community_id} — {len(rows)} symbol(s) shown:"]
        for r in rows:
            file_info = f"  ({r['file']})" if r.get("file") else ""
            lines.append(f"  [{r.get('kind', '?')}] {r['id']}{file_info}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Tool 5: query_neo4j
    # ------------------------------------------------------------------

    @tool
    def run_cypher_query(
        cypher: Annotated[
            str,
            "Read-only Cypher query to execute against the Neo4j graph.",
        ],
        params_json: Annotated[
            str,
            "JSON object of query parameters, e.g. '{\"repo\": \"my-repo\"}'. "
            "Leave empty if the query has no parameters.",
        ] = "",
    ) -> str:
        """Execute an arbitrary read-only Cypher query against the Neo4j graph.

        Returns up to 100 rows formatted as a JSON array.  Use this for custom
        graph exploration, e.g. finding callers of a specific symbol or listing
        all classes in a community.

        Example queries:
          MATCH (s:Symbol {repo: 'my-repo', kind_name: 'Class'}) RETURN s.id LIMIT 20
          MATCH p=(s1:Symbol)-[:RELATES_TO*1..2]->(s2:Symbol) WHERE s1.id CONTAINS 'MyClass' RETURN p
        """
        try:
            params = json.loads(params_json) if params_json.strip() else {}
        except json.JSONDecodeError as exc:
            return f"Invalid params_json: {exc}"

        try:
            driver = _neo4j_driver()
        except Exception as exc:
            return f"Cannot connect to Neo4j: {exc}"

        try:
            rows = query_neo4j(driver, cypher, params)
        except Exception as exc:
            return f"Query failed: {exc}"
        finally:
            driver.close()

        if not rows:
            return "Query returned no results."

        rows_shown = rows[:100]
        extra = f"\n… and {len(rows) - 100} more rows." if len(rows) > 100 else ""
        return json.dumps(rows_shown, ensure_ascii=False, indent=2) + extra

    # ------------------------------------------------------------------
    # Tool 6: extract_graph_entrypoints
    # ------------------------------------------------------------------

    @tool
    def extract_graph_entrypoints(
        output_path: Annotated[
            str,
            "Output path for the entrypoints JSON file. "
            "Leave empty to use the default path under agent_output/.",
        ] = "",
    ) -> str:
        """Extract root callables (entrypoints) from the method-level call graph.

        An entrypoint is a callable with in_degree=0 — nothing in the analysed
        codebase calls it, so it must be invoked externally (HTTP framework,
        scheduler, AI tool runner, event bus, etc.).

        Returns a flat list of root_methods sorted by out_degree descending,
        each with short_name, method_name, container_name, file path, and
        community_id.  Also returns a per-community summary with the top
        entrypoint of each cluster.

        Language-specific noise callables (toString / __init__ / constructor
        etc.) are excluded automatically based on the document language.

        Run load_scip_to_neo4j and find_graph_communities first.
        """
        out = output_path or _default_entrypoints

        try:
            driver = _neo4j_driver()
        except Exception as exc:
            return f"Cannot connect to Neo4j: {exc}"

        try:
            result = extract_entrypoints(driver, repo_name, output_path=out)
        finally:
            driver.close()

        root_methods = result.get("root_methods", [])
        communities = result.get("communities", [])

        lines = [
            f"Entrypoints extracted for repo '{repo_name}'.",
            f"  Total methods:    {result.get('total_methods', 0)}",
            f"  Total call edges: {result.get('total_call_edges', 0)}",
            f"  Root methods:     {len(root_methods)}",
            f"  Output written to '{out}'.",
            "",
            "Root methods (sorted by out_degree):",
        ]
        for ep in root_methods[:20]:
            lines.append(f"  [{ep['out_degree']:>3} calls] {ep['short_name']}  ({ep['file']})")

        if communities:
            lines.append("")
            lines.append("Community top entrypoints:")
            for c in communities[:10]:
                top = c.get("top_entrypoint") or "(none)"
                lines.append(f"  comm {c['community_id']:>2} ({c['size']:>3} members): {top}")

        return "\n".join(lines)

    return [
        generate_scip_index,
        load_scip_to_neo4j,
        find_graph_communities,
        get_community_symbols,
        extract_graph_entrypoints,
        run_cypher_query,
    ]
