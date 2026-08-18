#!/usr/bin/env python3
"""Generate and visualize SAM2 candidates from explicit identity prompts."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image, ImageDraw

from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor


def point(value: str) -> tuple[float, float]:
    try:
        x, y = value.split(",")
        return float(x), float(y)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Expected x,y") from error


def box(value: str) -> tuple[float, float, float, float]:
    try:
        x0, y0, x1, y1 = value.split(",")
        result = float(x0), float(y0), float(x1), float(y1)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Expected x0,y0,x1,y1") from error
    if result[0] >= result[2] or result[1] >= result[3]:
        raise argparse.ArgumentTypeError("Box must have x0<x1 and y0<y1")
    return result


def rgb(value: str) -> tuple[int, int, int]:
    try:
        values = tuple(int(item) for item in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Expected r,g,b") from error
    if len(values) != 3 or any(item < 0 or item > 255 for item in values):
        raise argparse.ArgumentTypeError("RGB channels must be integers from 0 to 255")
    return values


def overlay(source: np.ndarray, mask: np.ndarray, color: tuple[int, int, int]) -> Image.Image:
    result = source.astype(np.float32).copy()
    tint = np.zeros_like(result)
    tint[:] = color
    result[mask] = result[mask] * 0.30 + tint[mask] * 0.70
    edge = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    result[edge] = color
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8), mode="RGB")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--name", default="subject")
    parser.add_argument("--positive", type=point, action="append", required=True)
    parser.add_argument("--negative", type=point, action="append", default=[])
    parser.add_argument("--box", type=box)
    parser.add_argument("--color", type=rgb, default=(0, 0, 255))
    parser.add_argument("--select", choices=("auto", "0", "1", "2"), default="auto")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda", "mps"), default="auto")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source = np.asarray(Image.open(args.image).convert("RGB")).copy()

    if args.device == "auto":
        if torch.cuda.is_available():
            device = torch.device("cuda")
        elif torch.backends.mps.is_available():
            device = torch.device("mps")
        else:
            device = torch.device("cpu")
    else:
        device = torch.device(args.device)

    model = build_sam2(args.config, args.checkpoint, device=device)
    predictor = SAM2ImagePredictor(model)
    predictor.set_image(source)

    points = np.asarray([*args.positive, *args.negative], dtype=np.float32)
    labels = np.asarray([1] * len(args.positive) + [0] * len(args.negative), dtype=np.int32)
    prompt_box = np.asarray(args.box, dtype=np.float32) if args.box else None
    masks, scores, _ = predictor.predict(
        point_coords=points,
        point_labels=labels,
        box=prompt_box,
        multimask_output=True,
    )
    masks = masks > 0.0

    tiles: list[Image.Image] = []
    width, height = source.shape[1], source.shape[0]
    preview_width = min(width, 640)
    preview_height = round(height * preview_width / width)
    for index, (mask, score) in enumerate(zip(masks, scores)):
        mask_path = output_dir / f"{args.name}_candidate_{index}.png"
        Image.fromarray(mask.astype(np.uint8) * 255, mode="L").save(mask_path)
        preview = overlay(source, mask, args.color).resize(
            (preview_width, preview_height), Image.Resampling.LANCZOS
        )
        tile = Image.new("RGB", (preview_width, preview_height + 34), "black")
        tile.paste(preview, (0, 34))
        ImageDraw.Draw(tile).text(
            (8, 8), f"candidate {index} score={float(score):.3f}", fill="white"
        )
        tiles.append(tile)

    sheet = Image.new("RGB", (preview_width * 3, preview_height + 34), (24, 24, 24))
    for index, tile in enumerate(tiles):
        sheet.paste(tile, (index * preview_width, 0))
    sheet_path = output_dir / f"{args.name}_candidates.png"
    sheet.save(sheet_path)

    selected = int(np.argmax(scores)) if args.select == "auto" else int(args.select)
    selected_path = output_dir / f"{args.name}_selected.png"
    Image.fromarray(masks[selected].astype(np.uint8) * 255, mode="L").save(selected_path)

    print(f"device={device}")
    print("scores=" + ",".join(f"{float(score):.4f}" for score in scores))
    print(f"selected={selected}")
    print(sheet_path)
    print(selected_path)


if __name__ == "__main__":
    main()
