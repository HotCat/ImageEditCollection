#!/usr/bin/env python3
"""Compose mutually exclusive visible-surface masks for two touching people."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def box(value: str) -> tuple[int, int, int, int]:
    try:
        x0, y0, x1, y1 = (int(item) for item in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Expected x0,y0,x1,y1") from error
    if x0 >= x1 or y0 >= y1:
        raise argparse.ArgumentTypeError("Box must have x0<x1 and y0<y1")
    return x0, y0, x1, y1


def color(value: str) -> tuple[int, int, int]:
    if value.startswith("#") and len(value) == 7:
        try:
            return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))
        except ValueError as error:
            raise argparse.ArgumentTypeError("Expected #RRGGBB") from error
    raise argparse.ArgumentTypeError("Expected #RRGGBB")


def clean_components(mask: np.ndarray, minimum_area: int) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    output = np.zeros_like(mask, dtype=bool)
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] >= minimum_area:
            output |= labels == label
    return output


def fill_small_holes(mask: np.ndarray, maximum_area: int) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats((~mask).astype(np.uint8), 8)
    output = mask.copy()
    height, width = mask.shape
    for label in range(1, count):
        x, y, w, h, area = stats[label]
        touches_frame = x == 0 or y == 0 or x + w == width or y + h == height
        if not touches_frame and area <= maximum_area:
            output[labels == label] = True
    return output


def save_color(mask: np.ndarray, rgb: tuple[int, int, int], path: Path) -> None:
    image = np.zeros((*mask.shape, 3), dtype=np.uint8)
    image[mask] = rgb
    Image.fromarray(image, mode="RGB").save(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--union-mask", required=True)
    parser.add_argument("--b-mask", required=True, help="Reliable raw mask for subject B")
    parser.add_argument("--a-foreground-mask", help="Optional subject-A mask used only at the contact")
    parser.add_argument("--a-foreground-box", type=box, help="Restrict the A override to x0,y0,x1,y1")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--a-name", default="subject_a")
    parser.add_argument("--b-name", default="subject_b")
    parser.add_argument("--a-color", type=color, default=(255, 0, 0))
    parser.add_argument("--b-color", type=color, default=(0, 0, 255))
    parser.add_argument("--union-threshold", type=int, default=112)
    parser.add_argument("--minimum-component-area", type=int, default=30)
    parser.add_argument("--maximum-hole-area", type=int, default=180)
    parser.add_argument("--foreground-dilate", type=int, default=1)
    parser.add_argument("--absorb-b-edge", type=int, choices=(0, 1, 2), default=0)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source = np.asarray(Image.open(args.image).convert("RGB"))
    union_gray = np.asarray(Image.open(args.union_mask).convert("L"))
    b_raw = np.asarray(Image.open(args.b_mask).convert("L")) >= 128
    if union_gray.shape != source.shape[:2] or b_raw.shape != source.shape[:2]:
        raise ValueError("Source, union mask, and B mask must have identical dimensions")

    union = union_gray >= args.union_threshold
    a_foreground = np.zeros_like(union)
    if args.a_foreground_mask:
        a_foreground = np.asarray(Image.open(args.a_foreground_mask).convert("L")) >= 128
        if a_foreground.shape != union.shape:
            raise ValueError("A foreground mask dimensions do not match the source")
        if args.foreground_dilate:
            kernel = np.ones((3, 3), np.uint8)
            a_foreground = cv2.dilate(
                a_foreground.astype(np.uint8), kernel, iterations=args.foreground_dilate
            ) > 0
        if args.a_foreground_box:
            x0, y0, x1, y1 = args.a_foreground_box
            region = np.zeros_like(union)
            region[max(0, y0) : min(union.shape[0], y1), max(0, x0) : min(union.shape[1], x1)] = True
            a_foreground &= region

    b = b_raw & union & ~a_foreground
    b = clean_components(b, args.minimum_component_area)
    b = cv2.morphologyEx(b.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8)) > 0
    b = fill_small_holes(b & union & ~a_foreground, args.maximum_hole_area)
    if args.absorb_b_edge:
        b = cv2.dilate(
            b.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=args.absorb_b_edge
        ) > 0
        b &= union & ~a_foreground
    a = union & ~b

    a_binary = output_dir / f"{args.a_name}_binary_mask.png"
    b_binary = output_dir / f"{args.b_name}_binary_mask.png"
    a_color_path = output_dir / f"{args.a_name}_color_silhouette.png"
    b_color_path = output_dir / f"{args.b_name}_color_silhouette.png"
    combined_path = output_dir / "red_blue_separation.png"
    overlay_path = output_dir / "separation_overlay.png"

    Image.fromarray(a.astype(np.uint8) * 255, mode="L").save(a_binary)
    Image.fromarray(b.astype(np.uint8) * 255, mode="L").save(b_binary)
    save_color(a, args.a_color, a_color_path)
    save_color(b, args.b_color, b_color_path)

    combined = np.zeros_like(source)
    combined[a] = args.a_color
    combined[b] = args.b_color
    Image.fromarray(combined, mode="RGB").save(combined_path)

    overlay = (source.astype(np.float32) * 0.38).astype(np.uint8)
    overlay[a] = (source[a] * 0.25 + np.asarray(args.a_color) * 0.75).astype(np.uint8)
    overlay[b] = (source[b] * 0.25 + np.asarray(args.b_color) * 0.75).astype(np.uint8)
    Image.fromarray(overlay, mode="RGB").save(overlay_path)

    colors = np.unique(combined.reshape(-1, 3), axis=0)
    allowed = {tuple((0, 0, 0)), tuple(args.a_color), tuple(args.b_color)}
    if any(tuple(item) not in allowed for item in colors):
        raise RuntimeError("Combined output contains unexpected colors")
    if np.any(a & b):
        raise RuntimeError("Output masks overlap")

    print(f"dimensions={source.shape[1]}x{source.shape[0]}")
    print(f"{args.a_name}_pixels={int(a.sum())}")
    print(f"{args.b_name}_pixels={int(b.sum())}")
    print("overlap_pixels=0")
    for path in (a_binary, b_binary, a_color_path, b_color_path, combined_path, overlay_path):
        print(path)


if __name__ == "__main__":
    main()
