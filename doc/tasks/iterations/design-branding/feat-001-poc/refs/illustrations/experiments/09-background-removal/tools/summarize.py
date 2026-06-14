#!/usr/bin/env python3
"""Build review sheets and compact benchmark artifacts after a completed run."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = next(
    parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists()
)
EXPERIMENT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "doc/tasks/iterations/frontend/feat-007-design-branding/refs/illustrations/final"
SCENES = ("welcome-hero", "empty-sphere", "empty-artifacts")
THEMES = ("light", "dark")
METHODS = (
    "imagemagick-fuzz-2",
    "imagemagick-fuzz-4",
    "imagemagick-fuzz-6",
    "soft-tight",
    "soft-balanced",
    "soft-wide",
    "decontam-balanced",
    "pymatting-knn-balanced",
    "rembg-u2net",
    "rembg-isnet-anime",
)
PRUNED_METHODS = ("imagemagick-exact", "decontam-tight", "decontam-wide")
UI_DARK = (24, 20, 32)


def panel(image: Image.Image, label: str, size: tuple[int, int]) -> Image.Image:
    canvas = Image.new("RGB", size, "white")
    image.thumbnail((size[0] - 16, size[1] - 36), Image.Resampling.LANCZOS)
    canvas.paste(image, ((size[0] - image.width) // 2, 28))
    ImageDraw.Draw(canvas).text((8, 8), label, fill="black", font=ImageFont.load_default())
    return canvas


def composite(path: Path, background: tuple[int, int, int]) -> Image.Image:
    transparent = Image.open(path).convert("RGBA")
    canvas = Image.new("RGB", transparent.size, background)
    canvas.paste(transparent, mask=transparent.getchannel("A"))
    return canvas


def build_method_sheet(theme: str) -> None:
    width, height = 300, 230
    columns = len(METHODS) + 1
    sheet = Image.new("RGB", (columns * width, len(SCENES) * height), "#d7d3dc")
    for row, scene in enumerate(SCENES):
        source = Image.open(FINAL / theme / f"{scene}.png").convert("RGB")
        sheet.paste(panel(source, f"{scene}: source", (width, height)), (0, row * height))
        for column, method in enumerate(METHODS, start=1):
            path = EXPERIMENT / "outputs" / method / theme / scene / "transparent.png"
            sheet.paste(
                panel(composite(path, UI_DARK), method, (width, height)),
                (column * width, row * height),
            )
    sheet.save(EXPERIMENT / f"contact-sheet-methods-{theme}.jpg", quality=91, optimize=True)


def build_edge_sheet() -> None:
    methods = (
        "imagemagick-fuzz-2",
        "imagemagick-fuzz-4",
        "imagemagick-fuzz-6",
        "soft-balanced",
        "decontam-balanced",
        "pymatting-knn-balanced",
        "rembg-u2net",
        "rembg-isnet-anime",
    )
    panel_size = (420, 420)
    sheet = Image.new("RGB", (4 * panel_size[0], 4 * panel_size[1]), "#d7d3dc")
    for row, theme in enumerate(THEMES):
        for index, method in enumerate(methods):
            image = composite(
                EXPERIMENT
                / "outputs"
                / method
                / theme
                / "welcome-hero"
                / "transparent.png",
                UI_DARK,
            )
            crop = image.crop((430, 70, 1240, 880))
            x = (index % 4) * panel_size[0]
            y = (row * 2 + index // 4) * panel_size[1]
            sheet.paste(panel(crop, f"{theme}: {method}", panel_size), (x, y))
    sheet.save(EXPERIMENT / "contact-sheet-edge-crops.jpg", quality=92, optimize=True)


def compact_artifacts() -> None:
    manifest_path = EXPERIMENT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for run in manifest["runs"]:
        method = run["method"]
        if method in PRUNED_METHODS:
            run["artifacts_retained"] = False
            run["retention_note"] = "Метрики сохранены; дублирующие outputs удалены после ревью."
            continue
        run["artifacts_retained"] = True
        for key in ("preview", "recomposite"):
            old_path = ROOT / run["artifacts"][key]
            if not old_path.exists():
                continue
            new_path = old_path.with_suffix(".webp")
            image = Image.open(old_path).convert("RGB")
            quality = 88 if key == "preview" else 92
            image.save(new_path, "WEBP", quality=quality, method=6)
            old_path.unlink()
            run["artifacts"][key] = str(new_path.relative_to(ROOT))
    for method in PRUNED_METHODS:
        shutil.rmtree(EXPERIMENT / "outputs" / method, ignore_errors=True)
    manifest["retention"] = {
        "kept_methods": list(METHODS),
        "metrics_only_methods": list(PRUNED_METHODS),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    for theme in THEMES:
        build_method_sheet(theme)
    build_edge_sheet()
    compact_artifacts()


if __name__ == "__main__":
    main()
