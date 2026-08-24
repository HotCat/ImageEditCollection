#!/usr/bin/env python3
"""Run local CrossView preprocessing and the deployed RunningHub LTX workflow."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


DEFAULT_WORKFLOW_ID = "2091756366166839297"


def run(command: list[str]) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, check=True)


def default_helper() -> Path:
    candidate = Path(__file__).resolve().parents[2] / "run-runninghub-workflows" / "scripts" / "runninghub_workflow.py"
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--camera-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--crossview-root", type=Path, required=True)
    parser.add_argument("--runninghub-helper", type=Path, default=default_helper())
    parser.add_argument("--workflow-id", default=DEFAULT_WORKFLOW_ID)
    parser.add_argument("--frames", type=int, default=241)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--work-width", type=int, default=640)
    parser.add_argument("--work-height", type=int, default=360)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--device", default="auto", choices=("auto", "mps", "cuda", "cpu"))
    parser.add_argument("--prompt", default="crossview.")
    parser.add_argument("--timeout", type=float, default=7200.0)
    parser.add_argument("--skip-runninghub", action="store_true")
    parser.add_argument("--keep-depth-tensor", action="store_true")
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    camera_path = args.camera_path.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    crossview_root = args.crossview_root.expanduser().resolve()
    helper = args.runninghub_helper.expanduser().resolve()
    scripts = Path(__file__).resolve().parent
    if not source.is_file():
        raise RuntimeError(f"source video is missing: {source}")
    if not camera_path.is_file():
        raise RuntimeError(f"camera path is missing: {camera_path}")
    if args.frames > 241:
        raise RuntimeError("more than 241 frames requires explicit workflow capacity validation")
    if args.frames < 9 or (args.frames - 1) % 8:
        raise RuntimeError("LTX frame count must be 8n+1 and at least 9")
    if not args.prompt.lstrip().lower().startswith("crossview."):
        raise RuntimeError("prompt must begin with 'crossview.'")

    local_dir = output_dir / "local_preprocess"
    cloud_dir = output_dir / "runninghub_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized = local_dir / f"source_{args.frames}_{args.fps}fps.mp4"
    run(
        [
            sys.executable,
            str(scripts / "normalize_video.py"),
            "--source", str(source),
            "--output", str(normalized),
            "--frames", str(args.frames),
            "--fps", str(args.fps),
            "--width", str(args.width),
            "--height", str(args.height),
        ]
    )
    preprocess_command = [
        sys.executable,
        str(scripts / "build_crossview_control.py"),
        "--source", str(normalized),
        "--camera-path", str(camera_path),
        "--output-dir", str(local_dir),
        "--crossview-root", str(crossview_root),
        "--frames", str(args.frames),
        "--fps", str(args.fps),
        "--work-width", str(args.work_width),
        "--work-height", str(args.work_height),
        "--output-width", str(args.width),
        "--output-height", str(args.height),
        "--batch-size", str(args.batch_size),
        "--device", args.device,
    ]
    if args.keep_depth_tensor:
        preprocess_command.append("--keep-depth-tensor")
    run(preprocess_command)

    warp = local_dir / f"crossview_warp_{args.frames}_{args.width}x{args.height}.mp4"
    for video, label in ((normalized, "normalized_source"), (warp, "crossview_warp")):
        run(
            [
                sys.executable,
                str(scripts / "validate_video.py"),
                "--video", str(video),
                "--expect-frames", str(args.frames),
                "--expect-fps", str(args.fps),
                "--expect-width", str(args.width),
                "--expect-height", str(args.height),
                "--json-output", str(local_dir / f"{label}_probe.json"),
                "--sheet", str(local_dir / f"{label}_start_mid_end.png"),
            ]
        )

    if args.skip_runninghub:
        print(f"Local preprocessing complete: {warp}")
        return 0
    if not helper.is_file():
        raise RuntimeError(f"RunningHub API helper is missing: {helper}")
    if not os.environ.get("RUNNINGHUB_API_KEY", "").strip():
        raise RuntimeError("RUNNINGHUB_API_KEY is not set; local preprocessing is complete")

    started = time.time()
    run(
        [
            sys.executable,
            str(helper),
            "run",
            "--workflow-id", args.workflow_id,
            "--upload", f"441:video:{normalized}",
            "--upload", f"447:video:{warp}",
            "--set", f"447:force_rate:{args.fps}",
            "--set", f"447:frame_load_cap:{args.frames}",
            "--set", f"301:value:{args.frames}",
            "--set", f"300:value:{args.fps}",
            "--set", f"314:value:{args.width}",
            "--set", f"299:value:{args.height}",
            "--set", f"303:value:{args.prompt}",
            "--set", "319:vae_name:LTX23_video_vae_bf16.safetensors",
            "--set", "320:vae_name:LTX23_audio_vae_bf16.safetensors",
            "--set", "324:clip_name1:gemma_3_12B_it_fp8_e4m3fn.safetensors",
            "--set", "324:clip_name2:ltx-2.3_text_projection_bf16.safetensors",
            "--output-dir", str(cloud_dir),
            "--timeout", str(args.timeout),
        ]
    )

    runninghub_manifests = sorted(cloud_dir.glob("runninghub_*_manifest.json"), key=lambda p: p.stat().st_mtime)
    if not runninghub_manifests or runninghub_manifests[-1].stat().st_mtime < started:
        raise RuntimeError("RunningHub completed without a new manifest")
    runninghub_manifest_path = runninghub_manifests[-1]
    runninghub_manifest = json.loads(runninghub_manifest_path.read_text(encoding="utf-8"))
    target_videos = []
    for index, item in enumerate(runninghub_manifest.get("outputs", []), 1):
        path = Path(item["path"])
        if path.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}:
            continue
        probe_path = cloud_dir / f"target_{index}_probe.json"
        sheet_path = cloud_dir / f"target_{index}_start_mid_end.png"
        run(
            [
                sys.executable,
                str(scripts / "validate_video.py"),
                "--video", str(path),
                "--expect-frames", str(args.frames),
                "--expect-fps", str(args.fps),
                "--json-output", str(probe_path),
                "--sheet", str(sheet_path),
            ]
        )
        target_videos.append(str(path))
    if not target_videos:
        raise RuntimeError("RunningHub manifest contains no video output")

    experiment_manifest = {
        "source": str(source),
        "camera_path": str(camera_path),
        "workflow_id": args.workflow_id,
        "runninghub_task_id": runninghub_manifest.get("taskId"),
        "normalized_source": str(normalized),
        "crossview_warp": str(warp),
        "local_manifest": str(local_dir / "local_preprocess_manifest.json"),
        "runninghub_manifest": str(runninghub_manifest_path),
        "target_videos": target_videos,
    }
    experiment_manifest_path = output_dir / "experiment_manifest.json"
    experiment_manifest_path.write_text(
        json.dumps(experiment_manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Experiment manifest: {experiment_manifest_path}")
    for path in target_videos:
        print(f"Target video: {path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
