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
        """
        out = output_path or _default_sbom
        logger.debug("generate_sbom: project={!r} output={!r}", _project_path, out)
        run_command("cdxgen", "--json-pretty", "-o", out, _project_path)
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
    def get_application_dependencies(
        sbom_path: Annotated[
            str,
            "Path to the SBOM JSON file. Leave empty to use the default path under agent_output/.",
        ] = "",
    ) -> str:
        """Show direct dependencies for each application component in the SBOM.

        For every component classified as ``"type": "application"`` (root project
        and sub-modules), looks up its entry in the ``dependencies`` section and
        lists what it directly depends on, including the type of each dependency.
        """
        path = sbom_path or _default_sbom
        logger.debug("get_application_dependencies: path={!r}", path)
        if not Path(path).exists():
            return f"SBOM file not found at '{path}'. Run generate_sbom first."
        data = json.loads(Path(path).read_text(encoding="utf-8"))

        # Build bom-ref -> component lookup from all sources except tools
        ref_to_comp: dict[str, dict] = {}
        root = data.get("metadata", {}).get("component", {})
        if root:
            ref_to_comp[root["bom-ref"]] = root
            for child in root.get("components", []):
                ref_to_comp[child["bom-ref"]] = child
        for c in data.get("components", []):
            ref_to_comp[c["bom-ref"]] = c

        # Build ref -> dependsOn lookup from dependencies section
        dep_map: dict[str, list[str]] = {
            d["ref"]: d.get("dependsOn", [])
            for d in data.get("dependencies", [])
        }

        # Collect application components (root + direct children of root)
        candidates: list[dict] = []
        if root:
            candidates.append(root)
            candidates.extend(root.get("components", []))
        apps = [c for c in candidates if c.get("type") == "application"]

        if not apps:
            return "No application-type components found in SBOM."

        lines: list[str] = []
        for app in apps:
            name = app.get("name", "?")
            version = app.get("version", "N/A")
            lines.append(f"{name}@{version}")

            bom_ref = app.get("bom-ref", "")
            depends_on = dep_map.get(bom_ref, [])

            dep_components = [ref_to_comp.get(r, {"bom-ref": r}) for r in depends_on]
            dep_data = {"component": app, "dependencies": dep_components}
            comp_dir = cfg.component_dir(repo_name, name)
            (comp_dir / "dependencies.json").write_text(
                json.dumps(dep_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            if not depends_on:
                lines.append("  (no dependencies)")
            else:
                for i, dep_ref in enumerate(depends_on):
                    prefix = "  └─" if i == len(depends_on) - 1 else "  ├─"
                    dep = ref_to_comp.get(dep_ref)
                    if dep:
                        dep_name = dep.get("name", dep_ref)
                        dep_ver = dep.get("version", "N/A")
                        dep_type = dep.get("type", "?")
                        lines.append(f"{prefix} {dep_name}@{dep_ver}  [{dep_type}]")
                    else:
                        lines.append(f"{prefix} {dep_ref}  [unknown]")
            lines.append("")

        return "\n".join(lines).rstrip()

    return [generate_sbom, list_application_components, get_application_dependencies]
