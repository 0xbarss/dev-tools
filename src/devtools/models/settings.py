"""Pydantic models for ~/.config/devtools/config.toml."""

from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_IGNORED_DIRS = [
    ".git",
    # Python
    ".venv", "venv", "env", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", ".eggs", "*.egg-info",
    # Node / JS / TS
    "node_modules", "dist", "build", "out", ".next", ".nuxt",
    ".turbo", ".parcel-cache", ".angular", ".svelte-kit", "coverage",
    # Rust
    "target",
    # Go
    "vendor",
    # Java / Gradle / Maven
    ".gradle",
    # Flutter / Dart
    ".dart_tool", ".pub-cache",
    # .NET
    "bin", "obj",
    # Mobile / native
    "Pods", "DerivedData",
    # Misc infra
    ".terraform", "bazel-*", "cmake-build-*", ".stack-work",
    # Coverage / cache (general)
    "htmlcov", ".cache",
]


class ProjectOverride(BaseModel):
    ignored_dirs: list[str] = Field(default_factory=list)


class Settings(BaseModel):
    output_format: str = "markdown"
    max_bundle_size: str = "10MB"
    theme: str = "dark"
    allow_network: bool = False
    default_project: str | None = None

    # Pluggable AI backend (spec §4 / proposal deep-dive #5). `ai_provider`
    # is one of "none" (default; every AI command refuses to run), "claude",
    # "openai", or "ollama". API keys are read from the provider's usual env
    # var (ANTHROPIC_API_KEY / OPENAI_API_KEY) — never stored in config.toml.
    ai_provider: str = "none"
    ai_model: str | None = None

    ignored_dirs: list[str] = Field(default_factory=lambda: list(DEFAULT_IGNORED_DIRS))
    project_overrides: dict[str, ProjectOverride] = Field(default_factory=dict)

    # Base URL used to turn bare issue IDs found by `devtools pr link-issues`
    # into clickable links, e.g. "https://github.com/org/repo/issues" or
    # "https://org.atlassian.net/browse". None means IDs are printed as-is.
    issue_tracker_url: str | None = None

    def ignored_dirs_for(self, project_name: str | None) -> list[str]:
        """ignored_dirs is additive: global list + that project's overrides."""
        combined = list(self.ignored_dirs)
        if project_name and project_name in self.project_overrides:
            combined.extend(self.project_overrides[project_name].ignored_dirs)
        return combined

    model_config = {"extra": "allow"}
