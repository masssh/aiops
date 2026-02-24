"""RepoMap tools: Tree-sitter AST parsing + PageRank-based repository map generation.

Provides a factory function ``create_repomap_tools`` that returns a single
``generate_repomap`` LangChain tool scoped to a specific repository directory.

The tool combines two techniques:

1. **Tree-sitter AST parsing** – extracts top-level class definitions,
   function definitions, and import statements from Python source files.
2. **NetworkX PageRank** – builds a directed import-dependency graph across
   all Python files and ranks each file by its structural importance.

The resulting map is a plain-text directory tree where the top-N most important
files are expanded to show their symbols; less important files show only their
path.  The map is written to ``agent_output/repos/{repo_name}/repomap.txt``.
"""

from __future__ import annotations

import fnmatch
import importlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import networkx as nx
from langchain_core.tools import tool

from src.core.logging import get_logger
from src.core.project import get_project_config

logger = get_logger(__name__)

# Absolute path to the aiops project root (parent of src/).
_AIOPS_ROOT: Path = Path(__file__).parent.parent.parent.parent.resolve()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        "venv",
        ".venv",
        "env",
        ".env",
        "node_modules",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "dist",
        "build",
        ".tox",
        ".eggs",
    }
)

_TOP_N_DEFAULT: int = 10

# ---------------------------------------------------------------------------
# Internal helpers – file discovery
# ---------------------------------------------------------------------------


def _load_ignore_patterns(*roots: Path) -> frozenset[str]:
    """Load extra ignore patterns from ``.repomapignore`` files.

    Searches for ``.repomapignore`` in each directory supplied as *roots*
    and merges all patterns found.  Patterns from later roots take no
    precedence — all are union-merged.

    The aiops project root is always consulted first (global config), followed
    by the target directory being mapped (local, per-repo config).

    Each non-blank, non-comment line is treated as a pattern matched against
    file/directory *names* (not full paths) using ``fnmatch`` rules.

    Args:
        *roots: Directories in which to look for ``.repomapignore``.

    Returns:
        Frozenset of pattern strings, empty if no files are found.
    """
    patterns: set[str] = set()
    for root in roots:
        ignore_file = root / ".repomapignore"
        if not ignore_file.exists():
            continue
        for line in ignore_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.add(line)
        logger.debug("Loaded ignore patterns from {}", ignore_file)
    if patterns:
        logger.debug("Active ignore patterns: {}", sorted(patterns))
    return frozenset(patterns)


def _should_ignore(name: str, extra: frozenset[str] = frozenset()) -> bool:
    """Return True if the directory or file name should be skipped during traversal.

    Args:
        name:  Bare file or directory name (not a full path).
        extra: Additional patterns loaded from ``.repomapignore``.
    """
    if name in _IGNORED_DIRS or name.endswith(".egg-info"):
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in extra)


def _collect_files(root: Path, extra: frozenset[str] = frozenset()) -> list[Path]:
    """Recursively collect all files under *root*, excluding ignored directories.

    Args:
        root:  Absolute path to the root directory to traverse.
        extra: Additional ignore patterns from ``.repomapignore``.

    Returns:
        Sorted list of absolute file paths found under *root*.
    """
    files: list[Path] = []
    for dirpath_str, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not _should_ignore(d, extra))
        dirpath = Path(dirpath_str)
        for fname in sorted(filenames):
            files.append(dirpath / fname)
    return files


# ---------------------------------------------------------------------------
# Internal helpers – multi-language Tree-sitter support
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _LangConfig:
    """Tree-sitter node-type configuration for a single language.

    Attributes:
        class_nodes:      Node types that represent class-like definitions
                          (class, interface, enum, record, object, …).
        func_nodes:       Node types that represent callable definitions
                          (function, method, constructor, …).
        name_child_types: Child node types that carry the definition name
                          (identifier, simple_identifier, property_identifier, …).
        wrapper_nodes:    Top-level wrapper nodes whose children should also be
                          inspected (e.g. ``export_statement`` in TypeScript/JS,
                          ``decorated_definition`` in Python).
    """

    class_nodes: tuple[str, ...]
    func_nodes: tuple[str, ...]
    name_child_types: tuple[str, ...]
    wrapper_nodes: tuple[str, ...] = ()


