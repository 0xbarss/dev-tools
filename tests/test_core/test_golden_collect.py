"""Golden-file test for collect's markdown output (spec §11): a byte-for-byte
diff against a committed fixture, so accidental formatting/ordering changes
in collector.py get caught immediately.

If you deliberately change the markdown format, regenerate the fixture with:

    python -c "
    from pathlib import Path
    from devtools.core.collector import collect_files, render_markdown
    from devtools.core.ignore_rules import IgnoreRules
    # ... build the same sample_repo fixture as conftest.py ...
    " > tests/fixtures/sample_repo_collect_python.md
"""

from __future__ import annotations

from pathlib import Path

from devtools.core.collector import collect_files, render_markdown
from devtools.core.ignore_rules import IgnoreRules

GOLDEN_PATH = Path(__file__).parent.parent / "fixtures" / "sample_repo_collect_python.md"


def test_collect_markdown_matches_golden_file(sample_repo):
    rules = IgnoreRules.build(sample_repo, base_ignored_dirs=["node_modules", "__pycache__"])
    result = collect_files(sample_repo, rules, languages=["python"])
    actual = render_markdown(result, "sample_repo")
    expected = GOLDEN_PATH.read_text()
    assert actual == expected
