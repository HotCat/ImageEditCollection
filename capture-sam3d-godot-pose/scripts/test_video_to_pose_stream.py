#!/usr/bin/env python3
"""Checkpoint-free regression tests for the video solver and wire format."""

from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import video_to_pose_stream as mocap  # noqa: E402


def axis_angle(axis: tuple[float, float, float], degrees: float) -> np.ndarray:
    direction = np.asarray(axis, dtype=np.float64)
    direction /= np.linalg.norm(direction)
    half = math.radians(degrees) / 2.0
    return np.concatenate((direction * math.sin(half), [math.cos(half)]))


class QuaternionTests(unittest.TestCase):
    def test_matrix_round_trip_and_slerp_are_normalized(self) -> None:
        source = mocap.quat_normalize(np.array([0.2, -0.3, 0.1, 0.9]))
        rebuilt = mocap.matrix_to_quat(mocap.quat_to_matrix(source))
        self.assertAlmostEqual(abs(float(np.dot(source, rebuilt))), 1.0, places=7)
        halfway = mocap.quat_slerp(np.array([0.0, 0.0, 0.0, 1.0]), source, 0.5)
        self.assertAlmostEqual(float(np.linalg.norm(halfway)), 1.0, places=7)

    def test_hemisphere_continuity_removes_equivalent_sign_flip(self) -> None:
        value = mocap.quat_normalize(np.array([0.1, 0.2, 0.3, 0.9]))
        filtered = mocap.temporal_quaternion_filter(
            np.asarray([value, -value, value]), responsiveness=1.0,
        )
        self.assertGreater(float(np.dot(filtered[0], filtered[1])), 0.999999)
        self.assertGreater(float(np.dot(filtered[1], filtered[2])), 0.999999)


class AbsoluteLocalRotationTests(unittest.TestCase):
    def setUp(self) -> None:
        hips_rest = axis_angle((1.0, 0.0, 0.0), 37.0)
        child_rest = axis_angle((0.0, 0.0, 1.0), -28.0)
        self.rig = mocap.Rig(
            names=["Hips", "AccessoryRoll"],
            parents=np.asarray([-1, 0], dtype=np.int32),
            translations=np.asarray([[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
            rest_local=np.asarray([hips_rest, child_rest]),
            rest_global=np.asarray([hips_rest, mocap.quat_multiply(hips_rest, child_rest)]),
        )

    def test_fitted_root_is_sent_as_absolute_local_not_rest_delta(self) -> None:
        desired = axis_angle((0.0, 1.0, 0.0), 61.0)
        fitted, _ = mocap.fit_hierarchical_pose(
            self.rig,
            {"Hips": np.asarray([desired])},
            [],
            np.empty((1, 0, 3)),
            np.empty((1, 0)),
            1.0,
        )
        self.assertAlmostEqual(abs(float(np.dot(fitted["Hips"][0], desired))), 1.0, places=7)
        legacy_delta = mocap.quat_multiply(
            mocap.quat_conjugate(self.rig.rest_local[0]), desired,
        )
        self.assertLess(abs(float(np.dot(fitted["Hips"][0], legacy_delta))), 0.99)

    def test_unobserved_bone_keeps_nonidentity_rest_quaternion(self) -> None:
        fitted, driven = mocap.fit_hierarchical_pose(
            self.rig,
            {},
            [],
            np.empty((1, 0, 3)),
            np.empty((1, 0)),
            1.0,
        )
        self.assertNotIn("AccessoryRoll", driven)
        np.testing.assert_allclose(fitted["AccessoryRoll"][0], self.rig.rest_local[1])
        self.assertFalse(np.allclose(fitted["AccessoryRoll"][0], [0.0, 0.0, 0.0, 1.0]))


class ProtocolTests(unittest.TestCase):
    def test_pose_frame_declares_absolute_local_xyzw(self) -> None:
        message = mocap.make_pose_frame(
            {"Hips": [0.0, 0.0, 0.0, 1.0]}, 7, "Actor", "Skeleton3D",
            "../PoseControls", "/tmp/input.mp4", True,
        )
        decoded = json.loads(json.dumps(message))
        self.assertEqual(decoded["type"], "pose.frame")
        self.assertEqual(decoded["pose"]["rotation_space"], mocap.ROTATION_SPACE)
        self.assertEqual(
            decoded["pose"]["bones"]["Hips"]["rotation_quaternion"],
            [0.0, 0.0, 0.0, 1.0],
        )

    def test_cache_rejects_legacy_or_unlabelled_delta_space(self) -> None:
        cache = {
            "schema": "godot-pose-motion-cache",
            "version": 1,
            "bone_count": 1,
            "frames": [{"Hips": [0.0, 0.0, 0.0, 1.0]}],
        }
        with self.assertRaisesRegex(ValueError, "absolute-local"):
            mocap.validate_motion_cache(cache)
        cache["rotation_space"] = mocap.ROTATION_SPACE
        mocap.validate_motion_cache(cache)


if __name__ == "__main__":
    unittest.main()
