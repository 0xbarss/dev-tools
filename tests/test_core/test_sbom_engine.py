from __future__ import annotations

import json

from devtools.core.sbom_engine import UNKNOWN_LICENSE, build_cyclonedx_sbom, build_license_report


def test_build_cyclonedx_sbom_shape(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\nflask>=2.0\n")
    bom = build_cyclonedx_sbom(tmp_path)

    assert bom["bomFormat"] == "CycloneDX"
    assert bom["specVersion"] == "1.5"
    names = {c["name"] for c in bom["components"]}
    assert names == {"requests", "flask"}
    requests_component = next(c for c in bom["components"] if c["name"] == "requests")
    assert requests_component["purl"] == "pkg:pypi/requests@==2.31.0"
    assert requests_component["group"] == "python"


def test_build_cyclonedx_sbom_is_json_serializable(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"lodash": "^4.17.0"}}))
    bom = build_cyclonedx_sbom(tmp_path)
    json.dumps(bom)  # should not raise


def test_build_license_report_unknown_without_local_metadata(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n")
    report = build_license_report(tmp_path)
    assert len(report.entries) == 1
    assert report.entries[0].license == UNKNOWN_LICENSE
    assert report.unknown_count == 1


def test_build_license_report_reads_local_node_modules_license(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"lodash": "^4.17.0"}}))
    pkg_dir = tmp_path / "node_modules" / "lodash"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "package.json").write_text(json.dumps({"name": "lodash", "license": "MIT"}))

    report = build_license_report(tmp_path)
    assert len(report.entries) == 1
    assert report.entries[0].license == "MIT"
    assert report.unknown_count == 0


def test_license_report_by_license_groups_correctly(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"lodash": "^4.17.0", "chalk": "^5.0.0"}})
    )
    lodash_dir = tmp_path / "node_modules" / "lodash"
    lodash_dir.mkdir(parents=True)
    (lodash_dir / "package.json").write_text(json.dumps({"license": "MIT"}))

    report = build_license_report(tmp_path)
    grouped = report.by_license()
    assert "MIT" in grouped and len(grouped["MIT"]) == 1
    assert UNKNOWN_LICENSE in grouped
    assert len(grouped[UNKNOWN_LICENSE]) == 1