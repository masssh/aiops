"""Neo4j storage and community-detection helpers for SCIP index data.

Graph schema
============
Nodes
-----
  (:Document  {path, repo, language})
  (:Symbol    {id, kind, kind_name, language, repo, community_id?,
               is_method, is_noise, method_name})

Relationships
-------------
  (:Symbol)-[:DEFINED_IN]->(:Document)
  (:Symbol)-[:REFERENCED_IN]->(:Document)
  (:Symbol)-[:RELATES_TO {kind}]->(:Symbol)
      kind values: "reference" | "implementation" | "type_definition" | "unknown"
  (:Symbol)-[:CALLS {weight}]->(:Symbol)
      weight: number of call-sites discovered in occurrence data

Community detection
===================
``find_communities`` builds a call graph from CALLS edges, removes noise methods
**before** running the Louvain algorithm (via NetworkX ≥ 2.7), then writes
``community_id`` back to Symbol nodes.  Falls back to RELATES_TO edges for
indexers that emit relationship metadata but no call-site occurrences.

Entrypoint extraction
=====================
``extract_entrypoints`` identifies root methods (in_degree=0 in the CALLS graph)
and returns them as a flat list with file path and out-degree metadata.
No framework-specific categorisation is applied; the caller (e.g. an LLM agent)
interprets the semantic role of each root method.
"""

from __future__ import annotations

import bisect
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import networkx as nx
import networkx.algorithms.community as nx_comm

from src.agents.scip._scip_parser import ROLE_DEFINITION, ScipIndex, SymbolInfo  # noqa: F401
from src.core.logging import get_logger

if TYPE_CHECKING:
    from neo4j import Driver

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BATCH = 500  # rows per UNWIND batch


# ---------------------------------------------------------------------------
# Symbol analysis helpers
# ---------------------------------------------------------------------------

# SCIP callable descriptor: any symbol whose ID ends with (params).
# This pattern is consistent across scip-java, scip-python, and scip-typescript.
# Examples:
#   Java method:        …com/example/Foo#bar().
#   Python method:      …example.module:Foo#bar().
#   Python function:    …example.module:my_func().
#   TypeScript method:  …src/module:Foo#bar().
_IS_CALLABLE_RE = re.compile(r"\(.*\)\.$")


def _is_method_symbol(sid: str) -> bool:
    """Return True if the SCIP symbol ID represents a callable (method or function)."""
    return bool(_IS_CALLABLE_RE.search(sid))


def _method_name_from_id(sid: str) -> str:
    """Extract the short callable name from a SCIP symbol ID.

    Handles Java-style ``<init>`` as well as regular identifiers.

    Examples::

        …Foo#createOwner().       → "createOwner"
        …Foo#<init>().            → "<init>"
        …module:my_func().        → "my_func"
    """
    m = re.search(r"([A-Za-z_$<][A-Za-z0-9_$<>]*)\(", sid)
    return m.group(1) if m else ""


def _class_name_from_id(sid: str) -> str:
    """Extract the container name (class or module) from a SCIP symbol ID.

    Examples::

        …com/example/OwnerResource#createOwner(). → "OwnerResource"
        …example module:MyClass#method().          → "MyClass"
        …example module:top_func().                → "module"
    """
    # Class member: ClassName# (Java, Python, TypeScript)
    m = re.search(r"([A-Za-z_$][A-Za-z0-9_$]*)#", sid)
    if m:
        return m.group(1)
    # Module-level function: last module/path segment before ":"
    m = re.search(r"[/ ]([A-Za-z_][A-Za-z0-9_]*):[A-Za-z_]", sid)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Language-aware noise callable names
# ---------------------------------------------------------------------------

_JAVA_NOISE: frozenset[str] = frozenset({
    "toString", "hashCode", "equals", "<init>", "compareTo",
    "finalize", "clone", "wait", "notify", "notifyAll",
})
_PYTHON_NOISE: frozenset[str] = frozenset({
    "__str__", "__repr__", "__hash__", "__eq__", "__lt__", "__le__",
    "__gt__", "__ge__", "__ne__", "__init__", "__del__", "__new__",
    "__len__", "__bool__", "__contains__", "__iter__", "__next__",
})
_TS_JS_NOISE: frozenset[str] = frozenset({
    "toString", "valueOf", "constructor",
})

