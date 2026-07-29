from __future__ import annotations

from devtools.core.ignore_rules import IgnoreRules


def test_default_ignored_dirs_are_pruned(sample_repo):
    rules = IgnoreRules.build(sample_repo, base_ignored_dirs=[".git", "node_modules"])
    files = {p.relative_to(sample_repo).as_posix() for p in rules.filtered_walk()}
    assert "node_modules/pkg/index.js" not in files
    assert "src/main.py" in files


def test_gitignore_is_respected(sample_repo):
    rules = IgnoreRules.build(sample_repo, base_ignored_dirs=[])
    files = {p.relative_to(sample_repo).as_posix() for p in rules.filtered_walk()}
    assert "debug.log" not in files  # matched by the repo's own .gitignore


def test_no_gitignore_flag_includes_previously_ignored_files(sample_repo):
    rules = IgnoreRules.build(sample_repo, base_ignored_dirs=[], use_gitignore=False)
    files = {p.relative_to(sample_repo).as_posix() for p in rules.filtered_walk()}
    assert "debug.log" in files


def test_extra_excludes_take_highest_precedence(sample_repo):
    rules = IgnoreRules.build(sample_repo, base_ignored_dirs=[], extra_excludes=["*.py"])
    files = {p.relative_to(sample_repo).as_posix() for p in rules.filtered_walk()}
    assert not any(f.endswith(".py") for f in files)
    assert "README.md" in files


def test_git_directory_is_always_ignored(sample_repo):
    (sample_repo / ".git").mkdir()
    (sample_repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    rules = IgnoreRules.build(sample_repo, base_ignored_dirs=[])
    files = {p.relative_to(sample_repo).as_posix() for p in rules.filtered_walk()}
    assert not any(f.startswith(".git/") for f in files)


def test_project_override_dirs_are_combined_with_global(sample_repo):
    (sample_repo / "legacy").mkdir()
    (sample_repo / "legacy" / "old.py").write_text("x = 1\n")
    rules = IgnoreRules.build(
        sample_repo,
        base_ignored_dirs=["node_modules"],
        project_ignored_dirs=["legacy/"],
    )
    files = {p.relative_to(sample_repo).as_posix() for p in rules.filtered_walk()}
    assert "legacy/old.py" not in files
    assert "node_modules/pkg/index.js" not in files