_PY_CONFIG = _LangConfig(
    class_nodes=("class_definition",),
    func_nodes=("function_definition",),
    name_child_types=("identifier",),
    wrapper_nodes=("decorated_definition",),
)

_JAVA_CONFIG = _LangConfig(
    class_nodes=(
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
    ),
    func_nodes=("method_declaration", "constructor_declaration"),
    name_child_types=("identifier",),
)

_KOTLIN_CONFIG = _LangConfig(
    class_nodes=("class_declaration", "object_declaration", "interface_declaration"),
    func_nodes=("function_declaration",),
    name_child_types=("simple_identifier", "type_identifier"),
)

_TS_JS_CONFIG = _LangConfig(
    class_nodes=("class_declaration",),
    func_nodes=("function_declaration", "method_definition"),
    name_child_types=("identifier", "property_identifier", "type_identifier"),
    wrapper_nodes=("export_statement",),
)

# Extension → (pip module name, language-getter function name or None, config)
_EXT_REGISTRY: dict[str, tuple[str, str | None, _LangConfig]] = {
    ".py":  ("tree_sitter_python",     None,                  _PY_CONFIG),
    ".java":("tree_sitter_java",       None,                  _JAVA_CONFIG),
    ".kt":  ("tree_sitter_kotlin",     None,                  _KOTLIN_CONFIG),
    ".kts": ("tree_sitter_kotlin",     None,                  _KOTLIN_CONFIG),
    ".ts":  ("tree_sitter_typescript", "language_typescript", _TS_JS_CONFIG),
    ".tsx": ("tree_sitter_typescript", "language_tsx",        _TS_JS_CONFIG),
    ".js":  ("tree_sitter_javascript", None,                  _TS_JS_CONFIG),
    ".jsx": ("tree_sitter_javascript", None,                  _TS_JS_CONFIG),
    ".mjs": ("tree_sitter_javascript", None,                  _TS_JS_CONFIG),
}

# Module-level cache: populated once on first call to _load_parsers().
_parser_cache: dict[str, tuple[object, _LangConfig]] = {}


def _load_parsers() -> dict[str, tuple[object, _LangConfig]]:
    """Return extension → (Parser, LangConfig) for every installed language package.

    Results are cached after the first call.  Language packages that are not
    installed are silently skipped.

    Returns:
        Dict keyed by file extension (e.g. ``".py"``) mapping to a
        ``(Parser, _LangConfig)`` pair.
    """
    if _parser_cache:
        return _parser_cache

    try:
        from tree_sitter import Language, Parser  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("tree-sitter core not installed; symbol extraction disabled")
        return _parser_cache

    for ext, (module_name, lang_func, config) in _EXT_REGISTRY.items():
        try:
            mod = importlib.import_module(module_name)
            fn = getattr(mod, lang_func) if lang_func else getattr(mod, "language")
            language = Language(fn())
            try:
                parser: object = Parser(language)      # tree-sitter >= 0.23
            except TypeError:
                parser = Parser()                       # type: ignore[call-arg]
                parser.set_language(language)           # type: ignore[attr-defined]
            _parser_cache[ext] = (parser, config)
            logger.debug("Loaded tree-sitter parser for {}", ext)
        except Exception as exc:
            logger.debug("tree-sitter parser unavailable for {}: {}", ext, exc)

    if _parser_cache:
        logger.debug("Active tree-sitter parsers: {}", sorted(_parser_cache))
    return _parser_cache


