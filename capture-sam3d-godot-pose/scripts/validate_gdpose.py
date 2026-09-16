#!/usr/bin/env python3
"""Validate a Godot pose document and one generated SAM 3D pose profile."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Mapping


EXPECTED_IK_CONTROLS = (
    "pelvis_target", "center_back_target", "neck_target", "head_target",
    "l_arm_marker", "l_arm_pole", "r_arm_marker", "r_arm_pole",
    "l_feet_marker", "l_feet_pole", "r_feet_marker", "r_feet_pole",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument("--pose-name", help="profile to validate; defaults to active_pose")
    parser.add_argument("--expected-rig-bones", type=int,
                        help="require this many entries in top-level rig.bones")
    parser.add_argument("--require-sam3d-source", action="store_true",
                        help="require source.kind=sam3d_body_mhr70")
    parser.add_argument("--allow-partial-ik", action="store_true",
                        help="do not require all twelve humanoid PoseControls entries")
    return parser.parse_args(argv)


def numeric_vector(value: object, length: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == length
        and all(isinstance(item, (int, float)) and math.isfinite(float(item)) for item in value)
    )


def validate_document(document: object, args: argparse.Namespace) -> tuple[list[str], dict[str, object]]:
    failures: list[str] = []
    if not isinstance(document, Mapping):
        return ["document root must be an object"], {}
    if document.get("schema") != "godot-pose-document":
        failures.append("schema must be godot-pose-document")
    if document.get("version") != 1:
        failures.append("version must be 1")
    poses = document.get("poses")
    if not isinstance(poses, Mapping) or not poses:
        return failures + ["poses must be a non-empty object"], {}
    active_pose = document.get("active_pose")
    if not isinstance(active_pose, str) or active_pose not in poses:
        failures.append("active_pose must name an existing profile")
    pose_name = args.pose_name or active_pose
    if not isinstance(pose_name, str) or pose_name not in poses:
        return failures + [f"pose profile not found: {pose_name!r}"], {}

    rig = document.get("rig", {})
    rig_bones = rig.get("bones", []) if isinstance(rig, Mapping) else []
    if args.expected_rig_bones is not None:
        if not isinstance(rig_bones, list) or len(rig_bones) != args.expected_rig_bones:
            failures.append(
                f"rig.bones must contain {args.expected_rig_bones} entries "
                f"(found {len(rig_bones) if isinstance(rig_bones, list) else 0})"
            )

    pose = poses[pose_name]
    if not isinstance(pose, Mapping):
        return failures + [f"pose {pose_name!r} must be an object"], {}
    mode = pose.get("mode")
    if mode not in ("fk", "ik", "hybrid"):
        failures.append("pose mode must be fk, ik, or hybrid")
    modifiers = pose.get("modifiers", {})
    if not isinstance(modifiers, Mapping) or any(not isinstance(value, bool) for value in modifiers.values()):
        failures.append("pose modifiers must map names to booleans")

    controls = pose.get("ik", {})
    if not isinstance(controls, Mapping):
        failures.append("pose ik must be an object")
        controls = {}
    missing_controls = [name for name in EXPECTED_IK_CONTROLS if name not in controls]
    if missing_controls and not args.allow_partial_ik:
        failures.append("missing IK controls: " + ", ".join(missing_controls))
    for name, transform in controls.items():
        if not isinstance(transform, Mapping):
            failures.append(f"IK control {name} must be an object")
            continue
        if "position" in transform and not numeric_vector(transform["position"], 3):
            failures.append(f"IK control {name}.position must be three finite numbers")
        if "rotation_quaternion" in transform and not numeric_vector(transform["rotation_quaternion"], 4):
            failures.append(f"IK control {name}.rotation_quaternion must be four finite numbers")

    bones = pose.get("bones", {})
    if not isinstance(bones, Mapping):
        failures.append("pose bones must be an object")
        bones = {}
    for name, transform in bones.items():
        if not isinstance(transform, Mapping):
            failures.append(f"bone {name} must be an object")
            continue
        if "rotation_degrees" in transform and not numeric_vector(transform["rotation_degrees"], 3):
            failures.append(f"bone {name}.rotation_degrees must be three finite numbers")
        if "rotation_quaternion" in transform and not numeric_vector(transform["rotation_quaternion"], 4):
            failures.append(f"bone {name}.rotation_quaternion must be four finite numbers")

    source = pose.get("source", {})
    if args.require_sam3d_source and (
        not isinstance(source, Mapping) or source.get("kind") != "sam3d_body_mhr70"
    ):
        failures.append("pose source.kind must be sam3d_body_mhr70")

    return failures, {
        "pose_name": pose_name,
        "mode": mode,
        "rig_bone_count": len(rig_bones) if isinstance(rig_bones, list) else 0,
        "ik_control_count": len(controls),
        "bone_override_count": len(bones),
        "missing_ik_controls": missing_controls,
        "source_kind": source.get("kind") if isinstance(source, Mapping) else None,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        document = json.loads(args.document.read_text(encoding="utf-8"))
        failures, summary = validate_document(document, args)
    except (OSError, json.JSONDecodeError) as error:
        print(f"validate_gdpose: {error}", file=sys.stderr)
        return 1
    result = {"passed": not failures, "failures": failures, **summary}
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
