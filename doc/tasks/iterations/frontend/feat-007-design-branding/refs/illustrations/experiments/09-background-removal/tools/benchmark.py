#!/usr/bin/env python3
"""Reproducible background-removal benchmark for LearnFlowAI illustrations."""

from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage


ROOT = next(
    parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists()
)
EXPERIMENT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "doc/tasks/iterations/frontend/feat-007-design-branding/refs/illustrations/final"
SCENES = ("welcome-hero", "empty-sphere", "empty-artifacts")
THEMES = ("light", "dark")
PREVIEW_BACKGROUNDS = {
    "white": (255, 255, 255),
    "cream": (251, 238, 223),
    "black": (0, 0, 0),
    "ui-dark": (24, 20, 32),
}
SOFT_THRESHOLDS = {
    "soft-tight": (5.0, 18.0),
    "soft-balanced": (8.0, 28.0),
    "soft-wide": (12.0, 42.0),
}


def srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    rgb = rgb / 255.0
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(rgb: np.ndarray) -> np.ndarray:
    rgb = np.clip(rgb, 0.0, 1.0)
    return np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * rgb ** (1 / 2.4) - 0.055)


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


def border_connected(candidate: np.ndarray) -> np.ndarray:
    seeds = np.zeros_like(candidate, dtype=bool)
    seeds[0] = candidate[0]
    seeds[-1] = candidate[-1]
    seeds[:, 0] = candidate[:, 0]
    seeds[:, -1] = candidate[:, -1]
    return ndimage.binary_propagation(seeds, mask=candidate)


def soft_alpha(
    rgb: np.ndarray, background: np.ndarray, low: float, high: float
) -> np.ndarray:
    distance = np.linalg.norm(rgb.astype(np.float32) - background, axis=2)
    connected = border_connected(distance < high)
    alpha = np.ones(distance.shape, dtype=np.float32)
    alpha[connected] = np.clip(
        (distance[connected] - low) / max(high - low, 1e-6), 0.0, 1.0
    )
    return alpha


def decontaminate(
    rgb: np.ndarray, alpha: np.ndarray, background: np.ndarray
) -> np.ndarray:
    observed = srgb_to_linear(rgb.astype(np.float32))
    bg = srgb_to_linear(background.astype(np.float32))
    safe_alpha = np.maximum(alpha[..., None], 0.04)
    foreground = (observed - (1.0 - alpha[..., None]) * bg) / safe_alpha
    foreground = linear_to_srgb(foreground) * 255.0
    foreground[alpha < 0.01] = 0.0
    return np.clip(foreground, 0, 255).astype(np.uint8)


def rgba_image(rgb: np.ndarray, alpha: np.ndarray) -> Image.Image:
    rgba = np.dstack((rgb, np.clip(alpha * 255.0 + 0.5, 0, 255).astype(np.uint8)))
    return Image.fromarray(rgba, "RGBA")


