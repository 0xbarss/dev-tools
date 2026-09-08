from __future__ import annotations

import json

import pytest
from PIL import Image, ImageDraw
from typer.testing import CliRunner

from devtools.cli import app
from devtools.core.ocr_engine import tesseract_available

runner = CliRunner()

pytestmark = pytest.mark.skipif(not tesseract_available(), reason="tesseract binary/pytesseract not available")


@pytest.fixture
def clean_image(tmp_path):
    path = tmp_path / "clean.png"
    img = Image.new("RGB", (300, 80), "white")
    ImageDraw.Draw(img).text((10, 20), "Hello World", fill="black")
    img.save(path)
    return path


def test_ocr_defaults_to_txt_on_stdout(clean_image):
    result = runner.invoke(app, ["ocr", str(clean_image)])
    assert result.exit_code == 0, result.output
    assert "hello" in result.output.lower()


def test_ocr_json_format(clean_image):
    result = runner.invoke(app, ["ocr", str(clean_image), "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "hello" in payload["text"].lower()
    assert payload["mean_confidence"] is not None


def test_ocr_global_json_flag_overrides_format(clean_image):
    result = runner.invoke(app, ["--json", "ocr", str(clean_image)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "hello" in payload["text"].lower()


def test_ocr_writes_to_out_file(tmp_path, clean_image):
    out_path = tmp_path / "result.md"
    result = runner.invoke(app, ["ocr", str(clean_image), "--format", "md", "--out", str(out_path)])
    assert result.exit_code == 0, result.output
    assert out_path.is_file()
    assert "Hello" in out_path.read_text() or "hello" in out_path.read_text().lower()


def test_ocr_rejects_unknown_format(clean_image):
    result = runner.invoke(app, ["ocr", str(clean_image), "--format", "xml"])
    assert result.exit_code == 2
    assert "--format must be one of" in result.output


def test_ocr_rejects_unknown_pipeline(clean_image):
    result = runner.invoke(app, ["ocr", str(clean_image), "--pipeline", "nonsense"])
    assert result.exit_code == 2


def test_ocr_missing_image_fails_cleanly(tmp_path):
    result = runner.invoke(app, ["ocr", str(tmp_path / "nope.png")])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_ocr_show_attempts_lists_every_combination(clean_image):
    result = runner.invoke(app, ["ocr", str(clean_image), "--show-attempts"])
    assert result.exit_code == 0, result.output
    assert "psm=" in result.output


def test_ocr_thorough_flag_runs_without_error(clean_image):
    result = runner.invoke(app, ["ocr", str(clean_image), "--thorough", "--format", "csv"])
    assert result.exit_code == 0, result.output
    assert "text,confidence" in result.output


def test_ocr_list_langs(clean_image):
    result = runner.invoke(app, ["ocr", "--list-langs"])
    assert result.exit_code == 0, result.output
    assert "eng" in result.output


def test_ocr_list_langs_json():
    result = runner.invoke(app, ["--json", "ocr", "--list-langs"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "eng" in payload["languages"]


def test_ocr_missing_image_without_list_langs_fails_cleanly():
    result = runner.invoke(app, ["ocr"])
    assert result.exit_code == 2
    assert "list-langs" in result.output.lower()


def test_ocr_rejects_uninstalled_language(clean_image):
    result = runner.invoke(app, ["ocr", str(clean_image), "--lang", "xx-not-a-real-language"])
    assert result.exit_code == 1
    assert "not installed" in result.output.lower()


def test_ocr_lang_flag_is_accepted_for_english(clean_image):
    result = runner.invoke(app, ["ocr", str(clean_image), "--lang", "eng"])
    assert result.exit_code == 0, result.output
    assert "hello" in result.output.lower()
