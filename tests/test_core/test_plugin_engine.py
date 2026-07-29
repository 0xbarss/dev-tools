from __future__ import annotations

from importlib.metadata import EntryPoint

import pytest
import typer

from devtools.core import plugin_engine


@pytest.fixture(autouse=True)
def _isolated_plugins_dir(tmp_path, monkeypatch):
    """Every test gets its own empty plugins directory, same isolation
    pattern as the config/cache dir env-var overrides used elsewhere."""
    d = tmp_path / "plugins"
    monkeypatch.setattr(plugin_engine, "plugins_dir", lambda: d)
    return d


_VALID_PLUGIN_SOURCE = '''
import typer

DEVTOOLS_API_VERSION = "1"

def register(app: typer.Typer) -> None:
    @app.command("hello-from-plugin")
    def hello():
        print("hello from plugin")
'''

_NO_REGISTER_SOURCE = "x = 1\n"

_BROKEN_SOURCE = "this is not valid python (((\n"


def _write_plugin(tmp_path, name, source):
    p = tmp_path / f"{name}.py"
    p.write_text(source)
    return p


# --- script plugin install/list/remove ------------------------------------


def test_install_script_plugin_copies_file_into_plugins_dir(tmp_path, _isolated_plugins_dir):
    src = _write_plugin(tmp_path, "my_check", _VALID_PLUGIN_SOURCE)
    info = plugin_engine.install_script_plugin(src)
    assert info.name == "my_check"
    assert info.source == "script"
    assert (_isolated_plugins_dir / "my_check.py").exists()
    assert info.api_version == "1"


def test_install_script_plugin_rejects_non_py_file(tmp_path):
    src = tmp_path / "notes.txt"
    src.write_text("hi")
    with pytest.raises(plugin_engine.PluginError):
        plugin_engine.install_script_plugin(src)


def test_install_script_plugin_rejects_file_without_register(tmp_path):
    src = _write_plugin(tmp_path, "bad_plugin", _NO_REGISTER_SOURCE)
    with pytest.raises(plugin_engine.PluginError):
        plugin_engine.install_script_plugin(src)


def test_install_script_plugin_rejects_syntactically_broken_file(tmp_path):
    src = _write_plugin(tmp_path, "broken_plugin", _BROKEN_SOURCE)
    with pytest.raises(plugin_engine.PluginError):
        plugin_engine.install_script_plugin(src)


def test_list_script_plugins_reports_installed_plugin(tmp_path, _isolated_plugins_dir):
    src = _write_plugin(tmp_path, "my_check", _VALID_PLUGIN_SOURCE)
    plugin_engine.install_script_plugin(src)

    infos = plugin_engine.list_script_plugins()
    assert len(infos) == 1
    assert infos[0].name == "my_check"
    assert infos[0].error is None
    assert infos[0].api_compatible is True


def test_list_script_plugins_flags_incompatible_api_version(tmp_path, _isolated_plugins_dir):
    source = _VALID_PLUGIN_SOURCE.replace('"1"', '"999"')
    src = _write_plugin(tmp_path, "future_plugin", source)
    plugin_engine.install_script_plugin(src)

    infos = plugin_engine.list_script_plugins()
    assert infos[0].api_version == "999"
    assert infos[0].api_compatible is False


def test_list_script_plugins_empty_when_no_plugins_dir(_isolated_plugins_dir):
    assert plugin_engine.list_script_plugins() == []


def test_remove_script_plugin_deletes_the_file(tmp_path, _isolated_plugins_dir):
    src = _write_plugin(tmp_path, "my_check", _VALID_PLUGIN_SOURCE)
    plugin_engine.install_script_plugin(src)

    assert plugin_engine.remove_script_plugin("my_check") is True
    assert not (_isolated_plugins_dir / "my_check.py").exists()


def test_remove_script_plugin_returns_false_when_missing(_isolated_plugins_dir):
    assert plugin_engine.remove_script_plugin("does_not_exist") is False


# --- load_all_plugins actually registers commands --------------------------


def test_load_all_plugins_registers_script_plugin_command(tmp_path, _isolated_plugins_dir):
    src = _write_plugin(tmp_path, "my_check", _VALID_PLUGIN_SOURCE)
    plugin_engine.install_script_plugin(src)

    app = typer.Typer()
    results = plugin_engine.load_all_plugins(app)

    assert len(results) == 1
    assert results[0].loaded is True
    assert results[0].error is None

    from typer.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "hello from plugin" in result.output


def test_load_all_plugins_reports_error_without_crashing(tmp_path, _isolated_plugins_dir):
    src = _write_plugin(tmp_path, "bad_plugin", _NO_REGISTER_SOURCE)
    _isolated_plugins_dir.mkdir(parents=True, exist_ok=True)
    import shutil

    shutil.copy2(src, _isolated_plugins_dir / "bad_plugin.py")

    app = typer.Typer()
    results = plugin_engine.load_all_plugins(app)
    assert len(results) == 1
    assert results[0].loaded is False
    assert results[0].error is not None


# --- entry-point plugins (discovery only, via monkeypatched metadata) ------


def _make_fake_entry_point(name, module):
    """A real EntryPoint needs a distribution; for discovery tests we only
    need `.name`/`.value`/`.load()` to behave, so a tiny stand-in avoids
    needing an actually-installed fake package."""

    class _Fake:
        def __init__(self):
            self.name = name
            self.value = f"{module.__name__}"

        def load(self):
            return module

    return _Fake()


def test_list_entry_point_plugins_reads_api_version(monkeypatch):
    import types

    fake_module = types.ModuleType("fake_devtools_plugin")
    fake_module.DEVTOOLS_API_VERSION = "1"

    def fake_register(app):
        pass

    fake_module.register = fake_register

    ep = _make_fake_entry_point("fake", fake_module)
    monkeypatch.setattr(plugin_engine, "entry_points", lambda group=None: [ep])

    infos = plugin_engine.list_entry_point_plugins()
    assert len(infos) == 1
    assert infos[0].name == "fake"
    assert infos[0].api_version == "1"
    assert infos[0].error is None


def test_list_entry_point_plugins_reports_missing_register(monkeypatch):
    import types

    fake_module = types.ModuleType("fake_devtools_plugin_bad")
    ep = _make_fake_entry_point("fake_bad", fake_module)
    monkeypatch.setattr(plugin_engine, "entry_points", lambda group=None: [ep])

    infos = plugin_engine.list_entry_point_plugins()
    assert infos[0].error is not None


def test_load_all_plugins_registers_entry_point_command(monkeypatch):
    import types

    fake_module = types.ModuleType("fake_devtools_plugin_ep")

    def fake_register(app):
        @app.command("hello-from-entry-point")
        def hello():
            print("hello from entry point")

    fake_module.register = fake_register

    ep = _make_fake_entry_point("fake_ep", fake_module)
    monkeypatch.setattr(plugin_engine, "entry_points", lambda group=None: [ep])

    app = typer.Typer()
    results = plugin_engine.load_all_plugins(app)
    assert results[0].loaded is True

    from typer.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "hello from entry point" in result.output