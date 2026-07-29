"""Pydantic model for a single registered project (see projects.json)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, field_validator


class Project(BaseModel):
    name: str
    path: str
    last_collected: str | None = None
    cached_stats: dict | None = None

    @field_validator("path")
    @classmethod
    def _normalize_path(cls, v: str) -> str:
        return str(Path(v).expanduser())

    @property
    def resolved_path(self) -> Path:
        return Path(self.path)

    def exists(self) -> bool:
        return self.resolved_path.is_dir()