def _extract_symbols(
    file_path: Path, parser: object, config: _LangConfig
) -> dict[str, list[str]]:
    """Extract top-level class/function names and (for Python) import paths.

    Only top-level (module-scope) definitions are returned.  For languages with
    ``wrapper_nodes`` (e.g. TypeScript ``export_statement``), one extra level of
    unwrapping is applied so that exported declarations are also captured.

    Args:
        file_path: Path to the source file.
        parser:    Initialised tree-sitter ``Parser`` for the file's language.
        config:    ``_LangConfig`` describing the node types for this language.

    Returns:
        Dictionary with keys ``"classes"``, ``"functions"``, and ``"imports"``.
        ``"imports"`` is populated only for Python files (used for PageRank).
    """
    try:
        source = file_path.read_bytes()
    except OSError as exc:
        logger.debug("Cannot read {}: {}", file_path, exc)
        return {"classes": [], "functions": [], "imports": []}

    try:
        tree = parser.parse(source)  # type: ignore[attr-defined]
    except Exception as exc:
        logger.debug("tree-sitter parse failed for {}: {}", file_path, exc)
        return {"classes": [], "functions": [], "imports": []}

    classes: list[str] = []
    functions: list[str] = []
    imports: list[str] = []
    is_python = file_path.suffix == ".py"

    for node in tree.root_node.children:
        # Unwrap transparent wrapper nodes one level deep
        # (export_statement, decorated_definition, …).
        inner = list(node.children) if node.type in config.wrapper_nodes else [node]

        for n in inner:
            if n.type in config.class_nodes:
                for child in n.children:
                    if child.type in config.name_child_types:
                        classes.append(child.text.decode("utf-8"))
                        break
            elif n.type in config.func_nodes:
                for child in n.children:
                    if child.type in config.name_child_types:
                        functions.append(child.text.decode("utf-8"))
                        break

        # Python-only: collect import module paths for the dependency graph.
        if is_python:
            if node.type == "import_statement":
                for child in node.children:
                    if child.type == "dotted_name":
                        imports.append(child.text.decode("utf-8"))
            elif node.type == "import_from_statement":
                for child in node.children:
                    if child.type in ("dotted_name", "relative_import"):
                        raw = child.text.decode("utf-8").lstrip(".")
                        if raw:
                            imports.append(raw)
                        break

    return {"classes": classes, "functions": functions, "imports": imports}


# ---------------------------------------------------------------------------
# Internal helpers – dependency graph & PageRank
# ---------------------------------------------------------------------------


def _pagerank(
    graph: nx.DiGraph,
    alpha: float = 0.85,
    max_iter: int = 100,
    tol: float = 1.0e-6,
) -> dict[str, float]:
    """Compute PageRank via pure-Python power iteration.

    This avoids a hard dependency on scipy (which networkx 3.x otherwise
    requires for its built-in ``nx.pagerank``).

    Args:
        graph:    Directed graph whose nodes are file path strings.
        alpha:    Damping factor (probability of following a link).
        max_iter: Maximum number of power-iteration steps.
        tol:      Convergence tolerance (L1 norm per node).

    Returns:
        Dictionary mapping node identifiers to their PageRank scores.
    """
    nodes = list(graph.nodes())
    n = len(nodes)
    if n == 0:
        return {}

    out_degree: dict[str, int] = {node: graph.out_degree(node) for node in nodes}  # type: ignore[assignment]
    rank: dict[str, float] = {node: 1.0 / n for node in nodes}

    for _ in range(max_iter):
        dangling_sum = sum(rank[node] for node in nodes if out_degree[node] == 0)
        new_rank: dict[str, float] = {}
        for node in nodes:
            incoming = sum(
                rank[pred] / out_degree[pred]
                for pred in graph.predecessors(node)
                if out_degree[pred] > 0
            )
            new_rank[node] = alpha * (incoming + dangling_sum / n) + (1.0 - alpha) / n

        err = sum(abs(new_rank[node] - rank[node]) for node in nodes)
        rank = new_rank
        if err < tol * n:
            break

    return rank


