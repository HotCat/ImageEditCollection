#!/usr/bin/env python3
"""Fill a per-frame subject mask with a neutral matte while preserving the source video."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def probe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a full-frame neutralized reference for a character replacement edit."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--mask", type=Path, required=True,
                        help="Per-frame video mask; white is editable and black is protected.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--matte-color", default="0x808080",
                        help="FFmpeg color for the neutral matte (default: 0x808080).")
    args = parser.parse_args()

    source_info = probe(args.source)
    video_stream = next(s for s in source_info["streams"] if s.get("codec_type") == "video")
    width = int(video_stream["width"])
    height = int(video_stream["height"])
    fps_num, fps_den = (int(x) for x in video_stream["r_frame_rate"].split("/"))
    fps = fps_num / fps_den
    frames = int(video_stream.get("nb_frames") or 0)
    if frames <= 0:
        duration = float(source_info["format"]["duration"])
        frames = round(duration * fps)

    mask_info = probe(args.mask)
    mask_stream = next(s for s in mask_info["streams"] if s.get("codec_type") == "video")
    mask_frames = int(mask_stream.get("nb_frames") or 0)
    if mask_frames and abs(mask_frames - frames) > 1:
        raise ValueError(f"mask has {mask_frames} frames but source has {frames}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    size = f"{width}x{height}"
    filter_graph = (
        f"color=c={args.matte_color}:s={size}:r={fps_num}/{fps_den}[matte];"
        f"[1:v]format=gray,scale={size}:flags=neighbor[mask];"
        "[matte][mask]alphamerge[matte_a];"
        "[0:v][matte_a]overlay=0:0:format=auto[outv]"
    )
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(args.source), "-i", str(args.mask),
        "-filter_complex", filter_graph,
        "-map", "[outv]", "-map", "0:a:0?", "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
        str(args.output),
    ]
    subprocess.run(command, check=True)

    output_info = probe(args.output)
    output_video = next(s for s in output_info["streams"] if s.get("codec_type") == "video")
    checks = {
        "width": int(output_video["width"]) == width,
        "height": int(output_video["height"]) == height,
        "frame_count": int(output_video.get("nb_frames") or 0) == frames,
        "fps": output_video["r_frame_rate"] == video_stream["r_frame_rate"],
        "audio": any(s.get("codec_type") == "audio" for s in output_info["streams"])
        == any(s.get("codec_type") == "audio" for s in source_info["streams"]),
    }
    if not all(checks.values()):
        raise RuntimeError(f"output validation failed: {checks}")
    print(json.dumps({"output": str(args.output), "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
