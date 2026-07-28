from __future__ import annotations

import os

from devtools.core.doctor_checks import apply_fixes, run_all_checks
from devtools.core.ignore_rules import IgnoreRules


def _rules(root):
    return IgnoreRules.build(root, base_ignored_dirs=["node_modules", "__pycache__"])


def test_missing_license_is_reported(sample_repo):
    issues = run_all_checks(sample_repo, _rules(sample_repo), ["node_modules"])
    assert any(i.check == "missing_license" for i in issues)


def test_readme_present_is_not_reported(sample_repo):
    issues = run_all_checks(sample_repo, _rules(sample_repo), ["node_modules"])
    assert not any(i.check == "missing_readme" for i in issues)


def test_tests_present_is_not_reported(sample_repo):
    issues = run_all_checks(sample_repo, _rules(sample_repo), ["node_modules"])
    assert not any(i.check == "missing_tests" for i in issues)


def test_broken_symlink_detected(sample_repo):
    os.symlink(sample_repo / "does_not_exist", sample_repo / "broken")
    issues = run_all_checks(sample_repo, _rules(sample_repo), ["node_modules"])
    assert any(i.check == "broken_symlink" for i in issues)


def test_empty_folder_detected(sample_repo):
    (sample_repo / "empty_dir").mkdir()
    issues = run_all_checks(sample_repo, _rules(sample_repo), ["node_modules"])
    assert any(i.check == "empty_folder" and "empty_dir" in i.message for i in issues)


def test_apply_fixes_creates_gitignore_entries(sample_repo):
    (sample_repo / ".gitignore").write_text("*.log\n")
    issues = run_all_checks(sample_repo, _rules(sample_repo), ["node_modules", "dist"])
    fixable = [i for i in issues if i.fixable]
    assert fixable, "expected the incomplete .gitignore to be reported as fixable"
    actions = apply_fixes(sample_repo, fixable, ["node_modules", "dist"])
    assert actions
    content = (sample_repo / ".gitignore").read_text()
    assert "node_modules/" in content
    assert "dist/" in content


def test_apply_fixes_only_touches_fixable_issues(sample_repo):
    issues = run_all_checks(sample_repo, _rules(sample_repo), ["node_modules"])
    non_fixable = [i for i in issues if not i.fixable]
    actions = apply_fixes(sample_repo, non_fixable, ["node_modules"])
    assert actions == []


def test_missing_readme_is_fixable(sample_repo):
    (sample_repo / "README.md").unlink()
    issues = run_all_checks(sample_repo, _rules(sample_repo), ["node_modules"])
    readme_issue = next(i for i in issues if i.check == "missing_readme")
    assert readme_issue.fixable


def test_apply_fixes_creates_stub_readme(sample_repo):
    (sample_repo / "README.md").unlink()
    issues = run_all_checks(sample_repo, _rules(sample_repo), ["node_modules"])
    fixable = [i for i in issues if i.fixable]
    actions = apply_fixes(sample_repo, fixable, ["node_modules"], project_name="my-project")
    assert any("README" in a for a in actions)
    content = (sample_repo / "README.md").read_text()
    assert "# my-project" in content
    assert "## Installation" in content


def test_apply_fixes_does_not_overwrite_existing_readme(sample_repo):
    original = (sample_repo / "README.md").read_text()
    issues = run_all_checks(sample_repo, _rules(sample_repo), ["node_modules"])
    fixable = [i for i in issues if i.fixable]
    apply_fixes(sample_repo, fixable, ["node_modules"], project_name="my-project")
    assert (sample_repo / "README.md").read_text() == original
