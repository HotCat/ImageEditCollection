#!/usr/bin/env python3
"""Compact appearance references and validate a HeyRoute multipart image budget."""

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


def parse_role_path(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected ROLE=/absolute/path/image")
    role, raw_path = value.split("=", 1)
    role = re.sub(r"[^a-zA-Z0-9_-]+", "-", role.strip()).strip("-")
    if not role or not raw_path.strip():
        raise argparse.ArgumentTypeError("expected nonempty ROLE=/absolute/path/image")
    return role, Path(raw_path).expanduser().resolve()


def image_info(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with Image.open(path) as image:
        width, height = image.size
        image_format = image.format or path.suffix.lstrip(".").upper() or "UNKNOWN"
    return {
        "path": str(path),
        "width": width,
        "height": height,
        "format": image_format,
        "bytes": path.stat().st_size,
    }


def compact_reference(
    role: str,
    source: Path,
    output_dir: Path,
    max_long_edge: int,
    jpeg_quality: int,
) -> Path:
    destination = output_dir / f"{role}_{max_long_edge}.jpg"
    with Image.open(source) as image:
        image = image.convert("RGB")
        image.thumbnail((max_long_edge, max_long_edge), Image.Resampling.LANCZOS)
        image.save(destination, "JPEG", quality=jpeg_quality, optimize=True)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--fixed",
        action="append",
        default=[],
        help="Lossless scene/control input counted without modification; repeatable",
    )
    parser.add_argument(
        "--reference",
        action="append",
        default=[],
        type=parse_role_path,
        metavar="ROLE=PATH",
        help="Appearance reference compacted to JPEG; repeatable",
    )
    parser.add_argument("--max-long-edge", type=int, default=2048)
    parser.add_argument("--jpeg-quality", type=int, default=92)
    parser.add_argument("--budget-mib", type=float, default=29.0)
    parser.add_argument("--manifest", help="Default: OUTPUT_DIR/input_manifest.json")
    args = parser.parse_args()

    if args.max_long_edge < 256:
        parser.error("--max-long-edge must be at least 256")
    if not 1 <= args.jpeg_quality <= 95:
        parser.error("--jpeg-quality must be between 1 and 95")
    if args.budget_mib <= 0:
        parser.error("--budget-mib must be positive")

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = (
        Path(args.manifest).expanduser().resolve()
        if args.manifest
        else output_dir / "input_manifest.json"
    )

    fixed_items: list[dict[str, object]] = []
    reference_items: list[dict[str, object]] = []
    try:
        for raw_path in args.fixed:
            fixed_items.append(image_info(Path(raw_path).expanduser().resolve()))
        for role, source in args.reference:
            source_info = image_info(source)
            compact_path = compact_reference(
                role, source, output_dir, args.max_long_edge, args.jpeg_quality
            )
            reference_items.append(
                {
                    "role": role,
                    "source": source_info,
                    "compact": image_info(compact_path),
                }
            )
    except (FileNotFoundError, OSError) as exc:
        sys.exit(f"input preparation failed: {exc}")

    total_bytes = sum(int(item["bytes"]) for item in fixed_items)
    total_bytes += sum(int(item["compact"]["bytes"]) for item in reference_items)
    budget_bytes = round(args.budget_mib * 1024 * 1024)
    manifest = {
        "fixed": fixed_items,
        "references": reference_items,
        "total_bytes": total_bytes,
        "total_mib": round(total_bytes / 1024 / 1024, 3),
        "budget_bytes": budget_bytes,
        "budget_mib": args.budget_mib,
        "within_budget": total_bytes <= budget_bytes,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Manifest: {manifest_path}")
    print(f"Upload package: {manifest['total_mib']} MiB / {args.budget_mib} MiB")
    if not manifest["within_budget"]:
        print(
            "Package exceeds budget; lower --max-long-edge or --jpeg-quality.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
