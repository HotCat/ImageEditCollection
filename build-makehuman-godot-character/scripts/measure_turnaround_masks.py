#!/usr/bin/env python3
"""Measure normalized silhouette scanlines from Vision person masks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mask", action="append", type=Path, required=True,
                        help="Mask PNG; repeat for each accepted view")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.25)
    return parser.parse_args()


def central_run(row: np.ndarray, center: int):
    indices = np.flatnonzero(row)
    if not len(indices):
        return None
    runs = np.split(indices, np.where(np.diff(indices) > 1)[0] + 1)
    containing = [run for run in runs if run[0] <= center <= run[-1]]
    run = containing[0] if containing else min(
        runs, key=lambda item: min(abs(int(item[0]) - center), abs(int(item[-1]) - center))
    )
    return int(run[0]), int(run[-1])


def measure(path: Path, threshold: float) -> dict:
    image = np.asarray(Image.open(path).convert("L"), dtype=np.float32) / 255.0
    binary = image > threshold
    ys, xs = np.nonzero(binary)
    if not len(xs):
        raise ValueError(f"No foreground pixels in {path}")
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    height = y1 - y0 + 1
    center = int(round(np.median(xs)))
    scanlines = {}
    for fraction in np.linspace(0.05, 0.95, 19):
        y = min(y1, max(y0, int(round(y0 + float(fraction) * (height - 1)))))
        run = central_run(binary[y], center)
        scanlines[f"{fraction:.2f}"] = None if run is None else {
            "y": y, "left": run[0], "right": run[1],
            "width_px": run[1] - run[0] + 1,
            "width_over_height": (run[1] - run[0] + 1) / height,
        }
    return {
        "source": str(path.resolve()),
        "image_size": [int(image.shape[1]), int(image.shape[0])],
        "bbox": {"x0": x0, "x1": x1, "y0": y0, "y1": y1,
                 "width": x1 - x0 + 1, "height": height},
        "center_x": center, "scanlines": scanlines,
    }


def main():
    args = parse_args()
    result = {path.stem: measure(path, args.threshold) for path in args.mask}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
