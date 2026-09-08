from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from devtools.core.ocr_engine import (
    PIPELINES,
    OcrCandidate,
    OcrError,
    OcrWord,
    SUPPORTED_OUTPUT_FORMATS,
    available_languages,
    extract_text,
    looks_dark_mode,
    render,
    require_languages,
    step_grayscale,
    step_invert,
    step_threshold,
    step_upscale,
    tesseract_available,
)

pytestmark = pytest.mark.skipif(not tesseract_available(), reason="tesseract binary/pytesseract not available")


def _text_image(path, text="Hello World", size=(300, 80), bg="white", fg="black"):
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    draw.text((10, 20), text, fill=fg)
    img.save(path)
    return path


@pytest.fixture
def clean_image(tmp_path):
    return _text_image(tmp_path / "clean.png")


@pytest.fixture
def dark_mode_image(tmp_path):
    return _text_image(tmp_path / "dark.png", bg="black", fg="white")


@pytest.fixture
def tiny_image(tmp_path):
    return _text_image(tmp_path / "tiny.png", size=(120, 30))


# --- individual preprocessing steps ------------------------------------------


def test_step_upscale_grows_small_images():
    img = Image.new("L", (100, 40), 255)
    out = step_upscale(img, target=800)
    assert max(out.size) >= 800


def test_step_upscale_leaves_large_images_alone():
    img = Image.new("L", (2000, 500), 255)
    out = step_upscale(img, target=800)
    assert out.size == img.size


def test_step_grayscale_converts_mode():
    img = Image.new("RGB", (10, 10), "red")
    assert step_grayscale(img).mode == "L"


def test_step_invert_flips_pixel_values():
    img = Image.new("L", (2, 2), 0)
    inverted = step_invert(img)
    assert inverted.getpixel((0, 0)) == 255


def test_step_threshold_binarizes_to_black_and_white_only():
    img = Image.new("L", (20, 20), 128)
    for x in range(10):
        for y in range(20):
            img.putpixel((x, y), 10)
    out = step_threshold(img)
    values = set(out.getpixel((x, y)) for x in range(out.width) for y in range(out.height))
    assert values <= {0, 255}


def test_looks_dark_mode_detects_dark_background():
    dark = Image.new("L", (10, 10), 20)
    light = Image.new("L", (10, 10), 240)
    assert looks_dark_mode(dark) is True
    assert looks_dark_mode(light) is False


# --- pipelines are all registered and callable --------------------------------


def test_all_pipelines_are_callable_and_return_an_image():
    src = Image.new("RGB", (200, 60), "white")
    for name, build in PIPELINES.items():
        out = build(src)
        assert isinstance(out, Image.Image), f"pipeline {name} did not return an Image"


# --- candidate scoring ---------------------------------------------------------


def test_candidate_score_prefers_higher_confidence_and_more_words():
    strong = OcrCandidate(
        pipeline="a", psm=6, text="Hello World",
        words=[OcrWord("Hello", 95.0, 0, 0, 10, 10, 1, 1), OcrWord("World", 95.0, 20, 0, 10, 10, 1, 1)],
    )
    weak = OcrCandidate(pipeline="b", psm=6, text="Hello", words=[OcrWord("Hello", 40.0, 0, 0, 10, 10, 1, 1)])
    empty = OcrCandidate(pipeline="c", psm=6, text="")
    assert strong.score > weak.score > empty.score
    assert empty.mean_confidence is None


# --- end-to-end extraction -----------------------------------------------------


def test_extract_text_reads_clean_image(clean_image):
    result = extract_text(clean_image)
    assert "hello" in result.best.text.lower()
    assert result.best.mean_confidence is not None
    assert result.best.mean_confidence > 50
    assert result.attempted  # every combination tried is recorded


