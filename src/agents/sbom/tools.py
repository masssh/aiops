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

logger = get_logger(__name__)


def create_sbom_tools(project_path: str) -> list:
    """Create SBOM tools pinned to *project_path*.

    Tools operate within the configured project directory so the LLM cannot
    accidentally run cdxgen against the wrong path.

    Args:
        project_path: Absolute or relative path to the project directory.

    Returns:
        List of LangChain tools ready to be bound to an agent.
    """
    _project_path = str(Path(project_path).resolve())
    _default_sbom = str(Path(_project_path) / "sbom.json")

    @tool
    def generate_sbom(
        output_path: Annotated[
            str,
            "Output path for the SBOM file. Defaults to sbom.cdx.json inside the project directory.",
        ] = "",
    ) -> str:
        """Generate a CycloneDX SBOM for the project using ``cdxgen``.

        Runs ``cdxgen -o <output_path> <project_path>`` and writes the SBOM as
        JSON.  The SBOM captures all detected dependencies and their metadata.
        """
        out = output_path or _default_sbom
        logger.debug("generate_sbom: project={!r} output={!r}", _project_path, out)
        run_command("cdxgen", "-o", out, _project_path)
        return f"SBOM generated at '{out}'."

    @tool
    def list_application_components(
        sbom_path: Annotated[
            str,
            "Path to the SBOM JSON file. Defaults to sbom.json inside the project directory.",
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

    return [generate_sbom, list_application_components]