def _build_dependency_graph(
    root: Path,
    src_files: list[Path],
    symbols: dict[str, dict[str, list[str]]],
) -> nx.DiGraph:
    """Build a directed dependency graph from source files and Python import edges.

    All parseable source files become graph nodes.  Directed edges are added
    only for Python import relationships (the only language whose imports are
    resolved to local file paths).  Non-Python files therefore appear as
    dangling nodes and receive a uniform baseline PageRank score, which still
    allows the top-N selection to work in repositories with no Python code.

    Args:
        root:      Repository root directory.
        src_files: All parseable source file paths (nodes).
        symbols:   Mapping of relative-path strings to extracted symbol dicts.

    Returns:
        Directed ``networkx`` graph representing import dependencies.
    """
    graph: nx.DiGraph = nx.DiGraph()

    for f in src_files:
        graph.add_node(str(f.relative_to(root)))

    # Build a module-identifier → relative-file-path lookup for Python files.
    # e.g. "src/core/logging.py"  →  "src.core.logging"
    py_files = [f for f in src_files if f.suffix == ".py"]
    module_to_file: dict[str, str] = {}
    for f in py_files:
        rel = f.relative_to(root)
        parts = list(rel.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1][:-3]  # strip ".py"
        module_to_file[".".join(parts)] = str(f.relative_to(root))

    # Add edges from Python importer → imported
    for f in py_files:
        rel = str(f.relative_to(root))
        for imp in symbols.get(rel, {}).get("imports", []):
            target = module_to_file.get(imp)
            if target and target != rel:
                graph.add_edge(rel, target)

    return graph


# ---------------------------------------------------------------------------
# Internal helpers – tree formatting
# ---------------------------------------------------------------------------


