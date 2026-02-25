"""SBOM tools for use with the SBOMAgent.

Each tool is decorated with ``@tool`` so it can be bound directly to a
LangChain/LangGraph ReAct agent.

SBOM generation is delegated to the ``cdxgen`` CLI, which must be installed.
See https://cyclonedx.github.io/cdxgen for installation instructions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool

from src.core.logging import get_logger
from src.core.process import run_command
from src.core.project import get_project_config

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Project-type detection
# ---------------------------------------------------------------------------

# Ordered list of (indicator_files_or_globs, cdxgen_type).
# Earlier entries take priority. Glob patterns (containing "*") are matched
# against the root directory; plain names are checked with Path.exists().
_PROJECT_TYPE_INDICATORS: list[tuple[tuple[str, ...], str]] = [
    (("pom.xml", "mvnw", ".mvn"), "java"),
    (("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "gradlew"), "java"),
    (("package.json",), "js"),
    (("pyproject.toml", "setup.py", "requirements.txt", "Pipfile"), "python"),
    (("go.mod",), "go"),
    (("Cargo.toml",), "rust"),
    (("Gemfile",), "ruby"),
    (("*.csproj", "*.sln"), "dotnet"),
]


def _detect_project_type(root: Path) -> str:
    """Infer the cdxgen ``-t`` type from build/manifest files in *root*.

    Checks indicator files in priority order so that the primary source
    language takes precedence over tooling metadata such as
    ``.github/workflows/``.

    Returns:
        A cdxgen-compatible type string (e.g. ``"java"``, ``"python"``),
        or ``""`` if no known indicator is found.
    """
    for indicators, project_type in _PROJECT_TYPE_INDICATORS:
        for indicator in indicators:
            if "*" in indicator:
                if any(root.glob(indicator)):
                    return project_type
            elif (root / indicator).exists():
                return project_type
    return ""


def create_sbom_tools(project_path: str, repo_name: str) -> list:
    """Create SBOM tools pinned to *project_path*.

    Tools operate within the configured project directory so the LLM cannot
    accidentally run cdxgen against the wrong path.

    Args:
        project_path: Absolute or relative path to the project directory.
        repo_name: Repository name used to derive the agent_output sub-directory.

    Returns:
        List of LangChain tools ready to be bound to an agent.
    """
    _project_path = str(Path(project_path).resolve())
    cfg = get_project_config()
    _repo_out = cfg.repo_output_dir(repo_name)
    _default_sbom = str(_repo_out / "sbom.json")

    @tool
    def generate_sbom(
        output_path: Annotated[
            str,
            "Output path for the SBOM file. Leave empty to use the default path under agent_output/.",
        ] = "",
    ) -> str:
        """Generate a CycloneDX SBOM for the project using ``cdxgen``.

        Runs ``cdxgen -o <output_path> <project_path>`` and writes the SBOM as
        JSON.  The SBOM captures all detected dependencies and their metadata.
        Do NOT pass an explicit output_path unless instructed — the default
        writes to agent_output/repos/{repo}/sbom.json.

        The project type (e.g. java, python, js) is detected automatically
        from build files in the project directory.
        """
        out = output_path or _default_sbom
        project_type = _detect_project_type(Path(_project_path))
        logger.debug(
            "generate_sbom: project={!r} output={!r} detected_type={!r}",
            _project_path, out, project_type or "(auto)",
        )
        extra_args = ["-t", project_type] if project_type else []
        run_command("cdxgen", "--json-pretty", *extra_args, "-o", out, _project_path)
        return f"SBOM generated at '{out}'."

    @tool
    def list_application_components(
        sbom_path: Annotated[
            str,
            "Path to the SBOM JSON file. Leave empty to use the default path under agent_output/.",
        ] = "",
    ) -> str:
        """List top-level executable components (type=application) from the SBOM.

        Scans the root component (``metadata.component``) and its direct children
        (``metadata.component.components``) for entries classified as
        ``"type": "application"``.  Tool components recorded under
        ``metadata.tools`` are intentionally excluded.
        """
        path = sbom_path or _default_sbom
        logger.debug("list_application_components: path={!r}", path)
        if not Path(path).exists():
            return f"SBOM file not found at '{path}'. Run generate_sbom first."
        data = json.loads(Path(path).read_text(encoding="utf-8"))

        root = data.get("metadata", {}).get("component", {})
        candidates: list[dict] = []
        if root:
            candidates.append(root)
            candidates.extend(root.get("components", []))

        apps = [c for c in candidates if c.get("type") == "application"]
        if not apps:
            return "No application-type components found in SBOM."

        lines: list[str] = [f"Found {len(apps)} application component(s):"]
        for c in apps:
            name = c.get("name", "?")
            version = c.get("version", "N/A")
            purl = c.get("purl", "")
            line = f"- {name}@{version}"
            if purl:
                line += f"  ({purl})"
            lines.append(line)
        return "\n".join(lines)

    @tool
    def generate_component_sboms(
        sbom_path: Annotated[
            str,
            "Path to the root SBOM JSON file. Leave empty to use the default path under agent_output/.",
        ] = "",
    ) -> str:
        """Extract individual CycloneDX SBOMs for each sub-module from the root SBOM.

        Gradle multi-project builds require the root project context to resolve
        dependencies, so running cdxgen on a sub-module directory in isolation
        produces an empty SBOM.  This tool instead reads the already-generated root
        SBOM and walks the dependency graph to collect every transitive dependency
        for each application sub-module, then writes a fully-populated
        agent_output/repos/{repo}/components/{name}/sbom.json for each one.
        """
        path = sbom_path or _default_sbom
        logger.debug("generate_component_sboms: sbom_path={!r}", path)
        if not Path(path).exists():
            return f"SBOM file not found at '{path}'. Run generate_sbom first."
        data = json.loads(Path(path).read_text(encoding="utf-8"))

        root = data.get("metadata", {}).get("component", {})
        sub_modules = [c for c in root.get("components", []) if c.get("type") == "application"]
        if not sub_modules:
            return "No sub-module application components found in SBOM."

        # bom-ref → component object (library components only)
        ref_to_comp: dict[str, dict] = {c["bom-ref"]: c for c in data.get("components", [])}

        # ref → dependsOn list
        dep_map: dict[str, list[str]] = {
            d["ref"]: d.get("dependsOn", [])
            for d in data.get("dependencies", [])
        }

        sub_module_refs = {c["bom-ref"] for c in sub_modules}

        def collect_transitive(start_ref: str) -> set[str]:
            """BFS over dep_map to collect all transitive dependency refs."""
            visited: set[str] = set()
            queue = list(dep_map.get(start_ref, []))
            while queue:
                ref = queue.pop()
                if ref in visited:
                    continue
                visited.add(ref)
                queue.extend(dep_map.get(ref, []))
            return visited

        results: list[str] = []
        for comp in sub_modules:
            name = comp.get("name", "?")
            bom_ref = comp.get("bom-ref", "")

            transitive_refs = collect_transitive(bom_ref)
            # Exclude other sub-modules; include only library/framework components
            lib_refs = transitive_refs - sub_module_refs
            transitive_components = [ref_to_comp[r] for r in lib_refs if r in ref_to_comp]

            all_refs = {bom_ref} | transitive_refs
            sub_deps = [
                d for d in data.get("dependencies", []) if d["ref"] in all_refs
            ]

            component_sbom = {
                "bomFormat": data.get("bomFormat", "CycloneDX"),
                "specVersion": data.get("specVersion", "1.6"),
                "version": 1,
                "metadata": {**data.get("metadata", {}), "component": comp},
                "components": transitive_components,
                "services": [],
                "dependencies": sub_deps,
            }

            comp_dir = cfg.component_dir(repo_name, name)
            out_path = comp_dir / "sbom.json"
            out_path.write_text(
                json.dumps(component_sbom, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.debug(
                "generate_component_sboms: wrote {!r} ({} components)", str(out_path), len(transitive_components)
            )
            results.append(
                f"- {name}: {len(transitive_components)} components -> '{out_path}'."
            )

        return "\n".join(results)

    @tool
    def get_application_dependencies(
        component_name: Annotated[
            str,
            "Application component name to look up. Leave empty to return dependencies for all components.",
        ] = "",
    ) -> str:
        """Return dependency PURLs for one or all application sub-modules.

        Reads the per-component sbom.json files produced by generate_component_sboms
        and returns a compact JSON object mapping component name to a sorted list of
        dependency PURLs.  Run generate_component_sboms first if the files do not exist.
        """
        logger.debug("get_application_dependencies: component_name={!r}", component_name)

        if component_name:
            names = [component_name]
        else:
            comp_root = _repo_out / "components"
            if not comp_root.exists():
                return "No component SBOMs found. Run generate_component_sboms first."
            names = [p.name for p in comp_root.iterdir() if (p / "sbom.json").exists()]
            if not names:
                return "No component SBOMs found. Run generate_component_sboms first."

        result: dict[str, list[str]] = {}
        for name in sorted(names):
            comp_sbom_path = cfg.component_dir(repo_name, name) / "sbom.json"
            if not comp_sbom_path.exists():
                result[name] = [f"ERROR: not found. Run generate_component_sboms first."]
                continue
            comp_data = json.loads(comp_sbom_path.read_text(encoding="utf-8"))
            result[name] = sorted(
                c["purl"] for c in comp_data.get("components", []) if c.get("purl")
            )

        return json.dumps(result, ensure_ascii=False)

    return [generate_sbom, list_application_components, generate_component_sboms, get_application_dependencies]
