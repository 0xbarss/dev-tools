"""`export` turns another command's last output into a shareable file format.

We cache each exportable command's JSON-shaped output under the user cache
dir (~/.cache/devtools/last_output/<project>__<command>.json) the moment that
command runs; `export` reads that cache back and converts it to CSV/HTML.
This keeps `export` decoupled from having to re-run the original command.
"""

from __future__ import annotations

import csv
import html
import io
import json as _json
from pathlib import Path

try:
    import orjson
except ImportError:  # pragma: no cover
    orjson = None  # type: ignore[assignment]

from devtools.utils.paths import cache_dir


def _cache_path(command: str, project: str) -> Path:
    return cache_dir() / "last_output" / f"{project}__{command}.json"


def cache_output(command: str, project: str, data) -> None:
    path = _cache_path(command, project)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = orjson.dumps(data) if orjson is not None else _json.dumps(data).encode("utf-8")
    path.write_bytes(payload)


def load_cached_output(command: str, project: str):
    path = _cache_path(command, project)
    if not path.is_file():
        return None
    raw = path.read_bytes()
    return orjson.loads(raw) if orjson is not None else _json.loads(raw)


def to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    fieldnames = list(rows[0].keys())
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def to_html_table(title: str, rows: list[dict]) -> str:
    if not rows:
        columns: list[str] = []
    else:
        columns = list(rows[0].keys())
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in columns)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(str(row.get(c, '')))}</td>" for c in columns)
        body_rows.append(f"<tr>{cells}</tr>")
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:sans-serif;margin:2rem}"
        "table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #ccc;padding:6px 10px;text-align:left}"
        "th{background:#f2f2f2}</style></head><body>"
        f"<h1>{html.escape(title)}</h1>"
        f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"
        "</body></html>"
    )


def to_sarif(findings: list[dict], tool_name: str = "devtools lint") -> str:
    """SARIF 2.1.0 log for lint findings (backlog #55), so `devtools lint`
    output can feed GitHub code scanning, Azure DevOps, or any other
    SARIF-consuming dashboard. Expects the same shape `devtools lint --json`
    already emits per finding: file, line, rule, severity, message,
    source_linter (all but `file`/`message` are optional; missing values
    degrade gracefully rather than raising, since a partially-populated
    finding is still worth reporting).
    """
    _SEVERITY_TO_LEVEL = {"error": "error", "warning": "warning", "info": "note"}

    rule_ids = sorted({f.get("rule") for f in findings if f.get("rule")})
    rules = [{"id": rid, "name": rid} for rid in rule_ids]

    results = []
    for f in findings:
        line = f.get("line") or 1  # SARIF regions are 1-indexed; None means "location unknown"
        results.append(
            {
                "ruleId": f.get("rule") or "unspecified",
                "level": _SEVERITY_TO_LEVEL.get(f.get("severity"), "warning"),
                "message": {"text": f.get("message", "")},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": f.get("file", "")},
                            "region": {"startLine": line},
                        }
                    }
                ],
                "properties": {"source_linter": f.get("source_linter")} if f.get("source_linter") else {},
            }
        )

    sarif_log = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": {"name": tool_name, "informationUri": "https://github.com/", "rules": rules}},
                "results": results,
            }
        ],
    }
    return _json.dumps(sarif_log, indent=2)


def tree_to_html(title: str, tree_dict: dict) -> str:
    def _render(node: dict) -> str:
        name = html.escape(node.get("name", ""))
        if node.get("type") == "dir":
            children = "".join(f"<li>{_render(c)}</li>" for c in node.get("children", []))
            return f"<strong>{name}/</strong><ul>{children}</ul>"
        return name

    body = _render(tree_dict)
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:sans-serif;margin:2rem}"
        "ul{list-style-type:none}</style></head><body>"
        f"<h1>{html.escape(title)}</h1>{body}</body></html>"
    )
