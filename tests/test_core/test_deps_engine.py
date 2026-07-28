from __future__ import annotations

import json

from devtools.core.deps_engine import analyze


def test_analyze_python_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["typer>=0.12", "rich>=13.7"]\n'
        '[project.optional-dependencies]\ndev = ["pytest>=8.0"]\n'
    )
    report = analyze(tmp_path)
    assert "python" in report.ecosystems_found
    names = {d.name for d in report.dependencies}
    assert {"typer", "rich", "pytest"} <= names
    dev_flags = {d.name: d.dev for d in report.dependencies}
    assert dev_flags["pytest"] is True
    assert dev_flags["typer"] is False


def test_analyze_node_package_json(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"react": "^18.0.0"}, "devDependencies": {"eslint": "^9.0.0"}})
    )
    report = analyze(tmp_path)
    assert "node" in report.ecosystems_found
    names = {d.name for d in report.dependencies}
    assert {"react", "eslint"} <= names


def test_analyze_rust_cargo_toml(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[dependencies]\nserde = "1.0"\n')
    report = analyze(tmp_path)
    assert "rust" in report.ecosystems_found
    assert any(d.name == "serde" for d in report.dependencies)


def test_analyze_go_mod(tmp_path):
    (tmp_path / "go.mod").write_text(
        "module example.com/x\n\nrequire (\n\tgithub.com/pkg/errors v0.9.1\n)\n"
    )
    report = analyze(tmp_path)
    assert "go" in report.ecosystems_found
    assert any(d.name == "github.com/pkg/errors" for d in report.dependencies)


def test_analyze_flutter_pubspec(tmp_path):
    (tmp_path / "pubspec.yaml").write_text(
        "name: x\ndependencies:\n  flutter:\n    sdk: flutter\n  http: ^0.13.0\n"
        "dev_dependencies:\n  test: ^1.0.0\n"
    )
    report = analyze(tmp_path)
    assert "flutter" in report.ecosystems_found
    names = {d.name for d in report.dependencies}
    assert "http" in names
    assert "flutter" not in names  # the flutter SDK entry itself is excluded


def test_analyze_empty_project_returns_no_ecosystems(tmp_path):
    report = analyze(tmp_path)
    assert report.ecosystems_found == []
    assert report.dependencies == []
