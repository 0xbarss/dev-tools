"""`devtools ocr` — extract text from difficult screenshots (tiny, blurry,
low-contrast, compressed, or dark-mode) using local Tesseract OCR with
automatic image preprocessing.

Standalone tool, not project-scoped: it operates on a single image path,
same as `sonar-import` operates on a single report path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from devtools.commands._shared import fail
from devtools.core.exit_codes import GENERAL_ERROR, INVALID_USAGE
from devtools.core.ocr_engine import (
    PIPELINES,
    OcrError,
    SUPPORTED_OUTPUT_FORMATS,
    available_languages,
    extract_text,
    render,
    tesseract_available,
)

app = typer.Typer()


@app.command()
def ocr(
    ctx: typer.Context,
    image: Optional[Path] = typer.Argument(
        None, help="Path to the screenshot/image to OCR. Not required with --list-langs."
    ),
    fmt: str = typer.Option(
        "txt", "--format", "-f", help=f"Output format: {', '.join(SUPPORTED_OUTPUT_FORMATS)}."
    ),
    lang: str = typer.Option(
        "eng",
        "--lang",
        "-l",
        help="Tesseract language code(s) to OCR with, e.g. 'tur', or 'eng+tur' to read mixed-language "
        "text. Must already be installed (see --list-langs).",
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", "-o", help="Write the result to this file instead of printing it."
    ),
    thorough: bool = typer.Option(
        False,
        "--thorough",
        help="Try every preprocessing pipeline and more PSM modes (slower, best for text that a quick pass misses).",
    ),
    pipeline: Optional[str] = typer.Option(
        None,
        "--pipeline",
        help=f"Run only this single preprocessing pipeline instead of comparing several. One of: {', '.join(PIPELINES)}.",
    ),
    show_attempts: bool = typer.Option(
        False,
        "--show-attempts",
        help="Also print the confidence score of every (pipeline, PSM) attempt that was tried, not just the winner.",
    ),
    list_langs: bool = typer.Option(
        False,
        "--list-langs",
        help="List Tesseract language codes currently installed and exit (no image needed).",
    ),
) -> None:
    """OCR an image, trying multiple preprocessing pipelines (upscale,
    grayscale, contrast, sharpen, denoise, threshold, invert) crossed with
    several Tesseract page-segmentation modes, and keep whichever attempt
    scored the highest average word confidence. Fully offline.

    Examples:

        devtools ocr screenshot.png

        devtools ocr dark_mode_shot.png --format json --out result.json

        devtools ocr tiny_text.jpg --thorough --show-attempts

        devtools ocr turkish_ui.png --lang tur

        devtools ocr mixed.png --lang eng+tur

        devtools ocr --list-langs
    """
    state = ctx.obj

    if not tesseract_available():
        fail(
            ctx,
            GENERAL_ERROR,
            "The `tesseract` binary (or the `pytesseract` package) isn't available. "
            "Install Tesseract (e.g. `apt install tesseract-ocr` / `pacman -S tesseract` / `brew install tesseract`) "
            "and `pip install pytesseract`.",
        )

    if list_langs:
        try:
            langs = available_languages()
        except OcrError as exc:
            fail(ctx, GENERAL_ERROR, str(exc))
            return
        if state.output.is_json:
            state.output.emit_json({"languages": langs})
        else:
            state.output.print(", ".join(langs) if langs else "(none installed)")
        return

    if image is None:
        fail(ctx, INVALID_USAGE, "Missing argument 'IMAGE' (or pass --list-langs to see installed languages).")
    if fmt not in SUPPORTED_OUTPUT_FORMATS:
        fail(ctx, INVALID_USAGE, f"--format must be one of: {', '.join(SUPPORTED_OUTPUT_FORMATS)}")
    if pipeline is not None and pipeline not in PIPELINES:
        fail(ctx, INVALID_USAGE, f"--pipeline must be one of: {', '.join(PIPELINES)}")

    try:
        result = extract_text(
            image,
            thorough=thorough,
            pipelines=(pipeline,) if pipeline else None,
            lang=lang,
        )
    except OcrError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))
        return

    content = render(result, fmt)

    if out is not None:
        out.write_text(content, encoding="utf-8")
        state.output.print(f"[green]Wrote {out}[/green]")
    elif state.output.is_json and fmt != "json":
        # --json is a global flag; if the person passed both, JSON wins so
        # scripting against `devtools ocr` is never ambiguous.
        state.output.emit_json(result.as_dict())
    else:
        print(content)

    if show_attempts and not state.output.quiet:
        state.output.print("")
        rows = sorted(result.attempted, key=lambda c: c.score, reverse=True)
        for c in rows:
            conf = f"{c.mean_confidence:.1f}%" if c.mean_confidence is not None else "n/a"
            marker = "*" if c is result.best else " "
            state.output.print(f"{marker} {c.pipeline:<30} psm={c.psm:<3} conf={conf:<8} words={c.word_count}")
