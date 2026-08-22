#!/usr/bin/env python3
"""Create a labeled contact sheet from azimuth PNG renders."""

import argparse
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--cell", type=int, default=512)
    return parser.parse_args()


def angle(path):
    match = re.search(r"azimuth_(\d+)", path.stem)
    return int(match.group(1)) if match else 0


def main():
    args = parse_args()
    files = sorted(args.input_dir.glob("*azimuth_*.png"), key=angle)
    if not files:
        raise SystemExit(f"No azimuth PNGs found in {args.input_dir}")
    columns = max(1, args.columns)
    rows = (len(files) + columns - 1) // columns
    label_height = 44
    sheet = Image.new(
        "RGB",
        (args.cell * columns, (args.cell + label_height) * rows),
        (20, 22, 28),
    )
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=24)
    except TypeError:
        font = ImageFont.load_default()

    for index, path in enumerate(files):
        image = Image.open(path).convert("RGB")
        image.thumbnail((args.cell, args.cell), Image.Resampling.LANCZOS)
        column, row = index % columns, index // columns
        x = column * args.cell + (args.cell - image.width) // 2
        y = row * (args.cell + label_height) + label_height
        sheet.paste(image, (x, y))
        label = f"Azimuth {angle(path):03d}°"
        box = draw.textbbox((0, 0), label, font=font)
        width = box[2] - box[0]
        draw.text(
            (
                column * args.cell + (args.cell - width) / 2,
                row * (args.cell + label_height) + 9,
            ),
            label,
            fill="white",
            font=font,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
