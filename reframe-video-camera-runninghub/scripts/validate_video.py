#!/usr/bin/env python3
"""Probe a video, validate expected properties, and optionally make a 3-frame sheet."""

from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys

import cv2
import numpy as np


def probe(path: Path) -> dict:
    completed = subprocess.run(
        [
            "ffprobe", "-v", "error", "-count_frames", "-show_streams",
            "-show_format", "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    raw = json.loads(completed.stdout)
    video = next((s for s in raw.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise RuntimeError("file contains no video stream")
    rate_text = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
    rate = float(Fraction(rate_text)) if rate_text != "0/0" else 0.0
    frame_text = video.get("nb_read_frames") or video.get("nb_frames")
    frames = int(frame_text) if frame_text not in (None, "N/A") else None
    duration_text = video.get("duration") or raw.get("format", {}).get("duration")
    duration = float(duration_text) if duration_text not in (None, "N/A") else None
    return {
        "path": str(path),
        "codec": video.get("codec_name"),
        "width": int(video.get("width", 0)),
        "height": int(video.get("height", 0)),
        "frames": frames,
        "fps": rate,
        "duration": duration,
        "has_audio": any(s.get("codec_type") == "audio" for s in raw.get("streams", [])),
    }


def contact_sheet(path: Path, output: Path, frame_count: int | None) -> None:
    capture = cv2.VideoCapture(str(path))
    count = frame_count or int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    indices = [0, max(0, (count - 1) // 2), max(0, count - 1)]
    panels = []
    try:
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError(f"could not read frame {index + 1}")
            height, width = frame.shape[:2]
            panel_width = 480
            panel_height = max(1, round(height * panel_width / width))
            frame = cv2.resize(frame, (panel_width, panel_height), interpolation=cv2.INTER_AREA)
            cv2.putText(
                frame,
                f"frame {index + 1}",
                (14, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            panels.append(frame)
    finally:
        capture.release()
    sheet = np.concatenate(panels, axis=1)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), sheet):
        raise RuntimeError(f"could not write contact sheet: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--expect-frames", type=int)
    parser.add_argument("--expect-fps", type=float)
    parser.add_argument("--expect-width", type=int)
    parser.add_argument("--expect-height", type=int)
    parser.add_argument("--sheet", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    video = args.video.expanduser().resolve()
    if not video.is_file() or video.stat().st_size == 0:
        raise RuntimeError(f"video is missing or empty: {video}")
    info = probe(video)
    failures = []
    for key, expected in (
        ("frames", args.expect_frames),
        ("width", args.expect_width),
        ("height", args.expect_height),
    ):
        if expected is not None and info[key] != expected:
            failures.append(f"{key}: expected {expected}, got {info[key]}")
    if args.expect_fps is not None and abs(info["fps"] - args.expect_fps) > 0.01:
        failures.append(f"fps: expected {args.expect_fps}, got {info['fps']}")
    if args.sheet:
        contact_sheet(video, args.sheet.expanduser().resolve(), info["frames"])
        info["contact_sheet"] = str(args.sheet.expanduser().resolve())
    if args.json_output:
        destination = args.json_output.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(info, indent=2))
    if failures:
        raise RuntimeError("; ".join(failures))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