_NOISE_BY_LANG: dict[str, frozenset[str]] = {
    "java": _JAVA_NOISE,
    "kotlin": _JAVA_NOISE,
    "python": _PYTHON_NOISE,
    "typescript": _TS_JS_NOISE,
    "javascript": _TS_JS_NOISE,
}
# Union of all language noise sets (used when language is unknown)
_NOISE_ALL: frozenset[str] = _JAVA_NOISE | _PYTHON_NOISE | _TS_JS_NOISE


def _is_noise_method(sid: str, language: str = "") -> bool:
    """Return True for language-specific noise callables that pollute call graphs."""
    noise = _NOISE_BY_LANG.get(language.lower(), _NOISE_ALL)
    return _method_name_from_id(sid) in noise


# ---------------------------------------------------------------------------
# Test-file detection (language-agnostic)
# ---------------------------------------------------------------------------

_TEST_FILE_RE = re.compile(
    r"(?:"
    r"/tests?/"           # /test/ or /tests/ directory
    r"|/spec/"            # /spec/ directory (Ruby, JS)
    r"|[/_]tests?\."      # _test.py, /test.go, _tests.py
    r"|\.spec\."          # foo.spec.ts, foo.spec.js
    r"|\.test\."          # foo.test.ts, foo.test.js
    r"|Test\.java$"       # FooTest.java
    r"|Tests?\.java$"     # FooTests.java
    r"|IT\.java$"         # FooIT.java (integration test)
    r")",
    re.IGNORECASE,
)


def _is_test_file(path: str) -> bool:
    return bool(_TEST_FILE_RE.search(path))


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _short_sym(sid: str) -> str:
    """Short human-readable label for a callable symbol.

    Returns ``ClassName#methodName()`` for class members and
    ``module:funcName()`` for module-level functions.
    """
    container = _class_name_from_id(sid)
    name = _method_name_from_id(sid)
    if container and name:
        sep = "#" if "#" in sid else ":"
        return f"{container}{sep}{name}()"
    if name:
        return f"{name}()"
    return sid.rsplit(" ", 1)[-1] if " " in sid else sid


def _shorten_symbols(symbols: list[str], max_len: int = 60) -> list[str]:
    """Truncate long SCIP symbol identifiers for display."""
    return [s if len(s) <= max_len else "…" + s[-(max_len - 1):] for s in symbols]


# ---------------------------------------------------------------------------
# Driver factory
# ---------------------------------------------------------------------------


def create_driver(uri: str, username: str, password: str) -> "Driver":
    """Create a Neo4j :class:`Driver` instance.

    Args:
        uri:      Bolt/Neo4j URI, e.g. ``bolt://localhost:7687``.
        username: Neo4j username (default ``"neo4j"``).
        password: Neo4j password.

    Returns:
        Connected :class:`neo4j.Driver`.  Call ``.close()`` when done.
    """
    from neo4j import GraphDatabase  # lazy import — optional dependency

    return GraphDatabase.driver(uri, auth=(username, password))


# ---------------------------------------------------------------------------
# Index setup
# ---------------------------------------------------------------------------