def _render_tree(
    root: Path,
    symbols: dict[str, dict[str, list[str]]],
    top_files: set[str],
    extra: frozenset[str] = frozenset(),
) -> str:
    """Render the directory tree as a plain-text string.

    Files included in *top_files* are expanded to show their top-level classes
    and functions. All other files show only their name.

    Args:
        root:      Repository root directory.
        symbols:   Extracted symbols keyed by relative file path.
        top_files: Set of relative path strings to expand with symbols.
        extra:     Additional ignore patterns from ``.repomapignore``.

    Returns:
        Multi-line string representing the formatted repository map.
    """
    lines: list[str] = [f"{root.name}/"]

    def _render_entries(directory: Path, prefix: str) -> None:
        try:
            raw_entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return

        entries = [e for e in raw_entries if not _should_ignore(e.name, extra)]
        for idx, entry in enumerate(entries):
            is_last = idx == len(entries) - 1
            connector = "└──" if is_last else "├──"
            child_prefix = prefix + ("    " if is_last else "│   ")

            if entry.is_dir():
                lines.append(f"{prefix}{connector} {entry.name}/")
                _render_entries(entry, child_prefix)
            else:
                rel_path = str(entry.relative_to(root))
                lines.append(f"{prefix}{connector} {entry.name}")
                if rel_path in top_files:
                    file_syms = symbols.get(rel_path, {})
                    sym_entries: list[str] = [
                        f"class {c}:" for c in file_syms.get("classes", [])
                    ] + [f"def {fn}(...):" for fn in file_syms.get("functions", [])]
                    for sym_idx, sym in enumerate(sym_entries):
                        sym_is_last = sym_idx == len(sym_entries) - 1
                        sym_conn = "└──" if sym_is_last else "├──"
                        lines.append(f"{child_prefix}{sym_conn} {sym}")

    _render_entries(root, "")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def create_repomap_tools(project_path: str) -> list:
    """Create a ``generate_repomap`` tool scoped to *project_path*.

    The repository name is derived automatically from ``Path(project_path).name``
    and used to resolve the output directory:
    ``agent_output/repos/{repo_name}/repomap.txt``.

    Args:
        project_path: Absolute path to the repository directory to analyse.

    Returns:
        List containing a single LangChain tool, ``generate_repomap``.
    """
    _project_path = str(Path(project_path).resolve())
    _repo_name = Path(project_path).name
    cfg = get_project_config()
    _repo_out = cfg.repo_output_dir(_repo_name)
    _default_output = str(_repo_out / "repomap.txt")

    @tool
    def generate_repomap(
        root_dir: Annotated[
            str,
            "Directory to map. Absolute path or relative to project root. "
            "Leave empty to map the entire project directory.",
        ] = "",
        output_path: Annotated[
            str,
            "Output file path for the repomap. Leave empty to use the default "
            "path under agent_output/.",
        ] = "",
        top_n: Annotated[
            int,
            "Number of highest-ranked files to expand with class/function symbols. "
            "Default is 10.",
        ] = _TOP_N_DEFAULT,
    ) -> str:
        """Generate a token-optimised repository map and write it to a file.

        Do NOT pass an explicit output_path unless instructed by the user.

        Returns:
            Confirmation message with output path followed by the generated map.
        """
        # Resolve target directory.
        # Relative paths are resolved against CWD (the aiops project root),
        # matching the behaviour users expect when passing paths like
        # "./workspace/repos/my-project" from the command line.
        target = Path(root_dir).resolve() if root_dir else Path(_project_path)

        if not target.exists():
            return f"Error: directory '{target}' does not exist."
        if not target.is_dir():
            return f"Error: '{target}' is not a directory."

        out = Path(output_path) if output_path else Path(_default_output)

        logger.info("Generating repomap for {} -> {}", target, out)

        # --- Load .repomapignore ---
        # Global config (aiops root) is merged with local config (target dir).
        extra_patterns = _load_ignore_patterns(_AIOPS_ROOT, target)

        # --- File discovery ---
        all_files = _collect_files(target, extra_patterns)
        logger.debug("Discovered {} files total", len(all_files))

        # --- AST symbol extraction (all supported languages) ---
        parsers = _load_parsers()
        src_files = [f for f in all_files if f.suffix in parsers]
        symbols: dict[str, dict[str, list[str]]] = {}

        for f in src_files:
            parser, config = parsers[f.suffix]
            rel = str(f.relative_to(target))
            symbols[rel] = _extract_symbols(f, parser, config)

        if parsers:
            logger.debug(
                "Extracted symbols from {} source files (parsers: {})",
                len(src_files),
                sorted(parsers),
            )
        else:
            logger.warning(
                "No tree-sitter language packages available; "
                "install tree-sitter-python, tree-sitter-java, etc."
            )

        # --- Dependency graph + PageRank ---
        # Nodes = all source files; edges = Python import relationships.
        # Non-Python files are dangling nodes with uniform baseline score.
        top_files: set[str] = set()

        if src_files:
            graph = _build_dependency_graph(target, src_files, symbols)
            n_nodes = graph.number_of_nodes()
            n_edges = graph.number_of_edges()
            logger.debug("Dependency graph: {} nodes, {} edges", n_nodes, n_edges)

            if n_nodes > 0:
                pagerank = _pagerank(graph, alpha=0.85)
                ranked = sorted(pagerank.items(), key=lambda kv: kv[1], reverse=True)
                top_files = {rel for rel, _ in ranked[: max(top_n, 0)]}
                logger.debug(
                    "Top {} files by PageRank: {}", len(top_files), list(top_files)[:5]
                )

        # --- Tree rendering ---
        repomap = _render_tree(target, symbols, top_files, extra_patterns)

        # --- Persist to file ---
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(repomap, encoding="utf-8")
        line_count = repomap.count("\n") + 1
        logger.info("Repomap written to '{}' ({} lines)", out, line_count)

        return f"Repomap written to '{out}'.\n\n{repomap}"

    return [generate_repomap]
