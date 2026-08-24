#!/usr/bin/env python3
"""Estimate depth and build a CrossView-Warp control video for a camera path."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image
import torch
from transformers import AutoImageProcessor, AutoModelForDepthEstimation


MODEL_ID = "depth-anything/Depth-Anything-V2-Small-hf"


def load_crossview(root: Path):
    path = root / "crossview_warp_node.py"
    if not path.is_file():
        raise RuntimeError(f"CrossView node is missing: {path}")
    spec = importlib.util.spec_from_file_location("crossview_warp_node", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load CrossView module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resize_crop(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    old_height, old_width = frame.shape[:2]
    scale = max(width / old_width, height / old_height)
    new_width = int(round(old_width * scale))
    new_height = int(round(old_height * scale))
    resized = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)
    x = max(0, (new_width - width) // 2)
    y = max(0, (new_height - height) // 2)
    return resized[y:y + height, x:x + width]


def read_frames(path: Path, count: int, width: int, height: int):
    capture = cv2.VideoCapture(str(path))
    try:
        for index in range(count):
            ok, bgr = capture.read()
            if not ok:
                raise RuntimeError(f"video ended at frame {index}; expected {count}")
            resized = resize_crop(bgr, width, height)
            yield cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    finally:
        capture.release()


def writer(path: Path, width: int, height: int, fps: int):
    process = subprocess.Popen(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
            "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264",
            "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", str(path),
        ],
        stdin=subprocess.PIPE,
    )
    if process.stdin is None:
        raise RuntimeError(f"could not open ffmpeg input for {path}")
    return process


def select_device(requested: str) -> str:
    if requested != "auto":
        return requested
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def load_camera_path(path: Path, frame_count: int) -> tuple[dict, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_keyframes = data.get("keyframes")
    if not isinstance(raw_keyframes, list) or not raw_keyframes:
        raise RuntimeError("camera path must contain a nonempty keyframes array")
    defaults = {
        "dist": 1.0,
        "vs": 0.0,
        "px": 0.0,
        "py": 0.0,
        "pz": 1.05,
    }
    keyframes: list[dict] = []
    for index, item in enumerate(raw_keyframes, 1):
        if not isinstance(item, dict):
            raise RuntimeError(f"camera keyframe {index} must be an object")
        try:
            frame = int(item.get("frame", item.get("f")))
            azimuth = float(item.get("azimuth", item.get("az")))
            elevation = float(item.get("elevation", item.get("el")))
        except (TypeError, ValueError):
            raise RuntimeError(
                f"camera keyframe {index} needs numeric frame, azimuth, and elevation"
            ) from None
        if not 1 <= frame <= frame_count:
            raise RuntimeError(f"camera keyframe {index} frame is outside 1..{frame_count}")
        keyframes.append(
            {
                "f": frame,
                "az": azimuth,
                "el": elevation,
                "dist": float(item.get("distance", item.get("dist", defaults["dist"]))),
                "vs": float(item.get("vertical_shift", item.get("vs", defaults["vs"]))),
                "px": float(item.get("pivot_x", item.get("px", defaults["px"]))),
                "py": float(item.get("pivot_y", item.get("py", defaults["py"]))),
                "pz": float(item.get("pivot_z", item.get("pz", defaults["pz"]))),
            }
        )
    keyframes.sort(key=lambda item: item["f"])
    frames = [item["f"] for item in keyframes]
    if len(frames) != len(set(frames)):
        raise RuntimeError("camera path contains duplicate frame numbers")
    for item in keyframes:
        if not -180 <= item["az"] <= 180:
            raise RuntimeError("azimuth must be between -180 and 180 degrees")
        if not -90 <= item["el"] <= 90:
            raise RuntimeError("elevation must be between -90 and 90 degrees")
        if not 0.1 <= item["dist"] <= 3.0:
            raise RuntimeError("distance must be between 0.1 and 3.0")
    return data, keyframes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--camera-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--crossview-root", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=241)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--work-width", type=int, default=640)
    parser.add_argument("--work-height", type=int, default=360)
    parser.add_argument("--output-width", type=int, default=1280)
    parser.add_argument("--output-height", type=int, default=720)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--device", default="auto", choices=("auto", "mps", "cuda", "cpu"))
    parser.add_argument("--model-id", default=MODEL_ID)
    parser.add_argument("--keep-depth-tensor", action="store_true")
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    camera_path_file = args.camera_path.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    crossview_root = args.crossview_root.expanduser().resolve()
    if not source.is_file():
        raise RuntimeError(f"normalized source is missing: {source}")
    if not camera_path_file.is_file():
        raise RuntimeError(f"camera path is missing: {camera_path_file}")
    if args.frames < 9 or (args.frames - 1) % 8:
        raise RuntimeError("LTX frame count must be 8n+1 and at least 9")
    output_dir.mkdir(parents=True, exist_ok=True)

    config, keyframes = load_camera_path(camera_path_file, args.frames)
    crossview = load_crossview(crossview_root)
    path = crossview._prepare_path(keyframes)
    interpolation = str(config.get("interpolation", "smooth"))
    if interpolation not in {"linear", "ease_in", "ease_out", "ease_in_out", "smooth"}:
        raise RuntimeError(f"unsupported interpolation: {interpolation}")
    smooth = interpolation == "smooth"
    easing = "linear" if smooth else interpolation
    hfov = float(config.get("hfov", 50.0))
    depth_ratio = float(config.get("depth_ratio", 6.0))
    if hfov < 20 or hfov > 120:
        raise RuntimeError("hfov must be between 20 and 120 degrees")
    if depth_ratio < 1.01:
        raise RuntimeError("depth_ratio must be at least 1.01")

    frame_count = args.frames
    work_height, work_width = args.work_height, args.work_width
    depth_path = output_dir / "depth_raw_f32.dat"
    depth_map = np.memmap(
        depth_path,
        dtype=np.float32,
        mode="w+",
        shape=(frame_count, work_height, work_width),
    )

    device = select_device(args.device)
    print(f"Loading {args.model_id} on {device}...", flush=True)
    processor = AutoImageProcessor.from_pretrained(args.model_id)
    model = AutoModelForDepthEstimation.from_pretrained(args.model_id).to(device).eval()
    pending: list[np.ndarray] = []
    base_index = 0

    def infer_batch(images: list[np.ndarray], start: int) -> None:
        pil_images = [Image.fromarray(image) for image in images]
        inputs = processor(images=pil_images, return_tensors="pt")
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.inference_mode():
            predicted = model(**inputs).predicted_depth
            predicted = torch.nn.functional.interpolate(
                predicted.unsqueeze(1),
                size=(work_height, work_width),
                mode="bicubic",
                align_corners=False,
            ).squeeze(1)
        depth_map[start:start + len(images)] = predicted.float().cpu().numpy()

    for index, frame in enumerate(read_frames(source, frame_count, work_width, work_height)):
        pending.append(frame)
        if len(pending) == args.batch_size or index == frame_count - 1:
            infer_batch(pending, base_index)
            base_index += len(pending)
            pending.clear()
            print(f"Depth: {base_index}/{frame_count}", flush=True)

    depth_map.flush()
    sample = np.asarray(depth_map[:, ::8, ::8]).reshape(-1)
    low, high = np.percentile(sample, [1.0, 99.0])
    print(f"Depth normalization: p01={low:.6f}, p99={high:.6f}", flush=True)

    warp_path = output_dir / f"crossview_warp_{frame_count}_{args.output_width}x{args.output_height}.mp4"
    depth_video_path = output_dir / f"depth_preview_{frame_count}_{args.output_width}x{args.output_height}.mp4"
    warp_writer = writer(warp_path, args.output_width, args.output_height, args.fps)
    depth_writer = writer(depth_video_path, args.output_width, args.output_height, args.fps)
    fx = work_width / (2.0 * math.tan(math.radians(hfov) / 2.0))
    reference_camera = np.eye(4)

    try:
        for index, rgb in enumerate(read_frames(source, frame_count, work_width, work_height)):
            raw = np.asarray(depth_map[index], dtype=np.float64)
            normalized = np.clip((raw - low) / (high - low + 1e-9), 0.0, 1.0)
            z = 1.0 / (
                1.0 / depth_ratio + (1.0 - 1.0 / depth_ratio) * normalized
            )
            pose = crossview._sample_path(path, index + 1, easing, smooth)
            pivot = np.array([pose["px"], pose["py"], pose["pz"]], dtype=np.float64)
            target_camera = crossview._orbit_C_tgt(
                pose["az"], pose["el"], pose["dist"], pivot
            )
            warped = crossview._warp_frame(
                rgb,
                z,
                reference_camera,
                target_camera,
                fx,
                2,
                work_width / 2.0,
                work_height / 2.0 + pose["vs"] * work_height,
            )
            warped = cv2.resize(
                warped,
                (args.output_width, args.output_height),
                interpolation=cv2.INTER_LANCZOS4,
            )
            depth_u8 = np.clip(normalized * 255.0, 0, 255).astype(np.uint8)
            depth_rgb = np.repeat(depth_u8[:, :, None], 3, axis=2)
            depth_rgb = cv2.resize(
                depth_rgb,
                (args.output_width, args.output_height),
                interpolation=cv2.INTER_LANCZOS4,
            )
            warp_writer.stdin.write(warped.tobytes())
            depth_writer.stdin.write(depth_rgb.tobytes())
            if (index + 1) % 10 == 0 or index + 1 == frame_count:
                print(f"Warp: {index + 1}/{frame_count}", flush=True)
    finally:
        warp_writer.stdin.close()
        depth_writer.stdin.close()

    warp_status = warp_writer.wait()
    depth_status = depth_writer.wait()
    if warp_status or depth_status:
        raise RuntimeError(f"ffmpeg failed: warp={warp_status}, depth={depth_status}")

    manifest = {
        "source": str(source),
        "camera_path": str(camera_path_file),
        "keyframes": keyframes,
        "interpolation": interpolation,
        "hfov": hfov,
        "depth_ratio": depth_ratio,
        "depth_model": args.model_id,
        "device": device,
        "frames": frame_count,
        "fps": args.fps,
        "work_size": [work_width, work_height],
        "output_size": [args.output_width, args.output_height],
        "warp_video": str(warp_path),
        "depth_preview": str(depth_video_path),
    }
    manifest_path = output_dir / "local_preprocess_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    del depth_map
    if not args.keep_depth_tensor:
        depth_path.unlink(missing_ok=True)
    print(f"Warp video: {warp_path}")
    print(f"Depth preview: {depth_video_path}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