def ensure_constraints(driver: "Driver") -> None:
    """Create uniqueness constraints and indexes (idempotent)."""
    with driver.session() as session:
        session.run(
            "CREATE CONSTRAINT symbol_id IF NOT EXISTS "
            "FOR (s:Symbol) REQUIRE s.id IS UNIQUE"
        )
        session.run(
            "CREATE CONSTRAINT document_path IF NOT EXISTS "
            "FOR (d:Document) REQUIRE (d.path, d.repo) IS UNIQUE"
        )
        logger.debug("Neo4j constraints verified.")


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def store_scip_index(driver: "Driver", index: ScipIndex, repo_name: str) -> dict[str, int]:
    """Persist a :class:`ScipIndex` to Neo4j.

    Uses batched UNWIND Cypher statements for performance.

    After storing documents, symbols, and file-level occurrence edges this
    function also calls :func:`store_method_calls` to build method-level
    ``(:Symbol)-[:CALLS]->(:Symbol)`` edges from SCIP occurrence ranges.

    Args:
        driver:    Connected Neo4j driver.
        index:     Parsed SCIP index.
        repo_name: Repository name used to scope Document / Symbol nodes.

    Returns:
        Dict with counts: ``documents``, ``symbols``, ``occurrences``,
        ``relationships``, ``call_edges``.
    """
    ensure_constraints(driver)

    doc_count = sym_count = occ_count = rel_count = 0

    # ---- 1. Documents -------------------------------------------------------
    doc_batch = [
        {"path": doc.relative_path, "repo": repo_name, "language": doc.language}
        for doc in index.documents
    ]
    _batch_write(
        driver,
        "UNWIND $rows AS r "
        "MERGE (d:Document {path: r.path, repo: r.repo}) "
        "SET d.language = r.language",
        doc_batch,
    )
    doc_count = len(doc_batch)
    logger.debug("Stored {} document nodes.", doc_count)

    # ---- 2. Symbols (with kind and method metadata) -------------------------
    sym_batch: list[dict[str, Any]] = []
    for doc in index.documents:
        for sym in doc.symbols:
            if sym.symbol:
                is_method = _is_method_symbol(sym.symbol)
                sym_batch.append({
                    "id": sym.symbol,
                    "kind": sym.kind,
                    "kind_name": sym.kind_name,
                    "language": doc.language,
                    "repo": repo_name,
                    "is_method": is_method,
                    # Use the document's language for language-aware noise detection
                    "is_noise": is_method and _is_noise_method(sym.symbol, doc.language),
                    "method_name": _method_name_from_id(sym.symbol) if is_method else "",
                })
    _batch_write(
        driver,
        "UNWIND $rows AS r "
        "MERGE (s:Symbol {id: r.id}) "
        "SET s.kind = r.kind, s.kind_name = r.kind_name, "
        "    s.language = r.language, s.repo = r.repo, "
        "    s.is_method = r.is_method, s.is_noise = r.is_noise, "
        "    s.method_name = r.method_name",
        sym_batch,
    )
    sym_count = len(sym_batch)
    logger.debug("Stored {} symbol nodes.", sym_count)

    # ---- 3. Symbol → Document edges (DEFINED_IN / REFERENCED_IN) -----------
    def_batch: list[dict[str, Any]] = []
    ref_batch: list[dict[str, Any]] = []

    for doc in index.documents:
        for occ in doc.occurrences:
            if not occ.symbol:
                continue
            entry = {"sym": occ.symbol, "path": doc.relative_path, "repo": repo_name}
            if occ.is_definition:
                def_batch.append(entry)
            else:
                ref_batch.append(entry)

    _batch_write(
        driver,
        "UNWIND $rows AS r "
        "MERGE (s:Symbol {id: r.sym}) "
        "WITH s, r "
        "MATCH (d:Document {path: r.path, repo: r.repo}) "
        "MERGE (s)-[:DEFINED_IN]->(d)",
        def_batch,
    )
    _batch_write(
        driver,
        "UNWIND $rows AS r "
        "MERGE (s:Symbol {id: r.sym}) "
        "WITH s, r "
        "MATCH (d:Document {path: r.path, repo: r.repo}) "
        "MERGE (s)-[:REFERENCED_IN]->(d)",
        ref_batch,
    )
    occ_count = len(def_batch) + len(ref_batch)
    logger.debug("Stored {} occurrence edges.", occ_count)

    # ---- 4. Symbol → Symbol RELATES_TO (from SymbolInfo.relationships) -----
    rel_batch: list[dict[str, Any]] = []
    for doc in index.documents:
        for sym in doc.symbols:
            if not sym.symbol:
                continue
            for rel in sym.relationships:
                if rel.symbol:
                    rel_batch.append({
                        "from_id": sym.symbol,
                        "to_id": rel.symbol,
                        "kind": _rel_kind(rel),
                    })
    _batch_write(
        driver,
        "UNWIND $rows AS r "
        "MERGE (s1:Symbol {id: r.from_id}) "
        "MERGE (s2:Symbol {id: r.to_id}) "
        "MERGE (s1)-[:RELATES_TO {kind: r.kind}]->(s2)",
        rel_batch,
    )
    rel_count = len(rel_batch)
    logger.debug("Stored {} symbol relationships.", rel_count)

    # ---- 5. Method-level CALLS edges (from occurrence ranges) ---------------
    call_stats = store_method_calls(driver, index, repo_name)
    logger.info(
        "store_scip_index complete: docs={} syms={} occs={} rels={} calls={}",
        doc_count, sym_count, occ_count, rel_count, call_stats["call_edges"],
    )

    return {
        "documents": doc_count,
        "symbols": sym_count,
        "occurrences": occ_count,
        "relationships": rel_count,
        "call_edges": call_stats["call_edges"],
    }


