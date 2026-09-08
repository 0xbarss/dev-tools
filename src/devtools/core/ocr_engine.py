"""`devtools ocr` engine — text extraction from difficult screenshots.

Screenshots that trip up a plain `tesseract image.png` run tend to fail for
a handful of predictable reasons: the text is tiny (UI chrome, status bars),
the source was heavily JPEG-compressed, the shot is slightly blurry, contrast
is low (light-gray-on-white), or it's a dark-mode screenshot (light text on
a dark background, which Tesseract -- trained mostly on dark-on-light text
-- handles poorly).

Rather than guessing which of those applies, this engine runs the image
through several *preprocessing pipelines* (upscale, grayscale, contrast,
sharpen, denoise, threshold, invert -- composed in different combinations)
crossed with a few Tesseract page-segmentation modes (PSM), OCRs every
combination, and scores each attempt using Tesseract's own per-word
confidence values. The highest-scoring attempt wins. This is slower than a
single `tesseract` call, but for a screenshot that already failed once,
trading a second or two of extra CPU for a readable result is the point.

Fully offline: the only external dependency is a local `tesseract` binary
(driven via `pytesseract`) plus Pillow for image preprocessing. No network
calls, no cloud OCR API.
"""

from __future__ import annotations

import csv
import html
import io
import json as _json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except ImportError:  # pragma: no cover - exercised via OcrError path in tests
    Image = None  # type: ignore[assignment]
    ImageEnhance = None  # type: ignore[assignment]
    ImageFilter = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]

try:
    import pytesseract
    from pytesseract import Output
except ImportError:  # pragma: no cover - exercised via OcrError path in tests
    pytesseract = None  # type: ignore[assignment]
    Output = None  # type: ignore[assignment]


class OcrError(RuntimeError):
    """Raised for any OCR setup or processing failure (missing binary,
    unreadable image, unsupported format, etc.)."""


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".tif", ".webp"}
SUPPORTED_OUTPUT_FORMATS = ("txt", "json", "csv", "md", "html")

# PSM (page segmentation mode) reference, for anyone reading result JSON:
#   3  = fully automatic layout analysis (Tesseract default)
#   4  = assume a single column of text of variable sizes
#   6  = assume a single uniform block of text (good for cropped UI panels)
#   7  = treat the image as a single text line
#   11 = sparse text -- find as much text as possible, no particular order
_QUICK_PSM_MODES = (6, 3)
_THOROUGH_PSM_MODES = (6, 3, 4, 7, 11)

_MIN_UPSCALE_DIMENSION = 1600  # target long-edge size when upscaling tiny screenshots


# --- data model --------------------------------------------------------------


@dataclass
class OcrWord:
    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int
    line_num: int
    block_num: int

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "confidence": round(self.confidence, 2),
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
            "line_num": self.line_num,
            "block_num": self.block_num,
        }


@dataclass
class OcrCandidate:
    """One (preprocessing pipeline, PSM mode) attempt."""

    pipeline: str
    psm: int
    text: str
    words: list[OcrWord] = field(default_factory=list)

    @property
    def mean_confidence(self) -> float | None:
        if not self.words:
            return None
        return sum(w.confidence for w in self.words) / len(self.words)

    @property
    def word_count(self) -> int:
        return len(self.words)

    @property
    def score(self) -> float:
        """Ranking score: mean confidence, with a small bonus for finding
        more words so that a confident-but-empty result never beats a
        confident result that actually extracted text."""
        conf = self.mean_confidence
        if conf is None:
            return -1.0
        return conf + min(self.word_count, 50) * 0.05

    def summary(self) -> dict:
        return {
            "pipeline": self.pipeline,
            "psm": self.psm,
            "mean_confidence": None if self.mean_confidence is None else round(self.mean_confidence, 2),
            "word_count": self.word_count,
        }


