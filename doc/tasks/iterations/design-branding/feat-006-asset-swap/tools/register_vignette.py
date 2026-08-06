"""Регистрация светлой sidebar-vignette под тёмную.

Светлый и тёмный арты сцены нарисованы в разном масштабе (одна композиция,
тёмная — перекраска). Скрипт подбирает масштаб и смещение светлого контента,
максимизируя IoU альфа-масок с тёмным артом, и пересобирает
frontend/src/shared/assets/illustrations/light/sidebar-vignette.png одним
ресемплингом LANCZOS от канонического пака feat-002.

Запуск из корня репозитория (нужны pillow, numpy, scipy):

    python doc/tasks/iterations/design-branding/feat-006-asset-swap/tools/register_vignette.py
"""

from pathlib import Path

import numpy as np
from PIL import Image
from scipy.signal import fftconvolve

REPO = Path(__file__).resolve().parents[5]
PACK_LIGHT = REPO / (
    "doc/tasks/iterations/design-branding/feat-002-cutout/cutouts/light/sidebar-vignette.png"
)
FE_ILLUSTRATIONS = REPO / "frontend/src/shared/assets/illustrations"
ALPHA_THRESHOLD = 8
DOWNSCALE = 4
SCALE_RANGE = np.arange(1.04, 1.145, 0.005)


def alpha_mask(img: Image.Image) -> np.ndarray:
    return np.asarray(img)[:, :, 3] > ALPHA_THRESHOLD


def content_bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(mask)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def main() -> None:
    pack_light = Image.open(PACK_LIGHT).convert("RGBA")
    dark = Image.open(FE_ILLUSTRATIONS / "dark/sidebar-vignette.png").convert("RGBA")

    x0, y0, x1, y1 = content_bbox(alpha_mask(pack_light))
    content = pack_light.crop((x0, y0, x1, y1))
    cw, ch = content.size

    dark_full = alpha_mask(dark).astype(np.float32)
    small_size = (dark_full.shape[1] // DOWNSCALE, dark_full.shape[0] // DOWNSCALE)
    dark_small = (
        np.asarray(
            Image.fromarray((dark_full * 255).astype(np.uint8)).resize(
                small_size, Image.BILINEAR
            ),
            np.float32,
        )
        / 255
    )
    dark_area = dark_small.sum()

    best: tuple[float, float, int, int] | None = None
    for scale in SCALE_RANGE:
        w, h = round(cw * scale / DOWNSCALE), round(ch * scale / DOWNSCALE)
        if h > dark_small.shape[0] or w > dark_small.shape[1]:
            continue
        light_small = (
            np.asarray(content.split()[3].resize((w, h), Image.BILINEAR), np.float32)
            / 255
        )
        inter = fftconvolve(dark_small, light_small[::-1, ::-1], mode="valid")
        iy, ix = np.unravel_index(np.argmax(inter), inter.shape)
        iou = inter[iy, ix] / (dark_area + light_small.sum() - inter[iy, ix])
        if best is None or iou > best[0]:
            best = (iou, scale, ix * DOWNSCALE, iy * DOWNSCALE)

    assert best is not None
    iou, scale, px, py = best
    resized = content.resize((round(cw * scale), round(ch * scale)), Image.LANCZOS)
    canvas = Image.new("RGBA", pack_light.size, (0, 0, 0, 0))
    canvas.paste(resized, (px, py), resized)
    out = FE_ILLUSTRATIONS / "light/sidebar-vignette.png"
    canvas.save(out)
    print(f"scale={scale:.3f} offset=({px},{py}) IoU={iou:.4f} -> {out}")


if __name__ == "__main__":
    main()
