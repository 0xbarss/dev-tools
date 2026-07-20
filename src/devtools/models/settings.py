"""Pydantic models for ~/.config/devtools/config.toml."""

from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_IGNORED_DIRS = [".git", "node_modules", ".venv", "build", "dist"]


class ProjectOverride(BaseModel):
    ignored_dirs: list[str] = Field(default_factory=list)


class Settings(BaseModel):
    output_format: str = "markdown"
    max_bundle_size: str = "10MB"
    theme: str = "dark"
    allow_network: bool = False
    default_project: str | None = None

    ignored_dirs: list[str] = Field(default_factory=lambda: list(DEFAULT_IGNORED_DIRS))
    project_overrides: dict[str, ProjectOverride] = Field(default_factory=dict)

    def ignored_dirs_for(self, project_name: str | None) -> list[str]:
        """ignored_dirs is additive: global list + that project's overrides."""
        combined = list(self.ignored_dirs)
        if project_name and project_name in self.project_overrides:
            combined.extend(self.project_overrides[project_name].ignored_dirs)
        return combined

    model_config = {"extra": "allow"}
