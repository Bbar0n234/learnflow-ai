#!/usr/bin/env python3
"""Вырезание фона через HF Space ZhengPeng7/BiRefNet_demo (Gradio API).

Рецепт feat-001: веса General-HR, инференс в нативных пропорциях с длинной
стороной 2048 (стороны кратны 32). Каждый исходник прогоняется через
endpoint /image; RGBA-результат сохраняется под именем исходника, все
параметры прогона фиксируются в manifest.json рядом с результатами.

Запуск: python birefnet_cutout.py <src.png ...> --out-dir <dir> [--hf-token ...]
Зависимости: gradio_client, pillow (venv вне проекта, см. README итерации).
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from gradio_client import Client, handle_file
from huggingface_hub import get_token
from PIL import Image

SPACE = "ZhengPeng7/BiRefNet_demo"
WEIGHTS = "General-HR"
LONG_SIDE = 2048


def native_resolution(width: int, height: int) -> tuple[int, int]:
    """Длинная сторона LONG_SIDE, короткая — по пропорции, кратно 32."""
    scale = LONG_SIDE / max(width, height)

    def snap32(value: float) -> int:
        return max(32, round(value / 32) * 32)

    if width >= height:
        return LONG_SIDE, snap32(height * scale)
    return snap32(width * scale), LONG_SIDE


def pick_rgba(result: object) -> Path:
    """Endpoint /image возвращает ImageSlider [оригинал, cutout] — берём RGBA."""
    paths = result if isinstance(result, (list, tuple)) else [result]
    for p in reversed([p for p in paths if p]):
        if Image.open(p).mode == "RGBA":
            return Path(p)
    raise RuntimeError(f"RGBA-результата нет в ответе Space: {paths}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sources", nargs="+", type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument(
        "--hf-token",
        default=None,
        help="HF-токен (Pro-квота ZeroGPU); по умолчанию — HF_TOKEN или ~/.cache/huggingface/token",
    )
    ap.add_argument("--retries", type=int, default=3)
    args = ap.parse_args()

    token = args.hf_token or get_token()
    print(f"HF-токен: {'есть' if token else 'нет (анонимная квота)'}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    client = Client(SPACE, token=token)

    manifest_path = args.out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []

    for src in args.sources:
        width, height = Image.open(src).size
        rw, rh = native_resolution(width, height)
        resolution = f"{rw}x{rh}"

        result = None
        for attempt in range(1, args.retries + 1):
            try:
                started = time.time()
                result = client.predict(
                    images=handle_file(str(src)),
                    resolution=resolution,
                    weights_file=WEIGHTS,
                    api_name="/image",
                )
                elapsed = time.time() - started
                break
            except Exception as exc:  # noqa: BLE001 — ретраим любой сбой Space/сети
                print(f"[{src.name}] попытка {attempt}: {exc}", file=sys.stderr)
                if attempt == args.retries:
                    raise
                time.sleep(30 * attempt)

        dest = args.out_dir / src.name
        shutil.copy(pick_rgba(result), dest)
        manifest.append(
            {
                "source": str(src),
                "output": str(dest),
                "source_size": [width, height],
                "inference_resolution": resolution,
                "weights": WEIGHTS,
                "space": SPACE,
                "seconds": round(elapsed, 1),
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
        )
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        print(f"[{src.name}] ok: {resolution} -> {dest} ({elapsed:.1f}s)")


if __name__ == "__main__":
    main()
