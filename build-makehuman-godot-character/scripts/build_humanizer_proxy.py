#!/usr/bin/env python3
"""Build and fresh-import-calibrate a Humanizer-native realtime proxy.

Humanizer can fit its source body arrays to an exact height while glTF skin/rest
transforms change the fresh-imported deformed body height slightly. This
orchestrator closes that gap without global scaling: it repeatedly asks the
Humanizer exporter for a morphology height, measures only the body surface of the
resulting GLB in a factory Blender process, and adjusts only the requested
Humanizer height until anatomical height converges. Hair-inclusive visual height
is reported separately and never drives morphology.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
INSTALLER = SCRIPT_DIR / "install_humanizer_exporter.py"
VALIDATOR = SCRIPT_DIR / "validate_glb.py"
SCENE = "res://tools/build_makehuman_godot_character/export_humanizer_proxy.tscn"


def run(command: list[str], *, label: str) -> subprocess.CompletedProcess:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        tail = "\n".join(result.stdout.splitlines()[-120:])
        raise RuntimeError(f"{label} failed with exit {result.returncode}:\n{tail}")
    return result


def executable(path: Path, label: str) -> str:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise SystemExit(f"{label} executable does not exist: {resolved}")
    return str(resolved)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--preset", type=Path, required=True)
    parser.add_argument("--height", type=float, required=True,
                        help="Target fresh-imported anatomical body height in metres")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--gender-map", choices=("invert", "identity"), default="invert")
    parser.add_argument("--body-material", default="")
    parser.add_argument("--hair", default="auto")
    parser.add_argument("--hair-material", default="")
    parser.add_argument("--rig", default="")
    parser.add_argument("--godot", type=Path,
                        default=Path("/Applications/Godot.app/Contents/MacOS/Godot"))
    parser.add_argument("--blender", type=Path,
                        default=Path("/Applications/Blender 4.5.app/Contents/MacOS/Blender"))
    parser.add_argument("--height-tolerance", type=float, default=0.001)
    parser.add_argument("--max-iterations", type=int, default=4)
    parser.add_argument("--min-bones", type=int, default=50)
    parser.add_argument(
        "--min-surfaces", type=int,
        help=(
            "Override the structural surface minimum. Default is derived from "
            "equipment: 8 with face parts and hair, 7 with face parts/no hair, "
            "or 1 for --no-face-parts."
        ),
    )
    parser.add_argument("--no-face-parts", action="store_true")
    return parser.parse_args()


def exporter_command(args, godot: str, morphology_height: float, report: Path):
    command = [
        godot, "--headless", "--path", str(args.project.resolve()),
        "--scene", SCENE, "--",
        "--preset", str(args.preset.resolve()),
        "--height", f"{morphology_height:.9f}",
        "--gender-map", args.gender_map,
        "--hair", args.hair,
        "--output", str(args.output.resolve()),
        "--report", str(report),
    ]
    for flag, value in (
        ("--body-material", args.body_material),
        ("--hair-material", args.hair_material),
        ("--rig", args.rig),
    ):
        if value:
            command.extend((flag, value))
    if args.no_face_parts:
        command.append("--no-face-parts")
    return command


def validator_command(args, blender: str, report: Path, expected_height=None):
    command = [
        blender, "--background", "--factory-startup", "--python", str(VALIDATOR), "--",
        "--glb", str(args.output.resolve()),
        "--output", str(report),
        "--min-bones", str(args.min_bones),
        "--require-all-mesh-nodes-skinned",
        "--require-single-payload-mesh",
        "--min-surfaces", str(args.min_surfaces),
        # Humanizer appends equipment into one Avatar in deterministic order:
        # body first, then eyes/brows/lashes/hair. Calibrating surface 0 prevents
        # a tall hairstyle from being mistaken for anatomical stature.
        "--height-surface-index", "0",
        "--require-animation", "Idle",
        "--require-animation", "Run",
    ]
    if expected_height is not None:
        command.extend((
            "--expected-height", f"{expected_height:.9f}",
            "--height-tolerance", f"{args.height_tolerance:.9f}",
        ))
    return command


def main():
    args = parse_args()
    if not 0.5 < args.height < 2.6:
        raise SystemExit("--height must be a plausible human height in metres")
    if args.height_tolerance <= 0 or args.height_tolerance > 0.02:
        raise SystemExit("--height-tolerance must be greater than 0 and at most 0.02 m")
    if args.max_iterations < 1 or args.max_iterations > 10:
        raise SystemExit("--max-iterations must be between 1 and 10")
    if args.min_surfaces is None:
        # Body + two eyes + two brows + two lashes + optional hair. Keeping the
        # threshold tied to requested equipment makes documented headless/body-only
        # modes valid without weakening the normal production proxy gate.
        args.min_surfaces = 1 if args.no_face_parts else (7 if args.hair == "none" else 8)
    if args.min_surfaces < 1:
        raise SystemExit("--min-surfaces must be at least 1")
    if not args.preset.is_file():
        raise SystemExit(f"MPFB preset does not exist: {args.preset}")
    godot = executable(args.godot, "Godot")
    blender = executable(args.blender, "Blender")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    run([
        sys.executable, str(INSTALLER), "--project", str(args.project.resolve()), "--force"
    ], label="Humanizer exporter installation")

    morphology_height = args.height
    trials = []
    final_humanizer_report = None
    final_validation = None
    with tempfile.TemporaryDirectory(prefix="humanizer-proxy-calibration-") as temp:
        temp_dir = Path(temp)
        for iteration in range(args.max_iterations):
            humanizer_report = temp_dir / f"humanizer_{iteration}.json"
            import_report = temp_dir / f"import_{iteration}.json"
            run(
                exporter_command(args, godot, morphology_height, humanizer_report),
                label=f"Humanizer export iteration {iteration + 1}",
            )
            final_humanizer_report = json.loads(
                humanizer_report.read_text(encoding="utf-8")
            )
            # The validator's surface measurement is meaningful only while the
            # exporter preserves its documented body-first combined-mesh order.
            # Fail loudly if a future Humanizer version changes that invariant.
            if final_humanizer_report.get("body_surface_index") != 0:
                raise RuntimeError(
                    "Humanizer exporter did not place Body-Default at surface 0: "
                    f"{final_humanizer_report.get('surface_equipment_order')}"
                )
            # Run strict structural gates on every iteration, but omit expected
            # height until convergence so a useful measurement report is produced.
            run(
                validator_command(args, blender, import_report),
                label=f"fresh-import validation iteration {iteration + 1}",
            )
            final_validation = json.loads(import_report.read_text(encoding="utf-8"))
            imported_height = float(final_validation["fresh_import"]["height_m"])
            imported_visual_height = float(
                final_validation["fresh_import"]["visual_height_m"]
            )
            error = imported_height - args.height
            trials.append({
                "iteration": iteration + 1,
                "requested_morphology_height_m": morphology_height,
                "fresh_import_height_m": imported_height,
                "fresh_import_body_height_m": imported_height,
                "fresh_import_visual_height_m": imported_visual_height,
                "height_measurement_surface_index": 0,
                "error_m": error,
                "calibrated_height_macro": final_humanizer_report.get("calibrated_height_macro"),
            })
            if abs(error) <= args.height_tolerance:
                break
            if imported_height <= 0:
                raise RuntimeError("Fresh-import validator returned a non-positive character height")
            # Multiplicative feedback is stable because MakeHuman's height macro is
            # locally monotonic. The Humanizer exporter re-fits every component and
            # skeleton; no object/root scale is introduced.
            morphology_height *= args.height / imported_height
        else:
            raise RuntimeError(
                f"Anatomical body height did not converge within "
                f"{args.max_iterations} iterations: {trials}"
            )

        final_strict_report = temp_dir / "final_strict.json"
        run(
            validator_command(args, blender, final_strict_report, expected_height=args.height),
            label="final strict GLB validation",
        )
        final_validation = json.loads(final_strict_report.read_text(encoding="utf-8"))

    report = dict(final_humanizer_report or {})
    final_import = final_validation["fresh_import"]
    report.update({
        "requested_anatomical_height_m": args.height,
        "final_requested_morphology_height_m": morphology_height,
        # The canonical height is measured from the freshly imported, deformed
        # body surface. Keep the legacy key but make both meanings explicit.
        "final_fresh_import_height_m": final_import["height_m"],
        "final_fresh_import_body_height_m": final_import["height_m"],
        "final_fresh_import_visual_height_m": final_import["visual_height_m"],
        "height_measurement_surface_index": final_import["height_surface_index"],
        "fresh_import_height_error_m": (
            final_import["height_m"] - args.height
        ),
        "height_tolerance_m": args.height_tolerance,
        "height_calibration_trials": trials,
        "strict_glb_validation": final_validation,
        "global_scale_used": False,
    })
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("HUMANIZER_PROXY_BUILD", json.dumps({
        "output": str(args.output.resolve()),
        "report": str(args.report.resolve()),
        "sex_label": report.get("sex_label"),
        "fresh_import_height_m": report["final_fresh_import_height_m"],
        "height_error_m": report["fresh_import_height_error_m"],
        "iterations": len(trials),
        "passed": final_validation["passed"],
    }))


if __name__ == "__main__":
    main()
