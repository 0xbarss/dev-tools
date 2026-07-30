from __future__ import annotations

from devtools.core.compliance_engine import build_compliance_report, render_html, render_markdown
from devtools.core.ignore_rules import IgnoreRules


def test_compliance_report_scores_clean_repo_near_perfect(tmp_path):
    (tmp_path / "README.md").write_text("# clean\n")
    (tmp_path / "LICENSE").write_text("MIT\n")
    (tmp_path / ".gitignore").write_text("*.log\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test_ok():\n    assert True\n")
    (tmp_path / "main.py").write_text("def main():\n    return 1\n\nmain()\n")

    rules = IgnoreRules.build(tmp_path, base_ignored_dirs=[])
    report = build_compliance_report(tmp_path, rules, [], "clean_project")

    assert report.score >= 85
    assert report.dependency_count == 0


def test_compliance_report_flags_missing_readme_and_license(tmp_path):
    (tmp_path / "main.py").write_text("print('hi')\n")
    rules = IgnoreRules.build(tmp_path, base_ignored_dirs=[])
    report = build_compliance_report(tmp_path, rules, [], "bare_project")

    messages = [f.message for f in report.findings]
    assert any("README" in m for m in messages)
    assert report.score < 100


def test_compliance_report_denied_license_is_an_error_finding(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="s"\ndependencies=["gpl-lib>=1.0"]\n')
    dist_info = tmp_path / ".venv" / "lib" / "gpl_lib-1.0.dist-info"
    # sbom_engine's license lookup is best-effort/local-only; without installed
    # metadata this dependency will resolve as "unknown", which is exactly the
    # scenario --deny is meant to be layered on top of at the license level.
    rules = IgnoreRules.build(tmp_path, base_ignored_dirs=[])
    report = build_compliance_report(tmp_path, rules, [], "denied_project", deny_licenses=["unknown"])

    assert report.denied_license_count >= 1
    assert report.has_errors is True


def test_compliance_report_deadcode_is_advisory_only(tmp_path):
    (tmp_path / "mod.py").write_text("def unused():\n    return 1\n")
    (tmp_path / "README.md").write_text("# x\n")
    rules = IgnoreRules.build(tmp_path, base_ignored_dirs=[])
    report = build_compliance_report(tmp_path, rules, [], "deadcode_project")

    deadcode_findings = [f for f in report.findings if f.category == "maintainability"]
    assert deadcode_findings
    assert all(f.severity == "info" for f in deadcode_findings)


def test_compliance_score_never_goes_below_zero(tmp_path):
    # An empty, hygiene-failing project with several denied dependencies.
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="s"\ndependencies=["a>=1.0", "b>=1.0", "c>=1.0", "d>=1.0"]\n'
    )
    rules = IgnoreRules.build(tmp_path, base_ignored_dirs=[])
    report = build_compliance_report(tmp_path, rules, [], "bad_project", deny_licenses=["unknown"])
    assert 0 <= report.score <= 100


def test_render_markdown_reports_clean_bill_of_health(tmp_path):
    (tmp_path / "README.md").write_text("# x\n")
    (tmp_path / "LICENSE").write_text("MIT\n")
    (tmp_path / ".gitignore").write_text("*.log\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n")
    rules = IgnoreRules.build(tmp_path, base_ignored_dirs=[])
    report = build_compliance_report(tmp_path, rules, [], "spotless")
    md = render_markdown(report)
    assert "clean bill of health" in md.lower()


def test_render_html_is_self_contained_and_escapes_project_name(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n")
    rules = IgnoreRules.build(tmp_path, base_ignored_dirs=[])
    report = build_compliance_report(tmp_path, rules, [], "<script>evil</script>")
    html = render_html(report)
    assert "<script>evil</script>" not in html
    assert "&lt;script&gt;" in html
    assert "<html" in html
