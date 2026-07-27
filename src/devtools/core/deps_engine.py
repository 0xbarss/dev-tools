"""Dependency analysis for Python, Node, Rust, Go, Java, Flutter.

Reads local manifests/lockfiles only (per spec §1 non-goals — no registry
calls except the explicit, opt-in `--outdated` path handled in commands/deps.py).
"""

from __future__ import annotations

import json as _json
import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass
class Dependency:
    name: str
    version: str | None
    ecosystem: str
    dev: bool = False
    source_file: str = ""


@dataclass
class DepsReport:
    ecosystems_found: list[str] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)
    manifest_files: list[str] = field(default_factory=list)

    def by_ecosystem(self) -> dict[str, list[Dependency]]:
        out: dict[str, list[Dependency]] = {}
        for dep in self.dependencies:
            out.setdefault(dep.ecosystem, []).append(dep)
        return out


_PARSERS: list[tuple[str, str]] = [
    ("pyproject.toml", "python"),
    ("requirements.txt", "python"),
    ("package.json", "node"),
    ("Cargo.toml", "rust"),
    ("go.mod", "go"),
    ("pom.xml", "java"),
    ("build.gradle", "java"),
    ("build.gradle.kts", "java"),
    ("pubspec.yaml", "flutter"),
]


def detect_manifests(root: Path) -> list[Path]:
    return [root / name for name, _eco in _PARSERS if (root / name).is_file()]


def analyze(root: Path) -> DepsReport:
    report = DepsReport()
    for filename, ecosystem in _PARSERS:
        path = root / filename
        if not path.is_file():
            continue
        report.manifest_files.append(filename)
        if ecosystem not in report.ecosystems_found:
            report.ecosystems_found.append(ecosystem)
        try:
            deps = _PARSE_DISPATCH[filename](path)
        except Exception:
            deps = []
        report.dependencies.extend(deps)
    return report


def _parse_pyproject(path: Path) -> list[Dependency]:
    with path.open("rb") as f:
        data = tomllib.load(f)
    deps: list[Dependency] = []
    project = data.get("project", {})
    for raw in project.get("dependencies", []):
        name, version = _split_pep508(raw)
        deps.append(Dependency(name, version, "python", dev=False, source_file=path.name))
    for group, items in project.get("optional-dependencies", {}).items():
        for raw in items:
            name, version = _split_pep508(raw)
            deps.append(Dependency(name, version, "python", dev=True, source_file=f"{path.name}[{group}]"))
    # Poetry-style fallback
    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    for name, spec in poetry_deps.items():
        if name.lower() == "python":
            continue
        version = spec if isinstance(spec, str) else spec.get("version") if isinstance(spec, dict) else None
        deps.append(Dependency(name, version, "python", dev=False, source_file=path.name))
    return deps


def _parse_requirements_txt(path: Path) -> list[Dependency]:
    deps = []
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        name, version = _split_pep508(line)
        deps.append(Dependency(name, version, "python", dev=False, source_file=path.name))
    return deps


def _parse_package_json(path: Path) -> list[Dependency]:
    data = _json.loads(path.read_text(errors="ignore"))
    deps = []
    for name, version in (data.get("dependencies") or {}).items():
        deps.append(Dependency(name, version, "node", dev=False, source_file=path.name))
    for name, version in (data.get("devDependencies") or {}).items():
        deps.append(Dependency(name, version, "node", dev=True, source_file=path.name))
    return deps


def _parse_cargo_toml(path: Path) -> list[Dependency]:
    with path.open("rb") as f:
        data = tomllib.load(f)
    deps = []
    for name, spec in (data.get("dependencies") or {}).items():
        version = spec if isinstance(spec, str) else (spec.get("version") if isinstance(spec, dict) else None)
        deps.append(Dependency(name, version, "rust", dev=False, source_file=path.name))
    for name, spec in (data.get("dev-dependencies") or {}).items():
        version = spec if isinstance(spec, str) else (spec.get("version") if isinstance(spec, dict) else None)
        deps.append(Dependency(name, version, "rust", dev=True, source_file=path.name))
    return deps


