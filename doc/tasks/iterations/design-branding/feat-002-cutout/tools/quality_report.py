#!/usr/bin/env python3
"""Автопроверка качества cutout + артефакты ревью (метрики, контактлисты).

Vision на полном кадре ненадёжен, поэтому проверка скриптовая, по слоям:

1. Псевдо-ground-truth по цвету фона. Стиль пака — плоские заливки на
   однотонном кремовом фоне; фон оценивается по рамке исходника. Тогда:
   - background leak: доля пикселей настоящего фона (кремовые области,
     связанные с границей кадра), оставшихся непрозрачными;
   - object eaten: доля пикселей объекта (цвет далёк от фона), ставших
     прозрачными.
2. Санити-метрики диапазонов: доли alpha zero/partial/full, кремовый halo
   в полупрозрачной кайме (средняя близость RGB каймы к цвету фона).
3. Флаги на большие полупрозрачные области внутри объекта — ловят
   недетерминизм BiRefNet на «объектах цвета фона» (лист бумаги и т.п.).
   Флаг не означает брак — это адрес зоны для точечного ревью.
4. Контактлисты: полный кадр на 4 фонах + edge-кропы с зумом вокруг самых
   насыщенных участков полупрозрачной каймы — единственное место, где
   подключается vision, уже на осмысленном масштабе.

Запуск: python quality_report.py --pairs src1:cut1 [src2:cut2 ...] --out-dir <dir>
Зависимости: pillow, numpy, scipy.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

BACKGROUNDS = {
    "white": (255, 255, 255),
    "cream": (250, 247, 241),
    "black": (0, 0, 0),
    "ui-dark": (24, 20, 32),
}
BG_TOLERANCE = 26  # RGB-дистанция: «это цвет фона»
OBJ_TOLERANCE = 52  # RGB-дистанция: «это точно объект»
PARTIAL_LO, PARTIAL_HI = 24, 232
SUSPICIOUS_BLOB_PX = 2500


def rgb_distance(arr: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    return np.sqrt(((arr.astype(np.float32) - np.array(color)) ** 2).sum(axis=-1))


def estimate_background(src: np.ndarray) -> tuple[int, int, int]:
    frame = np.concatenate(
        [src[:10].reshape(-1, 3), src[-10:].reshape(-1, 3),
         src[:, :10].reshape(-1, 3), src[:, -10:].reshape(-1, 3)]
    )
    return tuple(int(v) for v in np.median(frame, axis=0))


def composite(cut: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    base = Image.new("RGB", cut.size, color)
    base.paste(cut, mask=cut.split()[3])
    return base


def analyze(src_path: Path, cut_path: Path, out_dir: Path) -> dict:
    src = np.asarray(Image.open(src_path).convert("RGB"))
    cut_img = Image.open(cut_path)
    cut = np.asarray(cut_img)
    alpha = cut[..., 3]

    bg = estimate_background(src)
    dist = rgb_distance(src, bg)

    # настоящий фон: кремовые области, связанные с границей кадра
    bg_like = dist <= BG_TOLERANCE
    labels, _ = ndimage.label(bg_like)
    border_labels = np.unique(
        np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])
    )
    true_bg = np.isin(labels, border_labels[border_labels != 0])
    obj = dist >= OBJ_TOLERANCE

    partial = (alpha >= PARTIAL_LO) & (alpha <= PARTIAL_HI)
    halo = float(np.mean(rgb_distance(cut[..., :3][partial], bg))) if partial.any() else None

    # большие полупрозрачные области вне настоящего фона — кандидаты на «съеденный» объект
    inner_partial = partial & ~true_bg
    blob_labels, n_blobs = ndimage.label(inner_partial)
    blobs = []
    for i in range(1, n_blobs + 1):
        area = int((blob_labels == i).sum())
        if area >= SUSPICIOUS_BLOB_PX:
            ys, xs = np.where(blob_labels == i)
            blobs.append(
                {
                    "area_px": area,
                    "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
                    "mean_alpha": round(float(alpha[blob_labels == i].mean()), 1),
                }
            )
    blobs.sort(key=lambda b: -b["area_px"])

    metrics = {
        "image": src_path.stem,
        "theme": src_path.parent.name,
        "estimated_bg": bg,
        "alpha_zero": round(float(np.mean(alpha == 0)), 4),
        "alpha_partial": round(float(np.mean((alpha > 0) & (alpha < 255))), 4),
        "alpha_full": round(float(np.mean(alpha == 255)), 4),
        "bg_leak": round(float(np.mean(alpha[true_bg] > 128)), 5) if true_bg.any() else None,
        "object_eaten": round(float(np.mean(alpha[obj] < 128)), 5) if obj.any() else None,
        "halo_bg_similarity": round(halo, 1) if halo is not None else None,
        "suspicious_blobs": blobs[:8],
    }

    # контактлист: полный кадр на 4 фонах (2x2) + исходник
    thumbs = [Image.open(src_path).convert("RGB")] + [
        composite(cut_img, c) for c in BACKGROUNDS.values()
    ]
    tw = 560
    thumbs = [t.resize((tw, round(t.height * tw / t.width)), Image.LANCZOS) for t in thumbs]
    th = thumbs[0].height
    sheet = Image.new("RGB", (tw * len(thumbs) + 8 * (len(thumbs) - 1), th), (110, 110, 110))
    for i, t in enumerate(thumbs):
        sheet.paste(t, (i * (tw + 8), 0))
    sheet.save(out_dir / f"{src_path.parent.name}-{src_path.stem}__composites.jpg", quality=90)

    # edge-кропы: топ-участки полупрозрачной каймы, зум 3x, на 4 фонах
    density = ndimage.uniform_filter(partial.astype(np.float32), size=120)
    crops, taken = [], []
    flat = density.copy()
    crop_size = 150
    for _ in range(4):
        y, x = np.unravel_index(np.argmax(flat), flat.shape)
        if flat[y, x] <= 0:
            break
        taken.append((int(x), int(y)))
        y0, x0 = max(0, y - crop_size), max(0, x - crop_size)
        flat[max(0, y - 260):y + 260, max(0, x - 260):x + 260] = 0
        box = (x0, y0, min(cut.shape[1], x0 + 2 * crop_size), min(cut.shape[0], y0 + 2 * crop_size))
        row = [composite(cut_img, c).crop(box) for c in BACKGROUNDS.values()]
        crops.append([r.resize((r.width * 3, r.height * 3), Image.NEAREST) for r in row])
    if crops:
        cw, ch = crops[0][0].size
        grid = Image.new("RGB", (cw * 4 + 24, (ch + 8) * len(crops)), (110, 110, 110))
        for r, row in enumerate(crops):
            for c, img in enumerate(row):
                grid.paste(img, (c * (cw + 8), r * (ch + 8)))
        grid.save(out_dir / f"{src_path.parent.name}-{src_path.stem}__edges.jpg", quality=90)
    metrics["edge_crop_centers"] = taken

    return metrics


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairs", nargs="+", required=True, help="src.png:cutout.png")
    ap.add_argument("--out-dir", required=True, type=Path)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    report = []
    for pair in args.pairs:
        src, cut = pair.split(":")
        m = analyze(Path(src), Path(cut), args.out_dir)
        report.append(m)
        flags = f" blobs={len(m['suspicious_blobs'])}" if m["suspicious_blobs"] else ""
        print(
            f"[{m['theme']}/{m['image']}] leak={m['bg_leak']} eaten={m['object_eaten']} "
            f"halo≈{m['halo_bg_similarity']} partial={m['alpha_partial']}{flags}"
        )
    (args.out_dir / "quality-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