@dataclass
class OcrResult:
    image_path: str
    best: OcrCandidate
    attempted: list[OcrCandidate]
    elapsed_seconds: float
    lang: str = "eng"

    @property
    def lines(self) -> list[str]:
        """Best candidate's text, reconstructed as a list of non-blank lines."""
        return [ln for ln in self.best.text.splitlines() if ln.strip()]

    def as_dict(self) -> dict:
        return {
            "image_path": self.image_path,
            "lang": self.lang,
            "text": self.best.text,
            "mean_confidence": None if self.best.mean_confidence is None else round(self.best.mean_confidence, 2),
            "pipeline": self.best.pipeline,
            "psm": self.best.psm,
            "word_count": self.best.word_count,
            "words": [w.as_dict() for w in self.best.words],
            "attempts": [c.summary() for c in self.attempted],
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }


# --- availability --------------------------------------------------------------


def tesseract_available() -> bool:
    if pytesseract is None or Image is None:
        return False
    return shutil.which("tesseract") is not None


def require_tesseract() -> None:
    missing = []
    if Image is None:
        missing.append("Pillow")
    if pytesseract is None:
        missing.append("pytesseract")
    if missing:
        raise OcrError(
            f"Missing required package(s) for `devtools ocr`: {', '.join(missing)}. Install with "
            f"`pip install {' '.join(m.lower() for m in missing)}` "
            '(devtools\' own optional extra: `pip install "devtools[ocr]"`).'
        )
    if shutil.which("tesseract") is None:
        raise OcrError(
            "The `tesseract` binary was not found on PATH. Install it with your package manager, "
            "e.g. `apt install tesseract-ocr` / `pacman -S tesseract` / `brew install tesseract`."
        )


def available_languages() -> list[str]:
    """Language codes Tesseract can currently see (installed .traineddata
    files), e.g. ['eng', 'tur', 'osd']. `osd` (orientation/script detection)
    isn't a real OCR language and is filtered out."""
    require_tesseract()
    try:
        langs = pytesseract.get_languages(config="")
    except Exception as exc:
        raise OcrError(f"Could not list installed Tesseract languages: {exc}") from exc
    return sorted(l for l in langs if l != "osd")


def require_languages(lang: str) -> None:
    """Validate a `-l` value (e.g. 'eng', 'tur', or 'eng+tur') against what's
    actually installed, and fail with an actionable message rather than
    letting Tesseract's own opaque error surface."""
    requested = [code.strip() for code in lang.split("+") if code.strip()]
    if not requested:
        raise OcrError("--lang cannot be empty. Use a Tesseract language code, e.g. 'eng', 'tur', or 'eng+tur'.")
    installed = set(available_languages())
    missing = [code for code in requested if code not in installed]
    if missing:
        raise OcrError(
            f"Language data not installed for: {', '.join(missing)}. "
            f"Currently installed: {', '.join(sorted(installed)) or 'none'}. "
            f"Install the missing pack, e.g. `pacman -S tesseract-data-{missing[0]}` (Arch/EndeavourOS) "
            f"or `apt install tesseract-ocr-{missing[0]}` (Debian/Ubuntu), then retry."
        )


# --- individual preprocessing steps (composable, each Image -> Image) --------


def step_upscale(img: Image.Image, target: int = _MIN_UPSCALE_DIMENSION) -> Image.Image:
    """Scale small screenshots up so tiny UI text has enough pixels for
    Tesseract to resolve glyph shapes. No-op if the image is already large."""
    long_edge = max(img.size)
    if long_edge >= target:
        return img
    factor = target / long_edge
    new_size = (max(1, round(img.width * factor)), max(1, round(img.height * factor)))
    return img.resize(new_size, Image.LANCZOS)


def step_grayscale(img: Image.Image) -> Image.Image:
    return img.convert("L")


def step_autocontrast(img: Image.Image) -> Image.Image:
    return ImageOps.autocontrast(img, cutoff=1)


def step_boost_contrast(img: Image.Image, factor: float = 1.8) -> Image.Image:
    return ImageEnhance.Contrast(img).enhance(factor)


def step_sharpen(img: Image.Image) -> Image.Image:
    return img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=2))


def step_denoise(img: Image.Image) -> Image.Image:
    """Light median-filter denoise -- smooths JPEG block artifacts and
    speckle noise without erasing thin glyph strokes."""
    return img.filter(ImageFilter.MedianFilter(size=3))