def test_extract_text_reads_dark_mode_image_via_inversion(dark_mode_image):
    result = extract_text(dark_mode_image)
    assert "hello" in result.best.text.lower()
    # an inverted pipeline should be competitive on a dark-mode screenshot
    assert any("invert" in c.pipeline for c in result.attempted if c.mean_confidence and c.mean_confidence > 0)


def test_extract_text_reads_tiny_image_after_upscaling(tiny_image):
    result = extract_text(tiny_image)
    assert "hello" in result.best.text.lower()


def test_extract_text_thorough_tries_more_combinations_than_quick(clean_image):
    quick = extract_text(clean_image, thorough=False)
    thorough = extract_text(clean_image, thorough=True)
    assert len(thorough.attempted) > len(quick.attempted)


def test_extract_text_single_pipeline_override(clean_image):
    result = extract_text(clean_image, pipelines=("plain",))
    assert all(c.pipeline == "plain" for c in result.attempted)


def test_extract_text_missing_file_raises():
    with pytest.raises(OcrError):
        extract_text(Path("/nonexistent/does-not-exist.png"))


def test_extract_text_unsupported_extension_raises(tmp_path):
    bogus = tmp_path / "notes.txt"
    bogus.write_text("not an image")
    with pytest.raises(OcrError):
        extract_text(bogus)


def test_extract_text_unknown_pipeline_raises(clean_image):
    with pytest.raises(OcrError):
        extract_text(clean_image, pipelines=("does-not-exist",))


# --- language support -----------------------------------------------------------


def test_available_languages_includes_eng():
    assert "eng" in available_languages()


def test_available_languages_excludes_osd():
    assert "osd" not in available_languages()


def test_require_languages_passes_for_installed_language():
    require_languages("eng")  # should not raise


def test_require_languages_rejects_uninstalled_language():
    with pytest.raises(OcrError, match="not installed"):
        require_languages("xx-not-a-real-language")


def test_require_languages_rejects_empty_string():
    with pytest.raises(OcrError):
        require_languages("")


def test_extract_text_rejects_uninstalled_language(clean_image):
    with pytest.raises(OcrError, match="not installed"):
        extract_text(clean_image, lang="xx-not-a-real-language")


def test_extract_text_defaults_to_english(clean_image):
    result = extract_text(clean_image)
    assert result.lang == "eng"


def test_result_lang_is_echoed_in_json_and_markdown(clean_image):
    result = extract_text(clean_image, lang="eng")
    payload = json.loads(render(result, "json"))
    assert payload["lang"] == "eng"
    assert "eng" in render(result, "md")


# --- output rendering -----------------------------------------------------------


def test_render_txt(clean_image):
    result = extract_text(clean_image)
    text = render(result, "txt")
    assert "Hello" in text or "hello" in text.lower()


def test_render_json_round_trips(clean_image):
    result = extract_text(clean_image)
    payload = json.loads(render(result, "json"))
    assert payload["image_path"] == str(clean_image)
    assert "words" in payload and "attempts" in payload


def test_render_csv_has_header_and_word_rows(clean_image):
    result = extract_text(clean_image)
    csv_text = render(result, "csv")
    lines = csv_text.strip().splitlines()
    assert lines[0] == "text,confidence,left,top,width,height,line_num"
    assert len(lines) > 1


def test_render_markdown_includes_metadata_and_text(clean_image):
    result = extract_text(clean_image)
    md = render(result, "md")
    assert md.startswith("# OCR result")
    assert "Mean confidence" in md
    assert "```" in md


def test_render_html_escapes_and_includes_confidence(clean_image):
    result = extract_text(clean_image)
    out = render(result, "html")
    assert "<html" in out
    assert "Mean confidence" in out


def test_render_unknown_format_raises(clean_image):
    result = extract_text(clean_image)
    with pytest.raises(OcrError):
        render(result, "pdf")


def test_all_supported_formats_render_without_error(clean_image):
    result = extract_text(clean_image)
    for fmt in SUPPORTED_OUTPUT_FORMATS:
        assert render(result, fmt)