def metrics(
    source: np.ndarray,
    foreground: np.ndarray,
    alpha: np.ndarray,
    background: np.ndarray,
    elapsed: float,
    output_path: Path,
) -> dict[str, float | int | list[float]]:
    recomposite = (
        foreground.astype(np.float32) * alpha[..., None]
        + background * (1.0 - alpha[..., None])
    )
    difference = recomposite - source.astype(np.float32)
    alpha_u8 = np.clip(alpha * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return {
        "background_rgb": [round(float(value), 2) for value in background],
        "mae": round(float(np.mean(np.abs(difference))), 4),
        "rmse": round(float(np.sqrt(np.mean(difference**2))), 4),
        "alpha_zero_fraction": round(float(np.mean(alpha_u8 == 0)), 6),
        "alpha_partial_fraction": round(
            float(np.mean((alpha_u8 > 0) & (alpha_u8 < 255))), 6
        ),
        "alpha_opaque_fraction": round(float(np.mean(alpha_u8 == 255)), 6),
        "elapsed_seconds": round(elapsed, 3),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "output_bytes": output_path.stat().st_size,
    }


def save_artifacts(
    source_path: Path,
    method: str,
    foreground: np.ndarray,
    alpha: np.ndarray,
    background: np.ndarray,
    elapsed: float,
    parameters: dict[str, object],
) -> dict[str, object]:
    theme = source_path.parent.name
    scene = source_path.stem
    output_dir = EXPERIMENT / "outputs" / method / theme / scene
    output_dir.mkdir(parents=True, exist_ok=True)

    source = np.asarray(Image.open(source_path).convert("RGB"))
    transparent_path = output_dir / "transparent.png"
    alpha_path = output_dir / "alpha.png"
    recomposite_path = output_dir / "recomposite.webp"
    preview_path = output_dir / "preview.webp"

    transparent = rgba_image(foreground, alpha)
    transparent.save(transparent_path, optimize=True)
    Image.fromarray(
        np.clip(alpha * 255.0 + 0.5, 0, 255).astype(np.uint8), "L"
    ).save(alpha_path, optimize=True)

    recomposite = Image.new("RGB", transparent.size, tuple(np.rint(background).astype(int)))
    recomposite.paste(transparent, mask=transparent.getchannel("A"))
    recomposite.save(recomposite_path, "WEBP", quality=92, method=6)

    thumbs: list[Image.Image] = []
    for name, color in PREVIEW_BACKGROUNDS.items():
        canvas = Image.new("RGB", transparent.size, color)
        canvas.paste(transparent, mask=transparent.getchannel("A"))
        canvas.thumbnail((520, 360), Image.Resampling.LANCZOS)
        panel = Image.new("RGB", (540, 400), "white")
        panel.paste(canvas, ((540 - canvas.width) // 2, 30))
        ImageDraw.Draw(panel).text((12, 8), name, fill="black", font=ImageFont.load_default())
        thumbs.append(panel)
    preview = Image.new("RGB", (1080, 800), "white")
    for index, thumb in enumerate(thumbs):
        preview.paste(thumb, ((index % 2) * 540, (index // 2) * 400))
    preview.save(preview_path, "WEBP", quality=88, method=6)

    result = {
        "source": str(source_path.relative_to(ROOT)),
        "theme": theme,
        "scene": scene,
        "method": method,
        "parameters": parameters,
        "artifacts": {
            "transparent": str(transparent_path.relative_to(ROOT)),
            "alpha": str(alpha_path.relative_to(ROOT)),
            "preview": str(preview_path.relative_to(ROOT)),
            "recomposite": str(recomposite_path.relative_to(ROOT)),
        },
    }
    result["metrics"] = metrics(
        source, foreground, alpha, background, elapsed, transparent_path
    )
    return result


def run_imagemagick(source_path: Path, fuzz: int) -> tuple[np.ndarray, np.ndarray, float]:
    source = np.asarray(Image.open(source_path).convert("RGB"))
    background = estimate_background(source)
    color = "#" + "".join(f"{round(value):02x}" for value in background)
    temp_path = Path("/tmp") / f"lf-bg-{source_path.parent.name}-{source_path.stem}-{fuzz}.png"
    started = time.perf_counter()
    subprocess.run(
        [
            "magick",
            str(source_path),
            "-alpha",
            "on",
            "-fuzz",
            f"{fuzz}%",
            "-transparent",
            color,
            str(temp_path),
        ],
        check=True,
    )
    elapsed = time.perf_counter() - started
    rgba = np.asarray(Image.open(temp_path).convert("RGBA"))
    temp_path.unlink(missing_ok=True)
    return rgba[..., :3], rgba[..., 3].astype(np.float32) / 255.0, elapsed


def run_pymatting(
    rgb: np.ndarray, base_alpha: np.ndarray, max_dimension: int = 800
) -> tuple[np.ndarray, float]:
    from pymatting import estimate_alpha_knn

    height, width = base_alpha.shape
    scale = min(1.0, max_dimension / max(height, width))
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    image_small = np.asarray(
        Image.fromarray(rgb, "RGB").resize(size, Image.Resampling.LANCZOS)
    ).astype(np.float64) / 255.0
    alpha_small = np.asarray(
        Image.fromarray((base_alpha * 255).astype(np.uint8), "L").resize(
            size, Image.Resampling.BILINEAR
        )
    ).astype(np.float64) / 255.0
    trimap = np.full(alpha_small.shape, 0.5, dtype=np.float64)
    trimap[alpha_small <= 0.03] = 0.0
    trimap[alpha_small >= 0.97] = 1.0
    started = time.perf_counter()
    matte = estimate_alpha_knn(image_small, trimap)
    elapsed = time.perf_counter() - started
    matte = np.asarray(
        Image.fromarray(np.clip(matte * 255, 0, 255).astype(np.uint8), "L").resize(
            (width, height), Image.Resampling.BICUBIC
        )
    ).astype(np.float32) / 255.0
    return matte, elapsed


def run_rembg(
    source_path: Path, model: str, session: object
) -> tuple[np.ndarray, np.ndarray, float]:
    from rembg import remove

    source = Image.open(source_path).convert("RGB")
    started = time.perf_counter()
    output = remove(source, session=session, alpha_matting=False)
    elapsed = time.perf_counter() - started
    rgba = np.asarray(output.convert("RGBA"))
    return rgba[..., :3], rgba[..., 3].astype(np.float32) / 255.0, elapsed


def source_paths() -> list[Path]:
    return [FINAL / theme / f"{scene}.png" for theme in THEMES for scene in SCENES]


def run_deterministic() -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for source_path in source_paths():
        source = np.asarray(Image.open(source_path).convert("RGB"))
        background = estimate_background(source)
        for fuzz in (0, 2, 4, 6):
            foreground, alpha, elapsed = run_imagemagick(source_path, fuzz)
            method = "imagemagick-exact" if fuzz == 0 else f"imagemagick-fuzz-{fuzz}"
            results.append(
                save_artifacts(
                    source_path,
                    method,
                    foreground,
                    alpha,
                    background,
                    elapsed,
                    {"fuzz_percent": fuzz},
                )
            )
        balanced_alpha: np.ndarray | None = None
        for method, (low, high) in SOFT_THRESHOLDS.items():
            started = time.perf_counter()
            alpha = soft_alpha(source, background, low, high)
            elapsed = time.perf_counter() - started
            results.append(
                save_artifacts(
                    source_path,
                    method,
                    source,
                    alpha,
                    background,
                    elapsed,
                    {"low_rgb_distance": low, "high_rgb_distance": high},
                )
            )
            started = time.perf_counter()
            foreground = decontaminate(source, alpha, background)
            elapsed = time.perf_counter() - started
            results.append(
                save_artifacts(
                    source_path,
                    method.replace("soft-", "decontam-"),
                    foreground,
                    alpha,
                    background,
                    elapsed,
                    {
                        "low_rgb_distance": low,
                        "high_rgb_distance": high,
                        "working_space": "linear RGB",
                    },
                )
            )
            if method == "soft-balanced":
                balanced_alpha = alpha
        assert balanced_alpha is not None
        matte, elapsed = run_pymatting(source, balanced_alpha)
        foreground = decontaminate(source, matte, background)
        results.append(
            save_artifacts(
                source_path,
                "pymatting-knn-balanced",
                foreground,
                matte,
                background,
                elapsed,
                {
                    "base": "soft-balanced",
                    "algorithm": "estimate_alpha_knn",
                    "max_dimension": 800,
                    "working_space": "linear RGB",
                },
            )
        )
    return results


def run_ml(models: tuple[str, ...]) -> list[dict[str, object]]:
    from rembg import new_session

    results: list[dict[str, object]] = []
    for model in models:
        session_started = time.perf_counter()
        session = new_session(model)
        session_seconds = time.perf_counter() - session_started
        for source_path in source_paths():
            source = np.asarray(Image.open(source_path).convert("RGB"))
            background = estimate_background(source)
            foreground, alpha, elapsed = run_rembg(source_path, model, session)
            results.append(
                save_artifacts(
                    source_path,
                    f"rembg-{model}",
                    foreground,
                    alpha,
                    background,
                    elapsed,
                    {
                        "model": model,
                        "alpha_matting": False,
                        "session_initialization_seconds": round(session_seconds, 3),
                        "onnx_providers": getattr(session, "providers", None),
                    },
                )
            )
    return results


def write_manifest(results: list[dict[str, object]], append: bool) -> None:
    manifest_path = EXPERIMENT / "manifest.json"
    if append and manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        results = existing["runs"] + results
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "python": os.sys.version,
        "runs": results,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "stage", choices=("deterministic", "ml"), help="Benchmark stage to execute"
    )
    parser.add_argument(
        "--models", nargs="+", default=("u2net", "isnet-anime"), help="rembg models"
    )
    args = parser.parse_args()
    if args.stage == "deterministic":
        write_manifest(run_deterministic(), append=False)
    else:
        write_manifest(run_ml(tuple(args.models)), append=True)


if __name__ == "__main__":
    main()