def store_method_calls(driver: "Driver", index: ScipIndex, repo_name: str) -> dict[str, int]:
    """Build method-level call graph from SCIP occurrence positions.

    For each non-test document in the index:

    1. Collects all callable *definition* occurrences, sorted by line number.
    2. For each callable *reference* occurrence, uses binary search to find the
       enclosing definition (the caller).
    3. Accumulates ``(caller, callee)`` call counts and writes them to Neo4j
       as ``(:Symbol)-[:CALLS {weight}]->(:Symbol)`` edges.

    SCIP ranges from scip-java are **absolute** coordinates (not delta-encoded).
    Range format: ``[start_line, start_col, end_col]`` or the 4-element form
    ``[start_line, start_col, end_line, end_col]``.

    Args:
        driver:    Connected Neo4j driver.
        index:     Parsed SCIP index.
        repo_name: Unused directly; kept for API consistency.

    Returns:
        Dict with ``call_edges`` count.
    """
    from collections import defaultdict

    call_counts: dict[tuple[str, str], int] = defaultdict(int)

    for doc in index.documents:
        path = doc.relative_path
        if not path or _is_test_file(path):
            continue

        # Collect callable definitions sorted by start line
        method_defs: list[tuple[int, str]] = []
        for occ in doc.occurrences:
            if (
                occ.is_definition
                and occ.symbol
                and not occ.symbol.startswith("local")
                and _is_method_symbol(occ.symbol)
                and occ.range
            ):
                method_defs.append((occ.range[0], occ.symbol))

        if not method_defs:
            continue

        method_defs.sort(key=lambda x: x[0])
        method_lines = [ln for ln, _ in method_defs]

        # Map each reference to its enclosing callable (= caller)
        for occ in doc.occurrences:
            if (
                occ.is_definition
                or not occ.symbol
                or occ.symbol.startswith("local")
                or not _is_method_symbol(occ.symbol)
                or not occ.range
            ):
                continue

            ref_line = occ.range[0]
            idx = bisect.bisect_right(method_lines, ref_line) - 1
            if idx < 0:
                continue

            caller = method_defs[idx][1]
            callee = occ.symbol
            if caller != callee:
                call_counts[(caller, callee)] += 1

    # Persist CALLS edges
    edge_batch = [
        {"caller": caller, "callee": callee, "weight": weight}
        for (caller, callee), weight in call_counts.items()
    ]
    _batch_write(
        driver,
        "UNWIND $rows AS r "
        "MERGE (s1:Symbol {id: r.caller}) "
        "MERGE (s2:Symbol {id: r.callee}) "
        "MERGE (s1)-[c:CALLS]->(s2) "
        "SET c.weight = r.weight",
        edge_batch,
    )
    logger.info("Stored {} method CALLS edges.", len(edge_batch))
    return {"call_edges": len(edge_batch)}


def _batch_write(driver: "Driver", cypher: str, rows: list[dict]) -> None:
    """Execute *cypher* with UNWIND in chunks of :data:`_BATCH` rows."""
    if not rows:
        return
    with driver.session() as session:
        for i in range(0, len(rows), _BATCH):
            chunk = rows[i: i + _BATCH]
            session.execute_write(lambda tx, c=chunk: tx.run(cypher, rows=c))


def _rel_kind(rel: Any) -> str:
    if rel.is_type_definition:
        return "type_definition"
    if rel.is_implementation:
        return "implementation"
    if rel.is_reference:
        return "reference"
    return "unknown"


# ---------------------------------------------------------------------------
# Community detection
# ---------------------------------------------------------------------------


