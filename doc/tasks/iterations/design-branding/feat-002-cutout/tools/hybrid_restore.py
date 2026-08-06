#!/usr/bin/env python3
"""Гибридная альфа: край и дырки — от BiRefNet, целостность внутренностей — от
детерминированной маски фона (логика feat-001).

Дефекты BiRefNet на нашем паке сидят в больших полупрозрачных зонах внутри
объекта: «объект цвета фона» (лист бумаги) и «тень-подложка» (сиреневые
эллипсы). Настоящий фон при этом известен точно — это кремовые области,
связанные с границей кадра. Поэтому:

1. Находим флагованные кляксы: большие связные области частичной альфы вне
   настоящего фона (тот же детектор, что в quality_report.py).
2. Расширяем каждую кляксу на связанные с ней не полностью непрозрачные
   пиксели вне настоящего фона — так подхватываются насквозь вырезанные части
   (alpha≈0): куски подложек и «объектов цвета фона», не попавшие в
   partial-диапазон. Расширение считается в локальном окне вокруг кляксы,
   чтобы не расползаться по тонкой AA-кайме силуэта на честные внутренние
   дырки в других частях кадра.
3. Восстанавливаем альфу в зоне до 255 через max() с размытой маской: шов
   к уже непрозрачным пикселям невидим, край зоны к прозрачности получает
   мягкую кайму; наружу в настоящий фон кайма не растёт.

RGB результата берётся из исходника (BiRefNet не меняет цвета, но исходник —
канонический источник).

Запуск: python hybrid_restore.py --pairs src.png:birefnet.png ... --out-dir <dir>
Зависимости: pillow, numpy, scipy.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

BG_TOLERANCE = 26
PARTIAL_LO, PARTIAL_HI = 24, 232
SUSPICIOUS_BLOB_PX = 2500
FEATHER_SIGMA = 1.2


def rgb_distance(arr: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    return np.sqrt(((arr.astype(np.float32) - np.array(color)) ** 2).sum(axis=-1))


def estimate_background(src: np.ndarray) -> tuple[int, int, int]:
    frame = np.concatenate(
        [src[:10].reshape(-1, 3), src[-10:].reshape(-1, 3),
         src[:, :10].reshape(-1, 3), src[:, -10:].reshape(-1, 3)]
    )
    return tuple(int(v) for v in np.median(frame, axis=0))


def true_background(src: np.ndarray, bg: tuple[int, int, int]) -> np.ndarray:
    bg_like = rgb_distance(src, bg) <= BG_TOLERANCE
    labels, _ = ndimage.label(bg_like)
    border = np.unique(
        np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])
    )
    return np.isin(labels, border[border != 0])


WINDOW_PAD = 32


def restore_region(src: np.ndarray, alpha: np.ndarray, bg: tuple[int, int, int]) -> np.ndarray:
    """Маска пикселей, подлежащих восстановлению до непрозрачности."""
    true_bg = true_background(src, bg)

    partial = (alpha >= PARTIAL_LO) & (alpha <= PARTIAL_HI) & ~true_bg
    blob_labels, n = ndimage.label(partial)
    region = np.zeros_like(partial)
    suspect = ~true_bg & (alpha < 240)
    for i in range(1, n + 1):
        component = blob_labels == i
        if component.sum() < SUSPICIOUS_BLOB_PX:
            continue
        ys, xs = np.where(component)
        y0 = max(0, ys.min() - WINDOW_PAD)
        y1 = min(component.shape[0], ys.max() + WINDOW_PAD + 1)
        x0 = max(0, xs.min() - WINDOW_PAD)
        x1 = min(component.shape[1], xs.max() + WINDOW_PAD + 1)
        window = suspect[y0:y1, x0:x1] | component[y0:y1, x0:x1]
        ext_labels, _ = ndimage.label(window)
        touched = np.unique(ext_labels[component[y0:y1, x0:x1]])
        region[y0:y1, x0:x1] |= np.isin(ext_labels, touched[touched != 0])
    return region


def hybrid(src_path: Path, cut_path: Path, out_path: Path) -> dict:
    src_img = Image.open(src_path).convert("RGB")
    src = np.asarray(src_img)
    alpha = np.asarray(Image.open(cut_path))[..., 3].astype(np.float32)

    bg = estimate_background(src)
    region = restore_region(src, alpha.astype(np.uint8), bg)

    restored_px = 0
    if region.any():
        soft = ndimage.gaussian_filter(region.astype(np.float32), FEATHER_SIGMA)
        soft[true_background(src, bg)] = 0.0  # кайма не растёт в настоящий фон
        new_alpha = np.maximum(alpha, soft * 255.0)
        restored_px = int(((new_alpha - alpha) > 8).sum())
        alpha = new_alpha

    out = np.dstack([src, np.clip(alpha, 0, 255).astype(np.uint8)])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out, "RGBA").save(out_path)
    return {
        "source": str(src_path),
        "birefnet": str(cut_path),
        "output": str(out_path),
        "restored_pixels": restored_px,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairs", nargs="+", required=True, help="src.png:birefnet.png")
    ap.add_argument("--out-dir", required=True, type=Path)
    args = ap.parse_args()

    manifest = []
    for pair in args.pairs:
        src, cut = pair.split(":")
        src_path = Path(src)
        out = args.out_dir / src_path.parent.name / src_path.name
        entry = hybrid(src_path, Path(cut), out)
        manifest.append(entry)
        print(f"[{src_path.parent.name}/{src_path.name}] restored {entry['restored_pixels']} px -> {out}")
    (args.out_dir / "manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
