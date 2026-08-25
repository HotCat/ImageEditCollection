#!/usr/bin/env python3
"""Reject pose detections that are not a usable front-view A-pose."""

import argparse
import json
import math
from pathlib import Path


REQUIRED = [
    "left_shoulder", "left_elbow", "left_wrist", "right_shoulder",
    "right_elbow", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle", "nose",
]


def angle(a, b, c):
    first = (a["x"] - b["x"], a["y"] - b["y"])
    second = (c["x"] - b["x"], c["y"] - b["y"])
    denominator = math.hypot(*first) * math.hypot(*second)
    if denominator == 0:
        return 0.0
    cosine = max(-1.0, min(1.0, (first[0] * second[0] + first[1] * second[1]) / denominator))
    return math.degrees(math.acos(cosine))


def arm_abduction(shoulder, wrist):
    dx, dy = abs(wrist["x"] - shoulder["x"]), shoulder["y"] - wrist["y"]
    return math.degrees(math.atan2(dx, max(dy, 1e-6)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-confidence", type=float, default=0.30)
    parser.add_argument("--min-arm-angle", type=float, default=12.0)
    parser.add_argument("--max-arm-angle", type=float, default=70.0)
    parser.add_argument("--min-elbow-angle", type=float, default=150.0)
    args = parser.parse_args()
    data = json.loads(args.analysis.read_text(encoding="utf-8"))
    joints = data.get("body_joints", {})
    failures = []
    missing = [name for name in REQUIRED if name not in joints]
    if missing:
        failures.append("missing joints: " + ", ".join(missing))
    low = [name for name in REQUIRED if name in joints and joints[name].get("confidence", 0) < args.min_confidence]
    if low:
        failures.append("low-confidence joints: " + ", ".join(low))
    measurements = {}
    if not missing:
        for side in ("left", "right"):
            shoulder, elbow, wrist = (joints[f"{side}_{part}"] for part in ("shoulder", "elbow", "wrist"))
            elbow_angle = angle(shoulder, elbow, wrist)
            abduction = arm_abduction(shoulder, wrist)
            measurements[f"{side}_elbow_angle_deg"] = elbow_angle
            measurements[f"{side}_arm_abduction_deg"] = abduction
            if not args.min_arm_angle <= abduction <= args.max_arm_angle:
                failures.append(f"{side} arm abduction {abduction:.1f}° is outside A-pose range")
            if elbow_angle < args.min_elbow_angle:
                failures.append(f"{side} elbow angle {elbow_angle:.1f}° is too bent")
            if not (wrist["y"] < elbow["y"] < shoulder["y"]):
                failures.append(f"{side} wrist/elbow/shoulder are not ordered downward")
            hip, knee, ankle = (joints[f"{side}_{part}"] for part in ("hip", "knee", "ankle"))
            if not (ankle["y"] < knee["y"] < hip["y"]):
                failures.append(f"{side} hip/knee/ankle are not ordered downward")
        arm_difference = abs(
            measurements["left_arm_abduction_deg"] - measurements["right_arm_abduction_deg"]
        )
        measurements["arm_abduction_difference_deg"] = arm_difference
        if arm_difference > 15:
            failures.append(f"arm abduction differs by {arm_difference:.1f}°")
        if joints["nose"]["y"] - min(joints["left_ankle"]["y"], joints["right_ankle"]["y"]) < 0.50:
            failures.append("detected body occupies too little vertical image area")
    result = {
        "passed": not failures, "failures": failures,
        "analysis": str(args.analysis.resolve()), "measurements": measurements,
        "limits": {
            "min_confidence": args.min_confidence, "min_arm_angle": args.min_arm_angle,
            "max_arm_angle": args.max_arm_angle, "min_elbow_angle": args.min_elbow_angle,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(args.output)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