def find_communities(
    driver: "Driver",
    repo_name: str,
    *,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Detect clusters of tightly-coupled callables using the Louvain algorithm.

    Builds a directed call graph from ``CALLS`` edges between Symbol nodes,
    removes noise callables **before** running Louvain on the undirected
    projection, then writes ``community_id`` back to every Symbol node.

    Falls back to ``RELATES_TO`` edges if no ``CALLS`` edges are found (e.g.
    for repos indexed with scip-python / scip-typescript that emit relationship
    metadata rather than call-site occurrence data).

    Args:
        driver:      Connected Neo4j driver.
        repo_name:   Repository name used to scope the query.
        output_path: If given, write community JSON to this file path.

    Returns:
        Summary dict with ``num_communities``, ``total_symbols``, and a list
        of community descriptors (id, size, top_entrypoint, sample_symbols).
    """
    with driver.session() as session:
        # Prefer CALLS edges (built by store_method_calls)
        calls_result = session.run(
            "MATCH (s1:Symbol)-[:CALLS]->(s2:Symbol) "
            "WHERE s1.repo = $repo AND s2.repo = $repo "
            "RETURN s1.id AS a, s2.id AS b",
            repo=repo_name,
        )
        edges = [(r["a"], r["b"]) for r in calls_result if r["a"] and r["b"]]

        if not edges:
            # Fallback: RELATES_TO (scip-python / scip-typescript)
            rel_result = session.run(
                "MATCH (s1:Symbol)-[:RELATES_TO]-(s2:Symbol) "
                "WHERE s1.repo = $repo AND s2.repo = $repo "
                "RETURN s1.id AS a, s2.id AS b",
                repo=repo_name,
            )
            edges = [(r["a"], r["b"]) for r in rel_result if r["a"] and r["b"]]

        sym_result = session.run(
            "MATCH (s:Symbol) WHERE s.repo = $repo "
            "RETURN s.id AS id, s.is_noise AS is_noise",
            repo=repo_name,
        )
        sym_meta = {
            r["id"]: {"is_noise": bool(r["is_noise"])}
            for r in sym_result
            if r["id"]
        }

    if not edges and not sym_meta:
        return {"error": "No symbols found for repo", "num_communities": 0}

    # Build graph excluding noise nodes — critical for clean Louvain clustering
    G = nx.DiGraph()
    for sid, meta in sym_meta.items():
        if not meta["is_noise"]:
            G.add_node(sid)
    for a, b in edges:
        if a in G and b in G:
            G.add_edge(a, b)

    logger.info(
        "Community detection graph: {} nodes, {} edges (noise excluded)",
        G.number_of_nodes(),
        G.number_of_edges(),
    )

    # Louvain on undirected projection, connected nodes only
    UG = G.to_undirected()
    connected_nodes = [n for n in UG.nodes if UG.degree(n) > 0]
    communities: list[set] = []
    if connected_nodes:
        subgraph = UG.subgraph(connected_nodes)
        communities = list(nx_comm.louvain_communities(subgraph, seed=42))
        communities.sort(key=len, reverse=True)

    logger.info("Found {} communities.", len(communities))

    # Write community_id back to Neo4j
    id_community: list[dict[str, Any]] = [
        {"id": node_id, "community_id": cid}
        for cid, nodes in enumerate(communities)
        for node_id in nodes
    ]
    _batch_write(
        driver,
        "UNWIND $rows AS r "
        "MATCH (s:Symbol {id: r.id}) "
        "SET s.community_id = r.community_id",
        id_community,
    )

    # Build community summary with top entrypoint per community
    in_deg = dict(G.in_degree())
    out_deg = dict(G.out_degree())

    summary: list[dict[str, Any]] = []
    for cid, c in enumerate(communities[:20]):
        roots = [n for n in c if in_deg.get(n, 0) == 0 and out_deg.get(n, 0) > 0]
        top = max(roots, key=lambda n: out_deg.get(n, 0)) if roots else None
        summary.append({
            "id": cid,
            "size": len(c),
            "top_entrypoint": _short_sym(top) if top else None,
            "sample_symbols": _shorten_symbols(
                [_short_sym(n) for n in sorted(c, key=lambda n: -out_deg.get(n, 0))[:5]]
            ),
        })

    result_data: dict[str, Any] = {
        "num_communities": len(communities),
        "total_symbols": G.number_of_nodes(),
        "communities": summary,
    }

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(
            json.dumps(result_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("Community data written to '{}'.", output_path)

    return result_data


# ---------------------------------------------------------------------------
# Entrypoint extraction
# ---------------------------------------------------------------------------


def extract_entrypoints(
    driver: "Driver",
    repo_name: str,
    *,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Identify root callables (entrypoints) from the method call graph.

    An entrypoint is a callable with ``in_degree=0`` in the ``CALLS`` graph —
    nothing in the analysed codebase calls it, so it must be invoked
    externally (HTTP framework, scheduler, event bus, test runner, etc.).

    The result is a flat list of ``root_methods`` sorted by ``out_degree``
    descending (methods that orchestrate the most work appear first).
    Language- or framework-specific interpretation is left to the caller.

    Noise callables (language-specific boilerplate such as ``toString``,
    ``__init__``, ``constructor``) are excluded using the ``is_noise``
    property stored on Symbol nodes during indexing.

    Also returns a per-community summary with each community's top
    entrypoint (in_degree=0 callable with the highest out_degree).

    Args:
        driver:      Connected Neo4j driver.
        repo_name:   Repository name used to scope the query.
        output_path: If given, serialise result to this JSON file path.

    Returns:
        Dict with ``root_methods``, ``communities``, ``total_methods``,
        ``total_call_edges``.
    """
    with driver.session() as session:
        sym_result = session.run(
            "MATCH (s:Symbol) WHERE s.repo = $repo AND s.is_method = true "
            "OPTIONAL MATCH (s)-[:DEFINED_IN]->(d:Document) "
            "RETURN s.id AS id, s.is_noise AS is_noise, "
            "       s.community_id AS community_id, d.path AS file_path",
            repo=repo_name,
        )
        symbols: dict[str, dict[str, Any]] = {
            r["id"]: {
                "file_path": r["file_path"] or "",
                "is_noise": bool(r["is_noise"]),
                "community_id": r["community_id"],
            }
            for r in sym_result
            if r["id"]
        }

        call_result = session.run(
            "MATCH (s1:Symbol)-[:CALLS]->(s2:Symbol) "
            "WHERE s1.repo = $repo AND s2.repo = $repo "
            "RETURN s1.id AS caller, s2.id AS callee",
            repo=repo_name,
        )
        call_edges = [(r["caller"], r["callee"]) for r in call_result]

    # Build directed graph from non-noise callables only
    G = nx.DiGraph()
    for sid, info in symbols.items():
        if not info["is_noise"]:
            G.add_node(sid, **info)
    for caller, callee in call_edges:
        if caller in G and callee in G:
            G.add_edge(caller, callee)

    in_deg = dict(G.in_degree())
    out_deg = dict(G.out_degree())

    # Root callables: in_degree=0, out_degree>0 (called only from outside)
    root_methods: list[dict[str, Any]] = []
    for node in sorted(G.nodes, key=lambda n: -out_deg.get(n, 0)):
        if in_deg.get(node, 0) != 0 or out_deg.get(node, 0) == 0:
            continue
        root_methods.append({
            "symbol": node,
            "short_name": _short_sym(node),
            "method_name": _method_name_from_id(node),
            "container_name": _class_name_from_id(node),
            "file": symbols[node]["file_path"],
            "out_degree": out_deg[node],
            "community_id": symbols[node].get("community_id"),
        })

    # Per-community summary with top entrypoint
    community_map: dict[int, list[str]] = {}
    for sid in G.nodes:
        cid = symbols[sid].get("community_id")
        if cid is not None:
            community_map.setdefault(int(cid), []).append(sid)

    communities_out: list[dict[str, Any]] = []
    for cid, members in sorted(community_map.items()):
        roots = [n for n in members if in_deg.get(n, 0) == 0 and out_deg.get(n, 0) > 0]
        top = max(roots, key=lambda n: out_deg.get(n, 0)) if roots else None
        communities_out.append({
            "community_id": cid,
            "size": len(members),
            "top_entrypoint": _short_sym(top) if top else None,
            "members": [
                _short_sym(n)
                for n in sorted(members, key=lambda n: -out_deg.get(n, 0))[:10]
            ],
        })

    result: dict[str, Any] = {
        "root_methods": root_methods,
        "communities": communities_out,
        "total_methods": G.number_of_nodes(),
        "total_call_edges": G.number_of_edges(),
    }

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("Entrypoints written to '{}'.", output_path)

    return result


# ---------------------------------------------------------------------------
# Generic Cypher query
# ---------------------------------------------------------------------------


def query_neo4j(driver: "Driver", cypher: str, params: dict | None = None) -> list[dict]:
    """Execute a read-only Cypher query and return rows as dicts.

    Args:
        driver: Connected Neo4j driver.
        cypher: Cypher query string.
        params: Optional parameter dict.

    Returns:
        List of result row dicts.
    """
    with driver.session() as session:
        result = session.run(cypher, **(params or {}))
        return [dict(r) for r in result]


# ---------------------------------------------------------------------------
# Purge helpers
# ---------------------------------------------------------------------------


def purge_repo(driver: "Driver", repo_name: str) -> dict[str, int]:
    """Delete all nodes and relationships for *repo_name*.

    Useful for re-indexing a repository from scratch.
    """
    with driver.session() as session:
        r1 = session.run(
            "MATCH (d:Document {repo: $repo}) "
            "DETACH DELETE d "
            "RETURN count(d) AS n",
            repo=repo_name,
        )
        docs_deleted = r1.single()["n"]

        r2 = session.run(
            "MATCH (s:Symbol {repo: $repo}) "
            "DETACH DELETE s "
            "RETURN count(s) AS n",
            repo=repo_name,
        )
        syms_deleted = r2.single()["n"]

    return {"documents_deleted": docs_deleted, "symbols_deleted": syms_deleted}
