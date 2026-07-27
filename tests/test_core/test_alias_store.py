from __future__ import annotations

from devtools.core.alias_store import add_alias, load_aliases, remove_alias, split_chain


def test_add_and_load_alias(tmp_path):
    path = tmp_path / "aliases.json"
    add_alias("morning", "stats api && doctor api", path)
    aliases = load_aliases(path)
    assert aliases["morning"] == "stats api && doctor api"


def test_remove_alias_returns_false_when_absent(tmp_path):
    path = tmp_path / "aliases.json"
    assert remove_alias("nope", path) is False


def test_remove_alias_returns_true_and_deletes(tmp_path):
    path = tmp_path / "aliases.json"
    add_alias("x", "stats api", path)
    assert remove_alias("x", path) is True
    assert "x" not in load_aliases(path)


def test_split_chain_parses_ampersand_separated_commands():
    chain = split_chain("stats api && doctor api --ci")
    assert chain == [["stats", "api"], ["doctor", "api", "--ci"]]


def test_split_chain_handles_quoted_arguments():
    chain = split_chain('grep "hello world" && stats api')
    assert chain[0] == ["grep", "hello world"]


def test_parse_pipeline_sequential_only():
    from devtools.core.alias_store import parse_pipeline

    pipeline = parse_pipeline("stats api && doctor api --ci")
    assert pipeline == [[["stats", "api"]], [["doctor", "api", "--ci"]]]


def test_parse_pipeline_with_pipe_stage():
    from devtools.core.alias_store import parse_pipeline

    pipeline = parse_pipeline("grep api TODO | wc -l")
    assert pipeline == [[["grep", "api", "TODO"], ["wc", "-l"]]]


def test_parse_pipeline_mixes_sequential_and_piped():
    from devtools.core.alias_store import parse_pipeline

    pipeline = parse_pipeline("stats api && grep api TODO | grep -v test")
    assert pipeline == [
        [["stats", "api"]],
        [["grep", "api", "TODO"], ["grep", "-v", "test"]],
    ]