#!/usr/bin/env python3
"""Ingest raw generated Kira art (chroma-green sheets or singles) into staged crops.

Usage:
  scripts/ingest.py --grid 3x2 RAW.png [RAW2.png ...] [--out incoming] [--max-size 640]

--grid COLSxROWS is the raw sheet's panel layout (1x1 for a single pose).
Each cell is trimmed to its content, chroma-keyed to RGBA with a soft matte
and green despill, downscaled to --max-size and quantized to PNG8 (255
colors, no dither). Cells that are mostly NOT green (framed scene art) are
kept as opaque editorial crops instead of being keyed. White panel-frame
gutters are ignored as background.

Output: <out>/<stem>-pN.png in row-major panel order, plus a report line per
panel: name, size, kind (keyed|editorial). Review visually and rename
semantically before moving files into the repo root.
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image


def green_mask(rgb: np.ndarray) -> np.ndarray:
    r = rgb[..., 0].astype(np.int16)
    g = rgb[..., 1].astype(np.int16)
    b = rgb[..., 2].astype(np.int16)
    return (g > 90) & (g - np.maximum(r, b) > 40)


def white_mask(rgb: np.ndarray) -> np.ndarray:
    return np.all(rgb > 232, axis=-1)


def key_crop(rgb: np.ndarray) -> Image.Image:
    r = rgb[..., 0].astype(np.int16)
    g = rgb[..., 1].astype(np.int16)
    b = rgb[..., 2].astype(np.int16)
    greenness = g - np.maximum(r, b)
    # soft matte: opaque below 12 greenness, transparent above 70
    alpha = np.clip((70 - greenness) * (255 / 58), 0, 255).astype(np.uint8)
    alpha[g <= 90] = 255  # dark/neutral pixels are never chroma background
    # despill: cap green at max(r,b) wherever it dominates
    spill = greenness > 0
    g2 = rgb[..., 1].copy()
    g2[spill] = np.maximum(r, b)[spill].astype(np.uint8)
    return Image.fromarray(np.dstack([rgb[..., 0], g2, rgb[..., 2], alpha]), "RGBA")


def drop_edge_debris(im: Image.Image) -> Image.Image:
    """Remove small alpha components touching the crop border: white panel-frame
    remnants and slivers of neighbor panels that crossed the sheet gutter."""
    a = np.asarray(im.getchannel("A")) > 0
    h, w = a.shape
    seen = np.zeros_like(a)
    comps = []
    for sy in range(h):
        for sx in range(w):
            if not a[sy, sx] or seen[sy, sx]:
                continue
            from collections import deque
            q = deque([(sy, sx)])
            seen[sy, sx] = True
            px = []
            touches = False
            while q:
                cy, cx = q.popleft()
                px.append((cy, cx))
                if cy in (0, h - 1) or cx in (0, w - 1):
                    touches = True
                for ny, nx in ((cy-1, cx), (cy+1, cx), (cy, cx-1), (cy, cx+1)):
                    if 0 <= ny < h and 0 <= nx < w and a[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
            comps.append((len(px), touches, px))
    if not comps:
        return im
    main = max(c[0] for c in comps)
    arr = np.asarray(im).copy()
    for area, touches, px in comps:
        if touches and area < main * 0.10:
            for cy, cx in px:
                arr[cy, cx, 3] = 0
    return Image.fromarray(arr, "RGBA")


def finalize(im: Image.Image, max_size: int) -> Image.Image:
    if im.mode == "RGBA":
        im = drop_edge_debris(im)
    if im.mode == "RGBA":
        bbox = im.getchannel("A").getbbox()
        if bbox:
            im = im.crop(bbox)
    if max(im.size) > max_size:
        im.thumbnail((max_size, max_size), Image.BOX)
    return im.quantize(colors=255, method=Image.FASTOCTREE, dither=Image.Dither.NONE)


def content_bbox(mask: np.ndarray, min_frac=0.002):
    """Bounding box over mask rows/cols with enough content to skip specks."""
    if not mask.any():
        return None
    rows = mask.sum(axis=1)
    cols = mask.sum(axis=0)
    rt = max(2, int(mask.shape[1] * min_frac))
    ct = max(2, int(mask.shape[0] * min_frac))
    ys = np.where(rows > rt)[0]
    xs = np.where(cols > ct)[0]
    if len(ys) == 0 or len(xs) == 0:
        return None
    return xs[0], ys[0], xs[-1] + 1, ys[-1] + 1


def process_cell(cell: np.ndarray, max_size: int):
    gm = green_mask(cell)
    if gm.mean() < 0.15:
        # framed scene panel: trim the white gutter frame, keep opaque
        box = content_bbox(~white_mask(cell))
        if box is None:
            return None, "empty"
        x0, y0, x1, y1 = box
        im = Image.fromarray(cell[y0 + 2:y1 - 2, x0 + 2:x1 - 2], "RGB")
        return finalize(im, max_size), "editorial"
    fg = ~gm & ~white_mask(cell)
    box = content_bbox(fg)
    if box is None:
        return None, "empty"
    x0, y0, x1, y1 = box
    pad = 4
    x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
    x1 = min(cell.shape[1], x1 + pad); y1 = min(cell.shape[0], y1 + pad)
    return finalize(key_crop(cell[y0:y1, x0:x1]), max_size), "keyed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--grid", default="1x1", help="COLSxROWS panel layout")
    ap.add_argument("--out", type=Path, default=Path("incoming"))
    ap.add_argument("--max-size", type=int, default=640)
    args = ap.parse_args()
    cols, rows = (int(v) for v in args.grid.lower().split("x"))
    args.out.mkdir(parents=True, exist_ok=True)

    for path in args.inputs:
        rgb = np.asarray(Image.open(path).convert("RGB"))
        h, w = rgb.shape[:2]
        n = 0
        for ry in range(rows):
            for rx in range(cols):
                # inset past the panel-frame gutter lines that sit on cell edges
                iy = max(4, (h // rows) * 15 // 1000)
                ix = max(4, (w // cols) * 15 // 1000)
                cell = rgb[ry * h // rows + iy:(ry + 1) * h // rows - iy,
                           rx * w // cols + ix:(rx + 1) * w // cols - ix]
                im, kind = process_cell(cell, args.max_size)
                n += 1
                if im is None:
                    print(f"{path.stem}-p{n}: skipped ({kind})")
                    continue
                name = f"{path.stem}-p{n}.png"
                im.save(args.out / name, optimize=True)
                print(f"{name}  {im.size[0]}x{im.size[1]}  {kind}")


if __name__ == "__main__":
    main()
