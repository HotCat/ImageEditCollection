#!/usr/bin/env python3
"""Create or verify the local runtime used by the camera-reframing skill."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


CROSSVIEW_URL = "https://github.com/cseti007/ComfyUI-CrossViewWarp.git"
CROSSVIEW_REVISION = "3266a83a84eaa6833a9ebc38ac7cdd8789e44f5b"
IMPORTS = ("numpy", "cv2", "PIL", "torch", "transformers", "truststore")


def run(command: list[str], *, dry_run: bool = False) -> None:
    print("+ " + " ".join(command), flush=True)
    if not dry_run:
        subprocess.run(command, check=True)


def require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"required command is unavailable: {name}")


def venv_python(runtime_dir: Path) -> Path:
    return runtime_dir / "venv" / "bin" / "python"


def checkout_crossview(runtime_dir: Path, dry_run: bool) -> Path:
    checkout = runtime_dir / "ComfyUI-CrossViewWarp"
    if not checkout.exists():
        run(["git", "clone", CROSSVIEW_URL, str(checkout)], dry_run=dry_run)
    elif not (checkout / ".git").is_dir():
        raise RuntimeError(f"CrossView target exists but is not a Git checkout: {checkout}")

    if dry_run and not checkout.exists():
        return checkout

    dirty = subprocess.run(
        ["git", "-C", str(checkout), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if dirty:
        raise RuntimeError(f"CrossView checkout has local changes; refusing to replace them: {checkout}")
    run(["git", "-C", str(checkout), "fetch", "origin", CROSSVIEW_REVISION], dry_run=dry_run)
    run(["git", "-C", str(checkout), "switch", "--detach", CROSSVIEW_REVISION], dry_run=dry_run)
    return checkout


def verify(python: Path, checkout: Path, dry_run: bool) -> None:
    code = (
        "import importlib.util, pathlib; "
        + "; ".join(f"import {name}" for name in IMPORTS)
        + "; p=pathlib.Path(r'" + str(checkout / "crossview_warp_node.py") + "'); "
        + "s=importlib.util.spec_from_file_location('crossview_warp_node', p); "
        + "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
        + "print('runtime imports and CrossView helpers: OK')"
    )
    run([str(python), "-c", code], dry_run=dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--python", default="python3.12", help="Python 3.12 executable")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    for command in ("git", "ffmpeg", "ffprobe"):
        require_command(command)

    runtime_dir = args.runtime_dir.expanduser().resolve()
    python = venv_python(runtime_dir)
    checkout = runtime_dir / "ComfyUI-CrossViewWarp"

    if args.check_only:
        if not python.is_file():
            raise RuntimeError(f"virtual-environment interpreter not found: {python}")
        if not (checkout / "crossview_warp_node.py").is_file():
            raise RuntimeError(f"CrossView checkout not found: {checkout}")
        verify(python, checkout, args.dry_run)
        print(f"Runtime ready: {runtime_dir}")
        return 0

    runtime_dir.mkdir(parents=True, exist_ok=True)
    if not python.exists():
        run([args.python, "-m", "venv", str(runtime_dir / "venv")], dry_run=args.dry_run)

    requirements = Path(__file__).with_name("requirements-macos.txt")
    run(
        [str(python), "-m", "pip", "install", "--upgrade", "pip"],
        dry_run=args.dry_run,
    )
    run(
        [str(python), "-m", "pip", "install", "-r", str(requirements)],
        dry_run=args.dry_run,
    )
    checkout = checkout_crossview(runtime_dir, args.dry_run)
    verify(python, checkout, args.dry_run)
    print(f"Runtime ready: {runtime_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