_GO_REQUIRE_RE = re.compile(r"^\s*([^\s]+)\s+([^\s]+)")


def _parse_go_mod(path: Path) -> list[Dependency]:
    deps = []
    in_block = False
    for line in path.read_text(errors="ignore").splitlines():
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_block = True
            continue
        if in_block and stripped == ")":
            in_block = False
            continue
        if in_block or stripped.startswith("require "):
            content = stripped.removeprefix("require ").strip()
            m = _GO_REQUIRE_RE.match(content)
            if m:
                deps.append(Dependency(m.group(1), m.group(2), "go", dev=False, source_file=path.name))
    return deps


_MAVEN_DEP_RE = re.compile(
    r"<dependency>\s*<groupId>(.*?)</groupId>\s*<artifactId>(.*?)</artifactId>(?:\s*<version>(.*?)</version>)?",
    re.DOTALL,
)


def _parse_pom_xml(path: Path) -> list[Dependency]:
    text = path.read_text(errors="ignore")
    deps = []
    for group, artifact, version in _MAVEN_DEP_RE.findall(text):
        deps.append(Dependency(f"{group}:{artifact}", version or None, "java", dev=False, source_file=path.name))
    return deps


_GRADLE_DEP_RE = re.compile(
    r"""(?:implementation|api|testImplementation|compileOnly|runtimeOnly)\s*[\(\s]['"]([^'"]+)['"]"""
)


def _parse_gradle(path: Path) -> list[Dependency]:
    text = path.read_text(errors="ignore")
    deps = []
    for match in _GRADLE_DEP_RE.findall(text):
        parts = match.split(":")
        name = ":".join(parts[:2]) if len(parts) >= 2 else match
        version = parts[2] if len(parts) >= 3 else None
        dev = "test" in match.lower()
        deps.append(Dependency(name, version, "java", dev=dev, source_file=path.name))
    return deps


_PUBSPEC_DEP_RE = re.compile(r"^\s{2}([a-zA-Z0-9_]+):\s*(\S+)?\s*$", re.MULTILINE)


def _parse_pubspec_yaml(path: Path) -> list[Dependency]:
    text = path.read_text(errors="ignore")
    deps = []
    section = None
    for line in text.splitlines():
        if re.match(r"^dependencies:\s*$", line):
            section = "dependencies"
            continue
        if re.match(r"^dev_dependencies:\s*$", line):
            section = "dev_dependencies"
            continue
        if re.match(r"^[a-zA-Z_]+:\s*$", line) and section:
            section = None
            continue
        if section and re.match(r"^\s{2}\S", line):
            m = re.match(r"^\s{2}([a-zA-Z0-9_]+):\s*(.*)$", line)
            if m:
                name, version = m.group(1), m.group(2).strip() or None
                if name == "flutter":
                    continue
                deps.append(
                    Dependency(name, version, "flutter", dev=(section == "dev_dependencies"), source_file=path.name)
                )
    return deps


_PARSE_DISPATCH = {
    "pyproject.toml": _parse_pyproject,
    "requirements.txt": _parse_requirements_txt,
    "package.json": _parse_package_json,
    "Cargo.toml": _parse_cargo_toml,
    "go.mod": _parse_go_mod,
    "pom.xml": _parse_pom_xml,
    "build.gradle": _parse_gradle,
    "build.gradle.kts": _parse_gradle,
    "pubspec.yaml": _parse_pubspec_yaml,
}

_PEP508_RE = re.compile(r"^([A-Za-z0-9._-]+)\s*(\[[^\]]*\])?\s*(.*)$")


def _split_pep508(raw: str) -> tuple[str, str | None]:
    raw = raw.strip()
    m = _PEP508_RE.match(raw)
    if not m:
        return raw, None
    name = m.group(1)
    rest = m.group(3).strip()
    return name, (rest or None)