def step_threshold(img: Image.Image) -> Image.Image:
    """Binarize using Otsu's method computed from the grayscale histogram
    (no numpy/opencv needed -- just Pillow's built-in histogram)."""
    gray = img.convert("L") if img.mode != "L" else img
    threshold = _otsu_threshold(gray.histogram())
    return gray.point(lambda p: 255 if p > threshold else 0)


def step_invert(img: Image.Image) -> Image.Image:
    """Flip light-text-on-dark to dark-text-on-light, for dark-mode
    screenshots. Tesseract is trained overwhelmingly on the latter."""
    if img.mode == "L":
        return ImageOps.invert(img)
    return ImageOps.invert(img.convert("RGB")).convert(img.mode if img.mode != "RGBA" else "RGB")


def _otsu_threshold(histogram: list[int]) -> int:
    total = sum(histogram)
    if total == 0:
        return 128
    sum_all = sum(i * h for i, h in enumerate(histogram))
    sum_bg, weight_bg, max_variance, best_threshold = 0.0, 0, 0.0, 128
    for i, count in enumerate(histogram):
        weight_bg += count
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += i * count
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_all - sum_bg) / weight_fg
        variance = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if variance > max_variance:
            max_variance = variance
            best_threshold = i
    return best_threshold


def looks_dark_mode(img: Image.Image) -> bool:
    """Heuristic: sample the grayscale histogram: if the image is
    predominantly dark (dark background, light text) it's worth
    prioritizing the inverted pipelines."""
    gray = img.convert("L")
    hist = gray.histogram()
    total = sum(hist)
    if total == 0:
        return False
    dark_pixels = sum(hist[:96])
    return (dark_pixels / total) > 0.55


# --- preprocessing pipelines (name -> function composing the steps above) ----

_Pipeline = Callable[[Any], Any]


def _build_pipelines() -> dict[str, _Pipeline]:
    def plain(img: Image.Image) -> Image.Image:
        return step_upscale(step_grayscale(img))

    def high_contrast(img: Image.Image) -> Image.Image:
        img = step_upscale(step_grayscale(img))
        return step_boost_contrast(step_autocontrast(img))

    def sharpened(img: Image.Image) -> Image.Image:
        img = step_upscale(step_grayscale(img))
        return step_sharpen(step_autocontrast(img))

    def denoised(img: Image.Image) -> Image.Image:
        img = step_upscale(step_grayscale(img))
        return step_autocontrast(step_denoise(img))

    def binarized(img: Image.Image) -> Image.Image:
        img = step_upscale(step_grayscale(img))
        return step_threshold(step_autocontrast(img))

    def denoised_binarized(img: Image.Image) -> Image.Image:
        img = step_upscale(step_grayscale(img))
        return step_threshold(step_denoise(img))

    def sharpened_binarized(img: Image.Image) -> Image.Image:
        img = step_upscale(step_grayscale(img))
        return step_threshold(step_sharpen(img))

    def inverted(img: Image.Image) -> Image.Image:
        img = step_upscale(step_grayscale(img))
        return step_autocontrast(step_invert(img))

    def inverted_binarized(img: Image.Image) -> Image.Image:
        img = step_upscale(step_grayscale(img))
        return step_threshold(step_invert(img))

    def inverted_denoised_binarized(img: Image.Image) -> Image.Image:
        img = step_upscale(step_grayscale(img))
        return step_threshold(step_denoise(step_invert(img)))

    return {
        "plain": plain,
        "high_contrast": high_contrast,
        "sharpened": sharpened,
        "denoised": denoised,
        "binarized": binarized,
        "denoised_binarized": denoised_binarized,
        "sharpened_binarized": sharpened_binarized,
        "inverted": inverted,
        "inverted_binarized": inverted_binarized,
        "inverted_denoised_binarized": inverted_denoised_binarized,
    }


PIPELINES: dict[str, _Pipeline] = _build_pipelines()

