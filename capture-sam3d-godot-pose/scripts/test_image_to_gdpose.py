import importlib.util
import json
import math
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("image_to_gdpose", SCRIPT_DIR / "image_to_gdpose.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
import sys
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ImageToGdposeTests(unittest.TestCase):
    def points(self):
        Point = MODULE.Point
        return {
            "nose": Point(0.0, -0.8, 0.0),
            "left_shoulder": Point(-0.2, -0.5, 0.0),
            "right_shoulder": Point(0.2, -0.5, 0.0),
            "left_elbow": Point(-0.35, -0.25, 0.1),
            "right_elbow": Point(0.35, -0.25, 0.1),
            "left_wrist": Point(-0.45, 0.0, 0.2),
            "right_wrist": Point(0.45, 0.0, 0.2),
            "left_hip": Point(-0.12, 0.0, 0.0),
            "right_hip": Point(0.12, 0.0, 0.0),
            "left_knee": Point(-0.13, 0.45, 0.1),
            "right_knee": Point(0.13, 0.45, 0.1),
            "left_ankle": Point(-0.14, 0.9, 0.0),
            "right_ankle": Point(0.14, 0.9, 0.0),
            "left_foot_index": Point(-0.14, 0.95, -0.12),
            "right_foot_index": Point(0.14, 0.95, -0.12),
        }

    def test_pose_contains_project_control_names(self):
        normalized = MODULE.normalize_landmarks(self.points(), 1.7, 0.08, False)
        pose = MODULE.make_ik_pose(normalized, 0.35, 0.35, "test.json")
        self.assertEqual(pose["mode"], "ik")
        self.assertEqual(set(pose["ik"]), {
            "pelvis_target", "center_back_target", "neck_target", "head_target",
            "l_arm_marker", "l_arm_pole", "r_arm_marker", "r_arm_pole",
            "l_feet_marker", "l_feet_pole", "r_feet_marker", "r_feet_pole",
        })
        self.assertAlmostEqual(min(normalized["left_ankle"].y,
                                   normalized["right_ankle"].y), 0.08)
        self.assertEqual(pose["ik"]["center_back_target"]["position"],
                         MODULE.midpoint(normalized["left_shoulder"],
                                         normalized["right_shoulder"]).values())
        self.assertEqual(pose["ik"]["neck_target"]["position"],
                         normalized["nose"].values())

    def test_torso_roll_produces_hybrid_hips_orientation(self):
        normalized = MODULE.normalize_landmarks(self.points(), 1.7, 0.08, False)
        pose = MODULE.make_ik_pose(normalized, 0.35, 0.35, "test.json")
        MODULE.apply_torso_roll(pose, 180.0)
        self.assertEqual(pose["mode"], "hybrid")
        self.assertEqual(pose["bones"], {
            "Hips": {"rotation_degrees": [0.0, 180.0, 0.0]},
        })
        self.assertEqual(pose["orientation_hint"]["kind"], "local_hips_axial_roll")

    def test_cli_writes_valid_document_from_landmark_json(self):
        serialized = {name: [point.x, point.y, point.z, point.confidence]
                      for name, point in self.points().items()}
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "landmarks.json"
            output = Path(directory) / "coarse.gdpose"
            source.write_text(json.dumps({"landmarks": serialized}), encoding="utf-8")
            result = MODULE.main([str(source), "--output", str(output),
                                  "--pose-name", "photo_pose"])
            self.assertEqual(result, 0)
            document = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(document["schema"], "godot-pose-document")
            self.assertEqual(document["active_pose"], "photo_pose")
            self.assertIn("photo_pose", document["poses"])

    def test_template_active_pose_is_preserved_unless_requested(self):
        serialized = {name: [point.x, point.y, point.z, point.confidence]
                      for name, point in self.points().items()}
        template = {
            "schema": "godot-pose-document", "version": 1,
            "active_pose": "keep_me", "poses": {
                "keep_me": {"mode": "ik", "ik": {
                    "r_arm_marker": {"position": [1, 2, 3]},
                }}
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "landmarks.json"
            template_path = Path(directory) / "template.gdpose"
            output = Path(directory) / "coarse.gdpose"
            source.write_text(json.dumps({"landmarks": serialized}), encoding="utf-8")
            template_path.write_text(json.dumps(template), encoding="utf-8")
            self.assertEqual(MODULE.main([str(source), "--template", str(template_path),
                                          "--output", str(output), "--pose-name", "photo"]), 0)
            document = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(document["active_pose"], "keep_me")
            self.assertIn("photo", document["poses"])
            self.assertEqual(MODULE.main([str(source), "--template", str(template_path),
                                          "--output", str(output), "--pose-name", "photo",
                                          "--activate"]), 0)
            document = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(document["active_pose"], "photo")

    def test_uncertain_control_copies_template_value(self):
        points = self.points()
        Point = MODULE.Point
        points["left_wrist"] = Point(-0.45, 0.0, 0.2, 0.1)
        normalized = MODULE.normalize_landmarks(points, 1.7, 0.08, False)
        pose = MODULE.make_ik_pose(normalized, 0.35, 0.35, "test.json")
        fallback = {"ik": {
            "l_arm_marker": {"position": [9.0, 8.0, 7.0]},
            "l_arm_pole": {"position": [6.0, 5.0, 4.0]},
        }}
        retained = MODULE.retain_uncertain_template_controls(
            pose, normalized, fallback, 0.35,
        )
        self.assertEqual(retained, ["l_arm_marker", "l_arm_pole"])
        self.assertEqual(pose["ik"]["l_arm_marker"], fallback["ik"]["l_arm_marker"])
        self.assertEqual(pose["ik"]["l_arm_pole"], fallback["ik"]["l_arm_pole"])

    def test_explicit_uncertain_landmark_forces_template_fallback(self):
        points = MODULE.mark_uncertain_landmarks(self.points(), ["right_wrist"])
        self.assertEqual(points["right_wrist"].confidence, 0.0)
        normalized = MODULE.normalize_landmarks(points, 1.7, 0.08, False)
        pose = MODULE.make_ik_pose(normalized, 0.35, 0.35, "test.json")
        fallback = {"ik": {
            "r_arm_marker": {"position": [1.0, 2.0, 3.0]},
            "r_arm_pole": {"position": [4.0, 5.0, 6.0]},
        }}
        retained = MODULE.retain_uncertain_template_controls(
            pose, normalized, fallback, 0.35,
        )
        self.assertEqual(retained, ["r_arm_marker", "r_arm_pole"])
        self.assertEqual(
            MODULE.controls_affected_by_landmarks(["right_wrist"]),
            ["r_arm_marker", "r_arm_pole"],
        )

    def test_cli_rejects_explicit_occlusion_without_complete_template(self):
        serialized = {name: [point.x, point.y, point.z, point.confidence]
                      for name, point in self.points().items()}
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "landmarks.json"
            output = Path(directory) / "coarse.gdpose"
            source.write_text(json.dumps({"landmarks": serialized}), encoding="utf-8")
            result = MODULE.main([
                str(source), "--output", str(output),
                "--uncertain", "left_wrist",
            ])
            self.assertEqual(result, 1)

    def test_pose_mapping_accepts_standing_sitting_and_lying_geometry(self):
        Point = MODULE.Point
        sitting = self.points()
        sitting.update({
            "left_knee": Point(-0.13, 0.15, -0.40),
            "right_knee": Point(0.13, 0.15, -0.40),
            "left_ankle": Point(-0.14, 0.65, -0.42),
            "right_ankle": Point(0.14, 0.65, -0.42),
        })
        lying = {
            name: Point(-point.y, point.x, point.z, point.confidence)
            for name, point in self.points().items()
        }
        for label, points in (("standing", self.points()),
                              ("sitting", sitting), ("lying", lying)):
            with self.subTest(pose=label):
                normalized = MODULE.normalize_landmarks(points, 1.7, 0.08, False)
                pose = MODULE.make_ik_pose(normalized, 0.35, 0.35, f"{label}.json")
                self.assertEqual(len(pose["ik"]), 12)
                for control in pose["ik"].values():
                    self.assertTrue(all(math.isfinite(value)
                                        for value in control["position"]))

    def test_sam3d_mhr70_json_maps_to_project_controls(self):
        points = []
        for index, name in enumerate(MODULE.MHR70_NAMES):
            # A deterministic upright MHR-like skeleton. The adapter only
            # needs the 13 mapped body points, but accepts the full 70 array.
            points.append([0.01 * index, 0.02 * index, 0.0])
        indices = {name: MODULE.MHR70_NAMES.index(name) for name in (
            "nose", "left-shoulder", "right-shoulder", "left-elbow", "right-elbow",
            "left-hip", "right-hip", "left-knee", "right-knee", "left-ankle",
            "right-ankle", "left-wrist", "right-wrist")}
        # Make the required points geometrically non-degenerate.
        for name, idx in indices.items():
            x = -0.2 if name.startswith("left-") else 0.2 if name.startswith("right-") else 0.0
            y = {"nose": -0.9, "left-shoulder": -0.55, "right-shoulder": -0.55,
                 "left-elbow": -0.3, "right-elbow": -0.3, "left-wrist": -0.1,
                 "right-wrist": -0.1, "left-hip": 0.0, "right-hip": 0.0,
                 "left-knee": 0.45, "right-knee": 0.45, "left-ankle": 0.9,
                 "right-ankle": 0.9}[name]
            points[idx] = [x, y, 0.0]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sam-output.json"
            output = Path(directory) / "coarse.gdpose"
            source.write_text(json.dumps([{"pred_keypoints_3d": points}]), encoding="utf-8")
            result = MODULE.main([str(source), "--format", "sam3d-mhr",
                                  "--output", str(output), "--pose-name", "mhr_pose",
                                  "--torso-roll-degrees", "180"])
            self.assertEqual(result, 0)
            document = json.loads(output.read_text(encoding="utf-8"))
            pose = document["poses"]["mhr_pose"]
            self.assertEqual(pose["source"]["kind"], "sam3d_body_mhr70")
            self.assertEqual(pose["mode"], "hybrid")
            self.assertEqual(pose["bones"]["Hips"]["rotation_degrees"],
                             [0.0, 180.0, 0.0])
            self.assertEqual(set(pose["ik"]), {
                "pelvis_target", "center_back_target", "neck_target", "head_target",
                "l_arm_marker", "l_arm_pole", "r_arm_marker", "r_arm_pole",
                "l_feet_marker", "l_feet_pole", "r_feet_marker", "r_feet_pole",
            })


if __name__ == "__main__":
    unittest.main()
