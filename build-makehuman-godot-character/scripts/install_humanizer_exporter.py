#!/usr/bin/env python3
"""Install the versioned Humanizer proxy exporter into a Humanizer project.

Humanizer's GDScript exporter must run inside the project so its global classes,
autoload services, generated targets, equipment, materials, rigs, and animations
are registered. This installer copies only the two deterministic runner files;
it does not change project.godot or enable/disable plugins.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


TOOL_SUBDIR = Path("tools/build_makehuman_godot_character")
FILES = ("export_humanizer_proxy.gd", "export_humanizer_proxy.tscn")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True,
                        help="Humanizer Godot project containing project.godot")
    parser.add_argument("--force", action="store_true",
                        help="Replace an installed exporter whose contents differ")
    args = parser.parse_args()
    project = args.project.expanduser().resolve()
    if not (project / "project.godot").is_file():
        raise SystemExit(f"Not a Godot project (project.godot missing): {project}")
    if not (project / "addons" / "humanizer").is_dir():
        raise SystemExit(f"Humanizer addon directory is missing: {project / 'addons/humanizer'}")

    source_dir = Path(__file__).resolve().parent
    destination = project / TOOL_SUBDIR
    destination.mkdir(parents=True, exist_ok=True)
    installed = []
    for name in FILES:
        source = source_dir / name
        target = destination / name
        if target.exists() and digest(target) != digest(source) and not args.force:
            raise SystemExit(
                f"Refusing to overwrite modified exporter: {target}\n"
                "Review it or rerun with --force."
            )
        shutil.copy2(source, target)
        installed.append({"path": str(target), "sha256": digest(target)})
    print(json.dumps({"project": str(project), "installed": installed}, indent=2))


if __name__ == "__main__":
    main()
