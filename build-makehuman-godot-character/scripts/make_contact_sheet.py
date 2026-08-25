#!/usr/bin/env python3
"""Create a labeled contact sheet for turnaround or texture-QA views."""

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--cell", type=int, default=512)
    args = parser.parse_args()
    files = sorted(args.input_dir.glob("*.png"))
    if not files:
        raise SystemExit(f"No PNG images in {args.input_dir}")
    columns = max(1, args.columns)
    rows = math.ceil(len(files) / columns)
    label_height = 42
    sheet = Image.new("RGB", (args.cell * columns, (args.cell + label_height) * rows), (22, 24, 28))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=22)
    except TypeError:
        font = ImageFont.load_default()
    for index, path in enumerate(files):
        image = Image.open(path).convert("RGB")
        image.thumbnail((args.cell, args.cell), Image.Resampling.LANCZOS)
        column, row = index % columns, index // columns
        x = column * args.cell + (args.cell - image.width) // 2
        y = row * (args.cell + label_height) + label_height
        sheet.paste(image, (x, y))
        label = path.stem.replace("_", " ")
        box = draw.textbbox((0, 0), label, font=font)
        draw.text((column * args.cell + (args.cell - box[2] + box[0]) / 2,
                   row * (args.cell + label_height) + 8), label, fill="white", font=font)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
