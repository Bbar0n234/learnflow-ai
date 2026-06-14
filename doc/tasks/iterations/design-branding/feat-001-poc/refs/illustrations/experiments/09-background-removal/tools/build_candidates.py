#!/usr/bin/env python3
"""Build the two approved transparent candidate packs."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage


ROOT = next(
    parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists()
)
ITERATION = ROOT / "doc/tasks/iterations/frontend/feat-007-design-branding"
FINAL = ITERATION / "refs/illustrations/final"
CANDIDATES = ITERATION / "refs/illustrations/candidates/transparent"
EXPERIMENT = ITERATION / "refs/illustrations/experiments/09-background-removal"
PROFILES = {
    "soft-balanced": (8.0, 28.0),
    "soft-wide": (12.0, 42.0),
}
THEMES = ("light", "dark")
BACKGROUNDS = {
    "white": (255, 255, 255),
    "cream": (251, 238, 223),
    "black": (0, 0, 0),
    "ui-dark": (24, 20, 32),
}


def estimate_background(rgb: np.ndarray, border_width: int = 12) -> np.ndarray:
    border = np.concatenate(
        (
            rgb[:border_width].reshape(-1, 3),
            rgb[-border_width:].reshape(-1, 3),
            rgb[:, :border_width].reshape(-1, 3),
            rgb[:, -border_width:].reshape(-1, 3),
        )
    )
    median = np.median(border, axis=0)
    distances = np.linalg.norm(border.astype(np.float32) - median, axis=1)
    inliers = border[distances <= np.percentile(distances, 70)]
    return np.median(inliers, axis=0).astype(np.float32)


def soft_alpha(
    rgb: np.ndarray, background: np.ndarray, low: float, high: float
) -> np.ndarray:
    distance = np.linalg.norm(rgb.astype(np.float32) - background, axis=2)
    candidate = distance < high
    seeds = np.zeros_like(candidate, dtype=bool)
    seeds[0] = candidate[0]
    seeds[-1] = candidate[-1]
    seeds[:, 0] = candidate[:, 0]
    seeds[:, -1] = candidate[:, -1]
    connected = ndimage.binary_propagation(seeds, mask=candidate)
    alpha = np.ones(distance.shape, dtype=np.float32)
    alpha[connected] = np.clip(
        (distance[connected] - low) / max(high - low, 1e-6), 0.0, 1.0
    )
    return alpha


def save_candidate(
    source_path: Path, profile: str, low: float, high: float
) -> dict[str, object]:
    started = time.perf_counter()
    source = np.asarray(Image.open(source_path).convert("RGB"))
    background = estimate_background(source)
    alpha = soft_alpha(source, background, low, high)
    rgba = np.dstack(
        (source, np.clip(alpha * 255.0 + 0.5, 0, 255).astype(np.uint8))
    )
    target = CANDIDATES / profile / source_path.parent.name / source_path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(target, optimize=True)
    alpha_u8 = rgba[..., 3]
    return {
        "profile": profile,
        "theme": source_path.parent.name,
        "source": str(source_path.relative_to(ROOT)),
        "output": str(target.relative_to(ROOT)),
        "size": list(Image.open(source_path).size),
        "background_rgb": [round(float(value), 2) for value in background],
        "low_rgb_distance": low,
        "high_rgb_distance": high,
        "alpha_zero_fraction": round(float(np.mean(alpha_u8 == 0)), 6),
        "alpha_partial_fraction": round(
            float(np.mean((alpha_u8 > 0) & (alpha_u8 < 255))), 6
        ),
        "alpha_opaque_fraction": round(float(np.mean(alpha_u8 == 255)), 6),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "output_bytes": target.stat().st_size,
    }


def panel(path: Path, label: str, background: tuple[int, int, int]) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    canvas = Image.new("RGB", image.size, background)
    canvas.paste(image, mask=image.getchannel("A"))
    canvas.thumbnail((430, 300), Image.Resampling.LANCZOS)
    result = Image.new("RGB", (450, 340), "white")
    result.paste(canvas, ((450 - canvas.width) // 2, 30))
    ImageDraw.Draw(result).text(
        (8, 8), label, fill="black", font=ImageFont.load_default()
    )
    return result


def build_sheet(theme: str, background_name: str) -> None:
    sources = sorted((FINAL / theme).glob("*.png"))
    sheet = Image.new(
        "RGB",
        (2 * 450, len(sources) * 340),
        "#d7d3dc",
    )
    background = BACKGROUNDS[background_name]
    for row, source in enumerate(sources):
        for column, profile in enumerate(PROFILES):
            target = CANDIDATES / profile / theme / source.name
            sheet.paste(
                panel(target, f"{source.stem} / {profile}", background),
                (column * 450, row * 340),
            )
    sheet.save(
        CANDIDATES / f"contact-sheet-{theme}-{background_name}.jpg",
        quality=92,
        optimize=True,
    )


def main() -> None:
    runs: list[dict[str, object]] = []
    for profile, (low, high) in PROFILES.items():
        for theme in THEMES:
            for source_path in sorted((FINAL / theme).glob("*.png")):
                runs.append(save_candidate(source_path, profile, low, high))

    for theme in THEMES:
        for background_name in BACKGROUNDS:
            build_sheet(theme, background_name)

    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "status": "awaiting_architect_approval",
        "profiles": {
            profile: {
                "low_rgb_distance": low,
                "high_rgb_distance": high,
                "foreground_decontamination": False,
            }
            for profile, (low, high) in PROFILES.items()
        },
        "runs": runs,
    }
    (CANDIDATES / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Built {len(runs)} candidates in {CANDIDATES}")


if __name__ == "__main__":
    main()
