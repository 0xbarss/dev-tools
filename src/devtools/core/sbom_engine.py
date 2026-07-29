"""SBOM generation and best-effort local license reporting.

Built directly on `deps_engine.analyze()` — same manifests, same six
ecosystems, no new parsing logic duplicated. Stays true to the project's
local-first / no-required-network philosophy (spec §1, `allow_network`):
license data is read from whatever's already checked out locally
(`node_modules/*/package.json`, installed Python dist-info metadata), never
fetched from a registry. Anything that can't be determined locally is
reported as "unknown" rather than guessed.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from pathlib import Path

from devtools import __version__
from devtools.core.deps_engine import Dependency, analyze

_PURL_TYPE = {
    "python": "pypi",
    "node": "npm",
    "rust": "cargo",
    "go": "golang",
    "java": "maven",
    "flutter": "pub",
}

UNKNOWN_LICENSE = "unknown"


@dataclass
class LicensedDependency:
    dependency: Dependency
    license: str = UNKNOWN_LICENSE


@dataclass
class LicenseReport:
    entries: list[LicensedDependency] = field(default_factory=list)

    def by_license(self) -> dict[str, list[LicensedDependency]]:
        out: dict[str, list[LicensedDependency]] = {}
        for entry in self.entries:
            out.setdefault(entry.license, []).append(entry)
        return out

    @property
    def unknown_count(self) -> int:
        return len(self.by_license().get(UNKNOWN_LICENSE, []))


def _purl(dep: Dependency) -> str:
    ptype = _PURL_TYPE.get(dep.ecosystem, dep.ecosystem)
    version_part = f"@{dep.version}" if dep.version else ""
    return f"pkg:{ptype}/{dep.name}{version_part}"


def build_cyclonedx_sbom(root: Path) -> dict:
    """Build a CycloneDX-shaped SBOM dict (schema-lite: the fields real
    CycloneDX tooling reads — components/type/name/version/purl — without
    pulling in a full CycloneDX SDK dependency)."""
    report = analyze(root)
    components = [
        {
            "type": "library",
            "name": dep.name,
            "version": dep.version or "",
            "purl": _purl(dep),
            "group": dep.ecosystem,
            "scope": "optional" if dep.dev else "required",
            "properties": [{"name": "devtools:source_file", "value": dep.source_file}],
        }
        for dep in report.dependencies
    ]
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "tools": [{"vendor": "devtools", "name": "devtools sbom", "version": __version__}],
            "component": {"type": "application", "name": root.name},
        },
        "components": components,
    }


def _node_license(root: Path, dep: Dependency) -> str | None:
    manifest = root / "node_modules" / dep.name / "package.json"
    if not manifest.is_file():
        return None
    try:
        data = _json.loads(manifest.read_text(errors="ignore"))
    except (OSError, ValueError):
        return None
    lic = data.get("license")
    if isinstance(lic, str):
        return lic
    if isinstance(lic, dict):
        return lic.get("type")
    licenses = data.get("licenses")
    if isinstance(licenses, list) and licenses:
        first = licenses[0]
        return first.get("type") if isinstance(first, dict) else str(first)
    return None


def _python_license(root: Path, dep: Dependency) -> str | None:
    """Best-effort: scan installed dist-info metadata under any local venv
    directory (.venv, venv) for a License field. Never touches PyPI."""
    import re

    for venv_name in (".venv", "venv"):
        venv = root / venv_name
        if not venv.is_dir():
            continue
        for dist_info in venv.rglob(f"{dep.name}-*.dist-info"):
            metadata_file = dist_info / "METADATA"
            if not metadata_file.is_file():
                continue
            text = metadata_file.read_text(errors="ignore")
            m = re.search(r"^License:\s*(.+)$", text, re.MULTILINE)
            if m and m.group(1).strip() and m.group(1).strip().upper() != "UNKNOWN":
                return m.group(1).strip()
            m = re.search(r"^Classifier:\s*License\s*::\s*OSI Approved\s*::\s*(.+)$", text, re.MULTILINE)
            if m:
                return m.group(1).strip()
    return None


_LOCAL_LOOKUP = {
    "node": _node_license,
    "python": _python_license,
}


def build_license_report(root: Path) -> LicenseReport:
    """Attach a best-effort, locally-sourced license string to each
    dependency found by `deps_engine.analyze()`. Ecosystems/dependencies
    with no locally-checked-out metadata are reported as "unknown" rather
    than guessed — this is a local audit aid, not a registry-verified
    compliance report."""
    report = analyze(root)
    entries = []
    for dep in report.dependencies:
        lookup = _LOCAL_LOOKUP.get(dep.ecosystem)
        license_str = lookup(root, dep) if lookup else None
        entries.append(LicensedDependency(dependency=dep, license=license_str or UNKNOWN_LICENSE))
    return LicenseReport(entries=entries)