# Kept small on purpose for the default/"quick" run; "thorough" adds the rest.
_QUICK_PIPELINES = ("plain", "high_contrast", "binarized", "denoised_binarized", "inverted_binarized")


# --- OCR execution -------------------------------------------------------------


def _run_tesseract(img: Image.Image, psm: int, lang: str) -> tuple[str, list[OcrWord]]:
    config = f"--psm {psm}"
    data = pytesseract.image_to_data(img, lang=lang, config=config, output_type=Output.DICT)
    words: list[OcrWord] = []
    n = len(data.get("text", []))
    for i in range(n):
        text = data["text"][i].strip()
        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1.0
        if not text or conf < 0:
            continue
        words.append(
            OcrWord(
                text=text,
                confidence=conf,
                left=int(data["left"][i]),
                top=int(data["top"][i]),
                width=int(data["width"][i]),
                height=int(data["height"][i]),
                line_num=int(data.get("line_num", [0] * n)[i]),
                block_num=int(data.get("block_num", [0] * n)[i]),
            )
        )
    full_text = pytesseract.image_to_string(img, lang=lang, config=config).strip()
    return full_text, words


def extract_text(
    image_path: Path,
    thorough: bool = False,
    psm_modes: tuple[int, ...] | None = None,
    pipelines: tuple[str, ...] | None = None,
    lang: str = "eng",
) -> OcrResult:
    """Run every (pipeline, PSM) combination, OCR each, and return the
    highest-scoring result plus a summary of every attempt.

    `thorough=True` tries the full pipeline set and more PSM modes -- slower,
    worth it for an image that already failed a quick pass. `pipelines` /
    `psm_modes` let a caller override either set explicitly. `lang` is a
    Tesseract language code, or several joined with '+' (e.g. 'eng+tur') to
    OCR mixed-language text -- run `devtools ocr --list-langs` (or
    `tesseract --list-langs`) to see what's installed.
    """
    require_tesseract()
    require_languages(lang)

    if not image_path.is_file():
        raise OcrError(f"Image not found: {image_path}")
    if image_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        raise OcrError(
            f"Unsupported image type '{image_path.suffix}'. Supported: {', '.join(sorted(SUPPORTED_IMAGE_SUFFIXES))}"
        )

    try:
        source = Image.open(image_path)
        source.load()
    except Exception as exc:  # PIL raises a variety of exception types
        raise OcrError(f"Could not open '{image_path}' as an image: {exc}") from exc

    pipeline_names = pipelines or (tuple(PIPELINES) if thorough else _QUICK_PIPELINES)
    modes = psm_modes or (_THOROUGH_PSM_MODES if thorough else _QUICK_PSM_MODES)

    start = time.perf_counter()
    attempted: list[OcrCandidate] = []
    for name in pipeline_names:
        build = PIPELINES.get(name)
        if build is None:
            raise OcrError(f"Unknown preprocessing pipeline '{name}'. Known: {', '.join(PIPELINES)}")
        try:
            processed = build(source)
        except Exception:  # a pipeline failing shouldn't sink the whole run
            continue
        for psm in modes:
            try:
                text, words = _run_tesseract(processed, psm, lang)
            except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError) as exc:
                # A broken Tesseract installation (missing binary, missing
                # language data, bad TESSDATA_PREFIX, ...) fails identically
                # for every pipeline/PSM combination -- retrying the other
                # nine pipelines just burns time before hitting the same
                # wall, so surface it immediately instead of swallowing it.
                raise OcrError(_friendly_tesseract_error(exc)) from exc
            except Exception:
                continue
            attempted.append(OcrCandidate(pipeline=name, psm=psm, text=text, words=words))

    if not attempted:
        # Last resort: a single unprocessed pass, so the tool never returns
        # nothing just because every scored candidate errored out.
        try:
            text, words = _run_tesseract(source.convert("L"), 3, lang)
        except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError) as exc:
            raise OcrError(_friendly_tesseract_error(exc)) from exc
        attempted.append(OcrCandidate(pipeline="fallback", psm=3, text=text, words=words))

    best = max(attempted, key=lambda c: c.score)
    elapsed = time.perf_counter() - start
    return OcrResult(image_path=str(image_path), best=best, attempted=attempted, elapsed_seconds=elapsed, lang=lang)


