"""YAML-based project configuration loader (singleton)."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator
from src.core.logging import get_logger

logger = get_logger(__name__)

_PROJECT_ROOT: Path = Path(__file__).parent.parent.parent.resolve()
_CONFIG_PATH: Path = _PROJECT_ROOT / "project.yaml"


class ProjectConfig(BaseModel):
    model_config = {"extra": "forbid"}
    workspace: Path

    @field_validator("workspace", mode="before")
    @classmethod
    def _resolve_workspace(cls, v: Any) -> Path:
        p = Path(str(v))
        if not p.is_absolute():
            p = _PROJECT_ROOT / p
        return p.resolve()


_config: ProjectConfig | None = None


def get_project_config() -> ProjectConfig:
    global _config
    if _config is not None:
        return _config

    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Required configuration file not found: {_CONFIG_PATH}\n"
            "Create 'project.yaml' at the project root."
        )

    with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}

    if "workspace" not in raw:
        raise ValueError(
            "project.yaml is missing required field 'workspace'.\n"
            "Add: workspace: /path/to/your/workspace"
        )

    _config = ProjectConfig(**raw)
    logger.info("Project workspace: {}", _config.workspace)
    return _config


def repo_name_from_url(url: str) -> str:
    """Extract bare repo name from any git remote URL."""
    url = url.rstrip("/")
    if ":" in url and not url.startswith("http"):
        url = url.split(":", 1)[1]
    return re.sub(r"\.git$", "", url.split("/")[-1])
