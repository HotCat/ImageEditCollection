#!/usr/bin/env python3
"""Record a human visual decision for an experimental texture bake."""

import argparse
import json
from pathlib import Path


REQUIRED = {
    "identity_match", "no_duplicate_features", "no_neck_projection",
    "no_uv_seams", "no_background_contamination", "front_clean",
    "profiles_clean", "back_clean", "closeup_clean",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--render-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--decision", choices=("pass", "fail"), required=True)
    parser.add_argument("--expected-views", type=int, default=6)
    parser.add_argument("--pass-check", action="append", default=[], choices=sorted(REQUIRED),
                        help="Visual check that passed; repeat for every required check")
    parser.add_argument("--reason", action="append", default=[])
    args = parser.parse_args()
    paths = sorted(args.render_dir.glob("*.png"))
    images = [str(path.resolve()) for path in paths]
    if not images:
        raise SystemExit("No QA renders found")
    passed = set(args.pass_check)
    unknown = passed - REQUIRED
    if unknown:
        raise SystemExit(f"Unknown checks: {', '.join(sorted(unknown))}")
    missing = REQUIRED - passed
    azimuths = [path for path in paths if path.stem.startswith("azimuth_")]
    evidence_failures = []
    expected_stems = {
        f"azimuth_{round(index * 360.0 / args.expected_views):03d}"
        for index in range(args.expected_views)
    }
    found_stems = {path.stem for path in azimuths}
    if found_stems != expected_stems:
        evidence_failures.append(
            "azimuth render set differs: expected " + ", ".join(sorted(expected_stems))
            + "; found " + ", ".join(sorted(found_stems))
        )
    if not any(path.stem == "face_closeup" for path in paths):
        evidence_failures.append("missing face_closeup.png")
    if args.decision == "pass" and evidence_failures:
        raise SystemExit("Cannot pass: " + "; ".join(evidence_failures))
    if args.decision == "pass" and missing:
        raise SystemExit("Cannot pass: missing visual checks " + ", ".join(sorted(missing)))
    if args.decision == "fail" and not args.reason:
        raise SystemExit("A failed bake requires at least one --reason")
    result = {
        "decision": args.decision,
        "passed_checks": sorted(passed), "missing_checks": sorted(missing),
        "reasons": args.reason, "renders": images,
        "evidence_failures": evidence_failures,
        "delivery": "experimental_textured_glb" if args.decision == "pass" else "clean_neutral_realtime_proxy",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