def _friendly_tesseract_error(exc: Exception) -> str:
    message = str(exc)
    if "tessdata" in message.lower() or "TESSDATA_PREFIX" in message:
        return (
            "Tesseract couldn't find the requested language data. "
            "Install the missing language pack (e.g. `pacman -S tesseract-data-eng` on Arch/EndeavourOS, "
            "`apt install tesseract-ocr-eng` on Debian/Ubuntu) or point TESSDATA_PREFIX at the directory "
            "containing it. Original error: " + message
        )
    return f"Tesseract failed to run: {message}"


# --- output formatting ---------------------------------------------------------


def to_txt(result: OcrResult) -> str:
    return result.best.text.strip() + "\n"


def to_json(result: OcrResult) -> str:
    return _json.dumps(result.as_dict(), indent=2)


def to_csv(result: OcrResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["text", "confidence", "left", "top", "width", "height", "line_num"])
    if result.best.words:
        for w in result.best.words:
            writer.writerow([w.text, round(w.confidence, 2), w.left, w.top, w.width, w.height, w.line_num])
    else:
        for line in result.lines:
            writer.writerow([line, "", "", "", "", "", ""])
    return buf.getvalue()


def to_markdown(result: OcrResult) -> str:
    conf = result.best.mean_confidence
    conf_str = f"{conf:.1f}%" if conf is not None else "n/a"
    lines = [
        f"# OCR result — {Path(result.image_path).name}",
        "",
        f"- **Source:** `{result.image_path}`",
        f"- **Language:** `{result.lang}`",
        f"- **Preprocessing:** `{result.best.pipeline}` (PSM {result.best.psm})",
        f"- **Mean confidence:** {conf_str}",
        f"- **Words detected:** {result.best.word_count}",
        "",
        "## Extracted text",
        "",
        "```",
        result.best.text.strip(),
        "```",
    ]
    return "\n".join(lines) + "\n"


def to_html(result: OcrResult) -> str:
    conf = result.best.mean_confidence
    conf_str = f"{conf:.1f}%" if conf is not None else "n/a"
    title = html.escape(Path(result.image_path).name)

    if result.best.words:
        spans = []
        last_line = None
        for w in result.best.words:
            if w.line_num != last_line:
                if last_line is not None:
                    spans.append("<br>")
                last_line = w.line_num
            # Green -> red as confidence drops, so low-trust words are easy to spot.
            hue = max(0, min(120, round(w.confidence * 1.2)))
            spans.append(
                f'<span class="w" style="background:hsl({hue},70%,85%)" title="{w.confidence:.1f}%">'
                f"{html.escape(w.text)}</span> "
            )
        body = "".join(spans)
    else:
        body = "<br>".join(html.escape(line) for line in result.lines)

    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>OCR — {title}</title>"
        "<style>body{font-family:sans-serif;margin:2rem;max-width:760px}"
        ".meta{color:#555;font-size:0.9em;margin-bottom:1.5rem}"
        ".w{padding:1px 2px;border-radius:2px}</style></head><body>"
        f"<h1>OCR result — {title}</h1>"
        f"<p class='meta'>Language: <code>{html.escape(result.lang)}</code> &middot; "
        f"Preprocessing: <code>{html.escape(result.best.pipeline)}</code> "
        f"(PSM {result.best.psm}) &middot; Mean confidence: {conf_str} &middot; "
        f"{result.best.word_count} words</p>"
        f"<div class='text'>{body}</div>"
        "</body></html>"
    )


_WRITERS: dict[str, Callable[[OcrResult], str]] = {
    "txt": to_txt,
    "json": to_json,
    "csv": to_csv,
    "md": to_markdown,
    "html": to_html,
}


def render(result: OcrResult, fmt: str) -> str:
    writer = _WRITERS.get(fmt)
    if writer is None:
        raise OcrError(f"Unknown output format '{fmt}'. Supported: {', '.join(SUPPORTED_OUTPUT_FORMATS)}")
    return writer(result)
