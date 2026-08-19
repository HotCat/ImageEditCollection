#!/usr/bin/env python3
"""Burn ASS karaoke subtitles into MP4 and verify that media invariants are preserved."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path


def probe(path: Path, count_frames: bool = False) -> dict:
    command = [
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json",
    ]
    if count_frames:
        command.insert(3, "-count_frames")
    command.append(str(path))
    return json.loads(subprocess.check_output(command, text=True))


def video_stream(data: dict) -> dict:
    return next(stream for stream in data["streams"] if stream["codec_type"] == "video")


def fps(stream: dict) -> float:
    numerator, denominator = stream["r_frame_rate"].split("/")
    return float(numerator) / float(denominator)


def frame_count(stream: dict, duration: float) -> int:
    value = stream.get("nb_read_frames") or stream.get("nb_frames")
    return int(value) if value and value != "N/A" else round(fps(stream) * duration)


def escape_filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--ass", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--preset", default="fast")
    parser.add_argument("--fonts-dir", type=Path)
    args = parser.parse_args()

    if args.output.resolve() == args.video.resolve():
        parser.error("output must differ from input")
    before = probe(args.video, count_frames=True)
    source_video = video_stream(before)
    source_duration = float(before["format"]["duration"])
    source_frames = frame_count(source_video, source_duration)
    has_audio = any(stream["codec_type"] == "audio" for stream in before["streams"])

    subtitle_filter = f"ass='{escape_filter_path(args.ass)}'"
    if args.fonts_dir:
        subtitle_filter += f":fontsdir='{escape_filter_path(args.fonts_dir)}'"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-hide_banner", "-y", "-i", str(args.video),
        "-vf", subtitle_filter,
        "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
        "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(args.output),
    ]
    subprocess.run(command, check=True)

    after = probe(args.output, count_frames=True)
    output_video = video_stream(after)
    output_duration = float(after["format"]["duration"])
    output_frames = frame_count(output_video, output_duration)
    output_audio = any(stream["codec_type"] == "audio" for stream in after["streams"])
    failures: list[str] = []
    if (source_video["width"], source_video["height"]) != (output_video["width"], output_video["height"]):
        failures.append("resolution changed")
    if not math.isclose(fps(source_video), fps(output_video), rel_tol=0, abs_tol=1e-6):
        failures.append("frame rate changed")
    if source_frames != output_frames:
        failures.append(f"frame count changed: {source_frames} -> {output_frames}")
    if abs(source_duration - output_duration) > max(0.05, 1 / fps(source_video)):
        failures.append("duration changed")
    if has_audio != output_audio:
        failures.append("audio presence changed")
    if failures:
        raise RuntimeError("; ".join(failures))

    print(f"resolution={output_video['width']}x{output_video['height']}")
    print(f"fps={fps(output_video):.6f}")
    print(f"frames={output_frames}")
    print(f"duration={output_duration:.6f}")
    print(f"audio_stream_copied={'yes' if has_audio else 'not_present'}")
    print(args.output)


if __name__ == "__main__":
    main()
