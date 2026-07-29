from __future__ import annotations

from devtools.core.marketplace_engine import (
    CURATED_REGISTRY,
    add_custom_entry,
    generate_site,
    load_registry,
    remove_custom_entry,
    render_html,
)


def test_load_registry_includes_curated_entries_by_default(tmp_path):
    custom_path = tmp_path / "marketplace_custom.json"
    registry = load_registry(custom_path)
    assert len(registry.entries) == len(CURATED_REGISTRY)
    assert all(e.source == "curated" for e in registry.entries)


def test_add_custom_entry_appears_alongside_curated(tmp_path):
    custom_path = tmp_path / "marketplace_custom.json"
    add_custom_entry("my-check", "does a thing", category="custom", path=custom_path)
    registry = load_registry(custom_path)
    custom_entries = [e for e in registry.entries if e.source == "custom"]
    assert len(custom_entries) == 1
    assert custom_entries[0].name == "my-check"
    assert len(registry.entries) == len(CURATED_REGISTRY) + 1


def test_add_custom_entry_with_same_name_replaces_previous(tmp_path):
    custom_path = tmp_path / "marketplace_custom.json"
    add_custom_entry("dup", "first description", path=custom_path)
    add_custom_entry("dup", "second description", path=custom_path)
    registry = load_registry(custom_path)
    matches = [e for e in registry.entries if e.name == "dup"]
    assert len(matches) == 1
    assert matches[0].description == "second description"


def test_remove_custom_entry(tmp_path):
    custom_path = tmp_path / "marketplace_custom.json"
    add_custom_entry("temp", "desc", path=custom_path)
    assert remove_custom_entry("temp", path=custom_path) is True
    registry = load_registry(custom_path)
    assert not [e for e in registry.entries if e.name == "temp"]


def test_remove_custom_entry_cannot_remove_curated(tmp_path):
    custom_path = tmp_path / "marketplace_custom.json"
    curated_name = CURATED_REGISTRY[0]["name"]
    assert remove_custom_entry(curated_name, path=custom_path) is False


def test_by_category_groups_entries(tmp_path):
    custom_path = tmp_path / "marketplace_custom.json"
    registry = load_registry(custom_path)
    grouped = registry.by_category()
    assert "hygiene" in grouped
    assert all(e.category == "hygiene" for e in grouped["hygiene"])


def test_render_html_includes_all_entries(tmp_path):
    custom_path = tmp_path / "marketplace_custom.json"
    add_custom_entry("my-check", "does a thing", category="custom", path=custom_path)
    registry = load_registry(custom_path)
    html = render_html(registry)
    assert "my-check" in html
    assert "<html" in html
    for entry in CURATED_REGISTRY:
        assert entry["name"] in html


def test_generate_site_writes_html_file(tmp_path):
    custom_path = tmp_path / "marketplace_custom.json"
    output = tmp_path / "site.html"
    written = generate_site(output, path=custom_path)
    assert written == output
    assert output.exists()
    assert "<html" in output.read_text()