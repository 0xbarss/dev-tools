"""Repository health checks for `doctor`.

Each check returns a DoctorIssue (or nothing). Checks are independent and
side-effect-free except `fix()`, which is only ever invoked under `--fix`
and only implements the checks explicitly documented as auto-fixable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from devtools.core.filesystem import dir_size, is_probably_binary
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.scanner import scan_project
from devtools.core.stats_engine import find_duplicate_files

BINARY_SIZE_WARN_BYTES = 5 * 1024 * 1024  # 5MB
README_NAMES = {"readme.md", "readme", "readme.rst", "readme.txt"}
LICENSE_NAMES = {"license", "license.md", "license.txt", "copying"}
TEST_DIR_HINTS = {"tests", "test", "__tests__", "spec"}


@dataclass
class DoctorIssue:
    check: str
    severity: str  # "info" | "warning" | "error"
    message: str
    fixable: bool = False
    fix_hint: str | None = None


def check_missing_readme(root: Path) -> DoctorIssue | None:
    if any((root / n).exists() for n in _case_variants(README_NAMES, root)):
        return None
    return DoctorIssue("missing_readme", "warning", "No README file found at the project root.")


def check_missing_license(root: Path) -> DoctorIssue | None:
    if any((root / n).exists() for n in _case_variants(LICENSE_NAMES, root)):
        return None
    return DoctorIssue("missing_license", "info", "No LICENSE file found at the project root.")


def check_missing_tests(root: Path, ignore_rules: IgnoreRules) -> DoctorIssue | None:
    for entry in ignore_rules.filtered_walk():
        parts = {p.lower() for p in entry.relative_to(root).parts}
        if parts & TEST_DIR_HINTS:
            return None
        name = entry.name.lower()
        if name.startswith("test_") or name.endswith("_test.py") or ".test." in name or ".spec." in name:
            return None
    return DoctorIssue("missing_tests", "warning", "No test files or test directory detected.")


def check_large_binaries(root: Path, ignore_rules: IgnoreRules, threshold: int = BINARY_SIZE_WARN_BYTES) -> list[DoctorIssue]:
    issues = []
    for entry in scan_project(root, ignore_rules):
        if entry.is_binary and entry.size > threshold:
            issues.append(
                DoctorIssue(
                    "large_binary",
                    "warning",
                    f"{entry.rel_path} is a {entry.size / (1024*1024):.1f}MB binary tracked in the project.",
                )
            )
    return issues


def check_broken_symlinks(root: Path, ignore_rules: IgnoreRules) -> list[DoctorIssue]:
    issues = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            children = list(current.iterdir())
        except OSError:
            continue
        for child in children:
            if ignore_rules.is_ignored(child):
                continue
            if child.is_symlink() and not child.exists():
                issues.append(DoctorIssue("broken_symlink", "error", f"Broken symlink: {child.relative_to(root)}"))
            elif child.is_dir() and not child.is_symlink():
                stack.append(child)
    return issues


def check_empty_folders(root: Path, ignore_rules: IgnoreRules) -> list[DoctorIssue]:
    issues = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            children = [c for c in current.iterdir() if not ignore_rules.is_ignored(c)]
        except OSError:
            continue
        if current != root and not children:
            issues.append(DoctorIssue("empty_folder", "info", f"Empty folder: {current.relative_to(root)}"))
        for c in children:
            if c.is_dir():
                stack.append(c)
    return issues


def check_duplicate_files(root: Path, ignore_rules: IgnoreRules) -> list[DoctorIssue]:
    dups = find_duplicate_files(root, ignore_rules)
    return [
        DoctorIssue("duplicate_files", "info", f"{len(paths)} identical files: {', '.join(paths)}")
        for paths in dups.values()
    ]


def check_gitignore_missing_common_dirs(root: Path, ignored_dirs: list[str]) -> DoctorIssue | None:
    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return DoctorIssue(
            "missing_gitignore", "info", "No .gitignore file found.", fixable=True,
            fix_hint="create a .gitignore with the project's configured ignored_dirs",
        )
    content = gitignore.read_text(errors="ignore")
    missing = [d for d in ignored_dirs if d not in content]
    if not missing:
        return None
    return DoctorIssue(
        "gitignore_incomplete",
        "info",
        f".gitignore is missing entries for: {', '.join(missing)}",
        fixable=True,
        fix_hint="append missing entries to .gitignore",
    )


def run_all_checks(root: Path, ignore_rules: IgnoreRules, ignored_dirs: list[str]) -> list[DoctorIssue]:
    issues: list[DoctorIssue] = []
    for issue in (
        check_missing_readme(root),
        check_missing_license(root),
        check_missing_tests(root, ignore_rules),
        check_gitignore_missing_common_dirs(root, ignored_dirs),
    ):
        if issue:
            issues.append(issue)
    issues.extend(check_large_binaries(root, ignore_rules))
    issues.extend(check_broken_symlinks(root, ignore_rules))
    issues.extend(check_empty_folders(root, ignore_rules))
    issues.extend(check_duplicate_files(root, ignore_rules))
    return issues


def apply_fixes(root: Path, issues: list[DoctorIssue], ignored_dirs: list[str]) -> list[str]:
    """Apply only the auto-fixable issues; returns a list of human-readable actions taken."""
    actions = []
    for issue in issues:
        if not issue.fixable:
            continue
        if issue.check in ("missing_gitignore", "gitignore_incomplete"):
            gitignore = root / ".gitignore"
            existing = gitignore.read_text(errors="ignore") if gitignore.is_file() else ""
            missing = [d for d in ignored_dirs if d not in existing]
            if missing:
                with gitignore.open("a", encoding="utf-8") as f:
                    if existing and not existing.endswith("\n"):
                        f.write("\n")
                    for d in missing:
                        f.write(f"{d}/\n")
                actions.append(f"Added {len(missing)} entries to .gitignore")
    return actions


def _case_variants(names: set[str], root: Path) -> list[str]:
    variants = set()
    for n in names:
        variants.add(n)
        variants.add(n.upper())
        variants.add(n.capitalize())
    return list(variants)
