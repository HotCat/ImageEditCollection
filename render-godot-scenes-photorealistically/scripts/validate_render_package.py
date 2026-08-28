#!/usr/bin/env python3
"""Record native render dimensions and delivery-size limitations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required: python -m pip install Pillow")


def parse_ratio(value: str) -> float:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[:/]\s*(\d+(?:\.\d+)?)\s*", value)
    if not match or float(match.group(2)) == 0:
        raise argparse.ArgumentTypeError("expected a ratio such as 16:9")
    return float(match.group(1)) / float(match.group(2))


def parse_size(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*[xX]\s*(\d+)\s*", value)
    if not match:
        raise argparse.ArgumentTypeError("expected WIDTHxHEIGHT")
    return int(match.group(1)), int(match.group(2))


def inspect_image(path: Path) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(f"missing or empty image: {path}")
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        width, height = image.size
        image_format = image.format or path.suffix.lstrip(".").upper() or "UNKNOWN"
    return {
        "path": str(path),
        "width": width,
        "height": height,
        "aspect_ratio": width / height,
        "format": image_format,
        "bytes": path.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot-beauty", required=True)
    parser.add_argument("--render", required=True)
    parser.add_argument("--expected-aspect", type=parse_ratio)
    parser.add_argument("--aspect-tolerance", type=float, default=0.005)
    parser.add_argument("--requested-size", type=parse_size)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    try:
        source = inspect_image(Path(args.godot_beauty).expanduser().resolve())
        render = inspect_image(Path(args.render).expanduser().resolve())
    except (FileNotFoundError, OSError) as exc:
        sys.exit(str(exc))

    expected_aspect = args.expected_aspect or float(source["aspect_ratio"])
    aspect_error = abs(float(render["aspect_ratio"]) - expected_aspect)
    aspect_passed = aspect_error <= args.aspect_tolerance
    requested_size = list(args.requested_size) if args.requested_size else None
    native_size_matches_request = (
        [render["width"], render["height"]] == requested_size
        if requested_size
        else None
    )
    report = {
        "godot_beauty": source,
        "native_render": render,
        "expected_aspect_ratio": expected_aspect,
        "aspect_tolerance": args.aspect_tolerance,
        "aspect_error": aspect_error,
        "aspect_passed": aspect_passed,
        "requested_size": requested_size,
        "native_size_matches_request": native_size_matches_request,
        "requires_visual_qa": True,
        "visual_qa_note": (
            "Inspect identity, morphology, pose, camera, object scale, anatomy, "
            "contacts, materials, and lighting against the Godot source."
        ),
    }
    report_path = Path(args.report).expanduser().resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Report: {report_path}")
    print(f"Native render: {render['width']}x{render['height']}")
    if native_size_matches_request is False:
        print("Native render differs from requested size; preserve it and label resampling.")
    return 0 if aspect_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
