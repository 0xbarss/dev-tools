"""`devtools marketplace` — a listing page for community plugins/checks
(Prioritized Backlog: "Marketplace listing page", P2, "static site").

The plugin *system* itself (proposal deep-dive/backlog "Plugin system", P1)
isn't built yet, so this deliberately doesn't pretend to install or execute
anything. What it does provide, matching the backlog entry as scoped
("Low"/"Low" effort, "static listing site"), is:

  - a small curated registry of plugin ideas/checks bundled with devtools,
  - a place for users to register their own entries locally
    (`~/.config/devtools/marketplace_custom.json`), the same JSON-store
    pattern as `alias_store.py` / `notify_engine.py`,
  - a static, self-contained HTML page listing all of it, so there's
    somewhere real to point people once a plugin system does land.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from pathlib import Path

try:
    import orjson
except ImportError:  # pragma: no cover
    orjson = None  # type: ignore[assignment]

from devtools import __version__
from devtools.utils.paths import marketplace_custom_file_path

# A small curated starter set — illustrative of the kind of organization- or
# community-supplied checks the eventual plugin system (§3 backlog #8) is
# meant to host. Bundled with the package, not fetched from a network, in
# keeping with the local-first / no-required-network philosophy.
CURATED_REGISTRY: list[dict] = [
    {
        "name": "conventional-commits-check",
        "category": "hygiene",
        "description": "Flags commits that don't follow Conventional Commits, for use with `devtools changelog`.",
        "author": "devtools core",
        "url": "https://github.com/example/devtools-plugins",
    },
    {
        "name": "license-allowlist",
        "category": "compliance",
        "description": "Org-specific license allowlist, layered on top of `devtools compliance report --deny`.",
        "author": "devtools core",
        "url": "https://github.com/example/devtools-plugins",
    },
    {
        "name": "secrets-scan",
        "category": "security",
        "description": "Regex/entropy-based scan for accidentally committed credentials, feeding `devtools doctor`.",
        "author": "devtools core",
        "url": "https://github.com/example/devtools-plugins",
    },
    {
        "name": "monorepo-ownership",
        "category": "maintainability",
        "description": "CODEOWNERS-aware hotspot/ownership report, complementing `devtools stats`.",
        "author": "devtools core",
        "url": "https://github.com/example/devtools-plugins",
    },
]


@dataclass
class MarketplaceEntry:
    name: str
    category: str
    description: str
    author: str = "unknown"
    url: str = ""
    source: str = "curated"  # "curated" | "custom"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "author": self.author,
            "url": self.url,
            "source": self.source,
        }


@dataclass
class MarketplaceRegistry:
    entries: list[MarketplaceEntry] = field(default_factory=list)

    def by_category(self) -> dict[str, list[MarketplaceEntry]]:
        out: dict[str, list[MarketplaceEntry]] = {}
        for entry in self.entries:
            out.setdefault(entry.category, []).append(entry)
        return out


def _dumps(obj) -> bytes:
    if orjson is not None:
        return orjson.dumps(obj, option=orjson.OPT_INDENT_2)
    return _json.dumps(obj, indent=2).encode("utf-8")


def _loads(data: bytes | str):
    if orjson is not None:
        return orjson.loads(data)
    return _json.loads(data)


def _load_custom(path: Path | None = None) -> list[dict]:
    p = path or marketplace_custom_file_path()
    if not p.is_file():
        return []
    return _loads(p.read_bytes())


def _save_custom(entries: list[dict], path: Path | None = None) -> Path:
    p = path or marketplace_custom_file_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_dumps(entries))
    return p


def load_registry(path: Path | None = None, include_curated: bool = True) -> MarketplaceRegistry:
    entries: list[MarketplaceEntry] = []
    if include_curated:
        entries.extend(MarketplaceEntry(source="curated", **e) for e in CURATED_REGISTRY)
    for raw in _load_custom(path):
        entries.append(
            MarketplaceEntry(
                name=raw.get("name", "unnamed"),
                category=raw.get("category", "uncategorized"),
                description=raw.get("description", ""),
                author=raw.get("author", "you"),
                url=raw.get("url", ""),
                source="custom",
            )
        )
    return MarketplaceRegistry(entries=entries)


def add_custom_entry(
    name: str,
    description: str,
    category: str = "uncategorized",
    author: str = "you",
    url: str = "",
    path: Path | None = None,
) -> list[dict]:
    entries = _load_custom(path)
    entries = [e for e in entries if e.get("name") != name]  # replace if re-added
    entries.append({"name": name, "category": category, "description": description, "author": author, "url": url})
    _save_custom(entries, path)
    return entries


def remove_custom_entry(name: str, path: Path | None = None) -> bool:
    entries = _load_custom(path)
    remaining = [e for e in entries if e.get("name") != name]
    if len(remaining) == len(entries):
        return False
    _save_custom(remaining, path)
    return True


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>devtools marketplace</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; margin: 2rem auto; max-width: 960px; color: #1a1a1a; }}
  h1 {{ margin-bottom: 0.25rem; }}
  .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 2rem; }}
  h2 {{ border-bottom: 1px solid #ddd; padding-bottom: 0.25rem; margin-top: 2rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 1rem; margin-top: 1rem; }}
  .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 1rem; }}
  .card h3 {{ margin: 0 0 0.4rem; font-size: 1rem; }}
  .card p {{ margin: 0 0 0.6rem; font-size: 0.9rem; color: #333; }}
  .card .author {{ font-size: 0.8rem; color: #777; }}
  .badge {{ display: inline-block; font-size: 0.7rem; padding: 0.1rem 0.5rem; border-radius: 999px; background: #eef; color: #334; margin-left: 0.4rem; }}
</style>
</head>
<body>
<h1>devtools marketplace</h1>
<div class="meta">A community listing of plugin ideas and checks for devtools {version}. No installer yet — this is a preview of what a plugin ecosystem will host.</div>
{sections_html}
</body>
</html>
"""


def render_html(registry: MarketplaceRegistry) -> str:
    sections = []
    for category, entries in sorted(registry.by_category().items()):
        cards = []
        for e in entries:
            badge = f'<span class="badge">{e.source}</span>' if e.source == "custom" else ""
            link = f'<div><a href="{e.url}">{e.url}</a></div>' if e.url else ""
            cards.append(
                f'<div class="card"><h3>{e.name}{badge}</h3><p>{e.description}</p>'
                f'<div class="author">by {e.author}</div>{link}</div>'
            )
        sections.append(f"<h2>{category.capitalize()}</h2><div class=\"grid\">{''.join(cards)}</div>")
    return _HTML_TEMPLATE.format(version=__version__, sections_html="\n".join(sections))


def generate_site(output_path: Path, path: Path | None = None) -> Path:
    """Render the marketplace listing to a self-contained static HTML file."""
    registry = load_registry(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(registry), encoding="utf-8")
    return output_path