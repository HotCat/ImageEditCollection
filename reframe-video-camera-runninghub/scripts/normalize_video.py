#!/usr/bin/env python3
"""Normalize a source video to an exact frame count, fps, crop, and duration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


def probe(path: Path) -> dict:
    completed = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=241)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--crf", type=int, default=18)
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("ffmpeg and ffprobe are required")
    source = args.source.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not source.is_file():
        raise RuntimeError(f"source video does not exist: {source}")
    if args.frames < 9 or (args.frames - 1) % 8:
        raise RuntimeError("LTX frame count must be 8n+1 and at least 9")
    if args.fps <= 0 or args.width <= 0 or args.height <= 0:
        raise RuntimeError("fps, width, and height must be positive")

    metadata = probe(source)
    has_audio = any(s.get("codec_type") == "audio" for s in metadata.get("streams", []))
    duration = args.frames / args.fps
    output.parent.mkdir(parents=True, exist_ok=True)
    video_filter = (
        f"fps={args.fps},"
        f"scale={args.width}:{args.height}:force_original_aspect_ratio=increase,"
        f"crop={args.width}:{args.height},"
        "tpad=stop_mode=clone:stop_duration=3600,"
        f"trim=end_frame={args.frames},setpts=N/({args.fps}*TB)"
    )
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
        "-map", "0:v:0", "-vf", video_filter,
        "-c:v", "libx264", "-preset", "medium", "-crf", str(args.crf),
        "-pix_fmt", "yuv420p",
    ]
    if has_audio:
        command += [
            "-map", "0:a:0?", "-af", f"apad,atrim=duration={duration:.9f}",
            "-c:a", "aac", "-b:a", "192k",
        ]
    else:
        command += ["-an"]
    command += ["-movflags", "+faststart", str(output)]
    subprocess.run(command, check=True)
    print(output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
