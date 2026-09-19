#!/usr/bin/env python3
"""Capture a coarse humanoid IK pose and write a Godot .gdpose document.

Images are processed with MediaPipe Pose when the optional dependencies are
installed.  A JSON landmark file can be used instead, which also provides a
stable interchange point for SAM 3D Body, ComfyUI, mocap, or another pose
estimator. The output is intentionally pose-category neutral: standing,
walking, running, sitting, lying, crouching, and carried poses use the same
control mapping.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import socket
import struct
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


LANDMARK_NAMES = (
    "nose", "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer", "left_ear",
    "right_ear", "mouth_left", "mouth_right", "left_shoulder",
    "right_shoulder", "left_elbow", "right_elbow", "left_wrist",
    "right_wrist", "left_pinky", "right_pinky", "left_index",
    "right_index", "left_thumb", "right_thumb", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle", "left_heel",
    "right_heel", "left_foot_index", "right_foot_index",
)

# SAM 3D Body exposes the first 70 MHR keypoints in this stable order. The
# adapter uses these anatomical points instead of depending on the private
# 308-joint MHR skeleton layout.
MHR70_NAMES = (
    "nose", "left-eye", "right-eye", "left-ear", "right-ear",
    "left-shoulder", "right-shoulder", "left-elbow", "right-elbow",
    "left-hip", "right-hip", "left-knee", "right-knee", "left-ankle",
    "right-ankle", "left-big-toe-tip", "left-small-toe-tip", "left-heel",
    "right-big-toe-tip", "right-small-toe-tip", "right-heel",
    "right-thumb-tip", "right-thumb-first-joint", "right-thumb-second-joint",
    "right-thumb-third-joint", "right-index-tip", "right-index-first-joint",
    "right-index-second-joint", "right-index-third-joint", "right-middle-tip",
    "right-middle-first-joint", "right-middle-second-joint",
    "right-middle-third-joint", "right-ring-tip", "right-ring-first-joint",
    "right-ring-second-joint", "right-ring-third-joint", "right-pinky-tip",
    "right-pinky-first-joint", "right-pinky-second-joint",
    "right-pinky-third-joint", "right-wrist", "left-thumb-tip",
    "left-thumb-first-joint", "left-thumb-second-joint", "left-thumb-third-joint",
    "left-index-tip", "left-index-first-joint", "left-index-second-joint",
    "left-index-third-joint", "left-middle-tip", "left-middle-first-joint",
    "left-middle-second-joint", "left-middle-third-joint", "left-ring-tip",
    "left-ring-first-joint", "left-ring-second-joint", "left-ring-third-joint",
    "left-pinky-tip", "left-pinky-first-joint", "left-pinky-second-joint",
    "left-pinky-third-joint", "left-wrist", "left-olecranon",
    "right-olecranon", "left-cubital-fossa", "right-cubital-fossa",
    "left-acromion", "right-acromion", "neck",
)

MHR_TO_LANDMARK = {
    "nose": "nose", "left-shoulder": "left_shoulder", "right-shoulder": "right_shoulder",
    "left-elbow": "left_elbow", "right-elbow": "right_elbow",
    "left-hip": "left_hip", "right-hip": "right_hip",
    "left-knee": "left_knee", "right-knee": "right_knee",
    "left-ankle": "left_ankle", "right-ankle": "right_ankle",
    "left-big-toe-tip": "left_foot_index", "right-big-toe-tip": "right_foot_index",
    "left-wrist": "left_wrist", "right-wrist": "right_wrist",
}

MODIFIERS = {
    "pelvis_control": True,
    "center_back_ik": True,
    "neck_ik": True,
    "r_leg": True,
    "l_leg": True,
    "r_arm": True,
    "l_arm": True,
    "head_look_at": False,
    "r_hand_copy_trans": False,
}


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    z: float
    confidence: float = 1.0

    def __add__(self, other: "Point") -> "Point":
        return Point(self.x + other.x, self.y + other.y, self.z + other.z,
                     min(self.confidence, other.confidence))

    def __sub__(self, other: "Point") -> "Point":
        return Point(self.x - other.x, self.y - other.y, self.z - other.z,
                     min(self.confidence, other.confidence))

    def scaled(self, value: float) -> "Point":
        return Point(self.x * value, self.y * value, self.z * value,
                     self.confidence)

    def values(self) -> list[float]:
        return [round(self.x, 6), round(self.y, 6), round(self.z, 6)]


def midpoint(a: Point, b: Point) -> Point:
    return (a + b).scaled(0.5)


def length(point: Point) -> float:
    return math.sqrt(point.x * point.x + point.y * point.y + point.z * point.z)


def pole(start: Point, joint: Point, end: Point, distance: float) -> Point:
    """Place a pole beyond the observed elbow/knee bend direction."""
    line_midpoint = midpoint(start, end)
    bend = joint - line_midpoint
    bend_length = length(bend)
    if bend_length < 1e-6:
        # Side-on and occluded limbs can appear perfectly straight.
        bend = Point(0.0, 0.0, 1.0)
        bend_length = 1.0
    return joint + bend.scaled(distance / bend_length)


def _point_from_value(value: object) -> Point:
    if isinstance(value, Mapping):
        return Point(float(value["x"]), float(value["y"]), float(value.get("z", 0.0)),
                     float(value.get("confidence", value.get("visibility", 1.0))))
    if isinstance(value, list) and len(value) >= 2:
        return Point(float(value[0]), float(value[1]),
                     float(value[2]) if len(value) > 2 else 0.0,
                     float(value[3]) if len(value) > 3 else 1.0)
    raise ValueError("landmark values must be objects or [x, y, z, confidence] arrays")


def load_landmark_json(path: Path) -> dict[str, Point]:
    data = json.loads(path.read_text(encoding="utf-8"))
    values = data.get("landmarks", data) if isinstance(data, dict) else data
    if isinstance(values, list):
        if len(values) != len(LANDMARK_NAMES):
            raise ValueError(f"expected {len(LANDMARK_NAMES)} ordered landmarks, got {len(values)}")
        return {name: _point_from_value(value) for name, value in zip(LANDMARK_NAMES, values)}
    if isinstance(values, dict):
        return {str(name).lower(): _point_from_value(value) for name, value in values.items()}
    raise ValueError("landmark JSON must contain a landmark object or a 33-item list")


def _first_output_record(data: object, index: int = 0) -> Mapping[str, object]:
    """Accept SAM output JSON saved as a record, list, or {outputs: [...]}.

    The official estimator returns a list of dictionaries. This permissive
    loader also accepts files exported from notebooks and ComfyUI.
    """
    if isinstance(data, Mapping):
        outputs = data.get("outputs")
        if isinstance(outputs, list) and outputs:
            if index < 0 or index >= len(outputs):
                raise ValueError(f"SAM 3D person index {index} is out of range (found {len(outputs)})")
            return _first_output_record(outputs[index])
        return data
    if isinstance(data, list) and data:
        if index < 0 or index >= len(data):
            raise ValueError(f"SAM 3D person index {index} is out of range (found {len(data)})")
        return _first_output_record(data[index])
    raise ValueError("SAM 3D JSON must contain an output record")


def _array_value(value: object) -> object:
    if isinstance(value, Mapping) and "data" in value:
        return value["data"]
    return value


def load_sam3d_json(path: Path, person_index: int = 0) -> dict[str, Point]:
    """Load SAM 3D Body's `pred_keypoints_3d`/MHR70 output."""
    data = json.loads(path.read_text(encoding="utf-8"))
    record = _first_output_record(data, person_index)
    raw = _array_value(record.get("pred_keypoints_3d", record.get("pred_joint_coords")))
    if not isinstance(raw, list) or len(raw) < len(MHR70_NAMES):
        raise ValueError("SAM 3D JSON needs a 70-point pred_keypoints_3d array")
    confidence = _array_value(record.get(
        "keypoint_confidence", record.get("pred_keypoints_3d_confidence", [])))
    points: dict[str, Point] = {}
    for index, mhr_name in enumerate(MHR70_NAMES):
        target_name = MHR_TO_LANDMARK.get(mhr_name)
        if target_name is None:
            continue
        point = _point_from_value(raw[index])
        score = point.confidence
        if isinstance(confidence, list) and index < len(confidence):
            score = float(confidence[index])
        points[target_name] = Point(point.x, point.y, point.z, score)
    if len(points) < 13:
        raise ValueError("SAM 3D JSON did not contain enough mapped MHR70 body points")
    return points


def estimate_mediapipe(path: Path, model_complexity: int) -> dict[str, Point]:
    try:
        import cv2  # type: ignore
        import mediapipe as mp  # type: ignore
    except ImportError as error:
        raise RuntimeError(
            "image input needs MediaPipe and OpenCV; install with "
            "'python3 -m pip install -r tools/requirements-image-pose.txt'"
        ) from error

    image = cv2.imread(str(path))
    if image is None:
        raise RuntimeError(f"could not read image: {path}")
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    try:
        pose_api = mp.solutions.pose
    except AttributeError as error:
        raise RuntimeError(
            "this MediaPipe build does not include mp.solutions.pose; use "
            "mediapipe==0.10.21 or provide a landmark JSON file"
        ) from error
    with pose_api.Pose(static_image_mode=True, model_complexity=model_complexity,
                       enable_segmentation=False) as estimator:
        result = estimator.process(image_rgb)
    landmarks = result.pose_world_landmarks or result.pose_landmarks
    if landmarks is None:
        raise RuntimeError("no person pose was detected in the image")
    return {
        name: Point(float(item.x), float(item.y), float(item.z),
                    float(getattr(item, "visibility", 1.0)))
        for name, item in zip(LANDMARK_NAMES, landmarks.landmark)
    }


def require_landmarks(points: Mapping[str, Point], names: Iterable[str], threshold: float) -> None:
    missing = [name for name in names if name not in points]
    uncertain = [name for name in names if name in points and points[name].confidence < threshold]
    if missing:
        raise ValueError("missing required landmarks: " + ", ".join(missing))
    if uncertain:
        print("warning: low-confidence landmarks: " + ", ".join(uncertain), file=sys.stderr)


def normalize_landmarks(points: Mapping[str, Point], height: float, floor_y: float,
                        mirror_x: bool, axis_mode: str = "mediapipe") -> dict[str, Point]:
    """Convert estimator coordinates to character-local Godot coordinates.

    MediaPipe world/image coordinates are treated as Y-down camera space;
    MHR keypoints are treated as Y-up body/world space.
    """
    left_hip, right_hip = points["left_hip"], points["right_hip"]
    hip = midpoint(left_hip, right_hip)
    head = points["nose"]
    feet = midpoint(points["left_ankle"], points["right_ankle"])
    measured_height = length(head - feet)
    if measured_height < 1e-5:
        raise ValueError("head and feet landmarks collapse to the same point")
    scale = height / measured_height
    sign_x = -1.0 if mirror_x else 1.0
    converted: dict[str, Point] = {}
    for name, value in points.items():
        relative = value - hip
        if axis_mode == "mhr":
            converted[name] = Point(sign_x * relative.x * scale,
                                    relative.y * scale,
                                    relative.z * scale,
                                    value.confidence)
        else:
            converted[name] = Point(sign_x * relative.x * scale,
                                    -relative.y * scale,
                                    -relative.z * scale,
                                    value.confidence)
    minimum_foot_y = min(converted["left_ankle"].y, converted["right_ankle"].y)
    y_offset = floor_y - minimum_foot_y
    return {name: Point(value.x, value.y + y_offset, value.z, value.confidence)
            for name, value in converted.items()}


def make_ik_pose(points: Mapping[str, Point], pole_distance: float,
                 confidence_threshold: float, source: str,
                 source_kind: str = "single_image_pose_estimate") -> dict[str, object]:
    required = (
        "nose", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
        "left_wrist", "right_wrist", "left_hip", "right_hip", "left_knee",
        "right_knee", "left_ankle", "right_ankle",
    )
    require_landmarks(points, required, confidence_threshold)
    hips = midpoint(points["left_hip"], points["right_hip"])
    shoulders = midpoint(points["left_shoulder"], points["right_shoulder"])

    left_foot = midpoint(points["left_ankle"], points.get("left_foot_index", points["left_ankle"]))
    right_foot = midpoint(points["right_ankle"], points.get("right_foot_index", points["right_ankle"]))
    controls = {
        "pelvis_target": {"position": hips.values()},
        # center_back_ik ends at UpperChest, so its target is the observed
        # shoulder center rather than the halfway point of the torso.
        "center_back_target": {"position": shoulders.values()},
        # neck_ik is a LookAtModifier3D: this value is a direction target, not
        # the neck's location. Aiming toward the nose gives the coarse head
        # direction and avoids folding the neck back toward the shoulders.
        "neck_target": {"position": points["nose"].values()},
        "head_target": {"position": points["nose"].values()},
        "l_arm_marker": {"position": points["left_wrist"].values()},
        "l_arm_pole": {"position": pole(points["left_shoulder"], points["left_elbow"],
                                                  points["left_wrist"], pole_distance).values()},
        "r_arm_marker": {"position": points["right_wrist"].values()},
        "r_arm_pole": {"position": pole(points["right_shoulder"], points["right_elbow"],
                                                  points["right_wrist"], pole_distance).values()},
        "l_feet_marker": {"position": left_foot.values()},
        "l_feet_pole": {"position": pole(points["left_hip"], points["left_knee"],
                                                   points["left_ankle"], pole_distance).values()},
        "r_feet_marker": {"position": right_foot.values()},
        "r_feet_pole": {"position": pole(points["right_hip"], points["right_knee"],
                                                   points["right_ankle"], pole_distance).values()},
    }
    return {
        "mode": "ik",
        "reset_to_rest": True,
        "modifiers": copy.deepcopy(MODIFIERS),
        "ik": controls,
        "bones": {},
        "source": {"kind": source_kind, "path": source},
    }


def quaternion_normalize(value: Iterable[float]) -> list[float]:
    quaternion = [float(item) for item in value]
    if len(quaternion) != 4:
        raise ValueError("a quaternion must contain four xyzw values")
    length = math.sqrt(sum(item * item for item in quaternion))
    if length < 1e-12:
        raise ValueError("cannot normalize a zero quaternion")
    return [item / length for item in quaternion]


def quaternion_multiply(a: Iterable[float], b: Iterable[float]) -> list[float]:
    ax, ay, az, aw = quaternion_normalize(a)
    bx, by, bz, bw = quaternion_normalize(b)
    return quaternion_normalize([
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    ])


def load_glb_rest_quaternion(path: Path, bone_name: str) -> list[float]:
    """Read one node's imported local rest quaternion from a binary glTF."""
    data = path.read_bytes()
    if data[:4] != b"glTF" or len(data) < 20:
        raise ValueError(f"not a binary glTF file: {path}")
    json_length, chunk_type = struct.unpack_from("<II", data, 12)
    if chunk_type != 0x4E4F534A:
        raise ValueError(f"first GLB chunk is not JSON: {path}")
    document = json.loads(data[20:20 + json_length].decode("utf-8"))
    skin_joints = {
        int(node_index)
        for skin in document.get("skins", [])
        for node_index in skin.get("joints", [])
    }
    for node_index in skin_joints:
        node = document.get("nodes", [])[node_index]
        if node.get("name") == bone_name:
            return quaternion_normalize(node.get("rotation", [0.0, 0.0, 0.0, 1.0]))
    raise ValueError(f"target GLB skin has no {bone_name!r} bone: {path}")


def apply_torso_roll(pose: dict[str, object], degrees: float,
                     hips_rest_quaternion: Iterable[float] | None = None) -> None:
    """Add an FK axial roll while retaining position-driven limb/body IK.

    A single-view keypoint skeleton identifies joint positions but cannot tell
    belly-up from belly-down. On this humanoid, local Hips +Y follows the long
    torso axis; a 180-degree local Y rotation flips a horizontal body without
    changing the pelvis-to-chest target line.
    """
    if abs(degrees) < 1e-6:
        return
    if hips_rest_quaternion is None:
        raise ValueError("torso roll requires the target GLB Hips rest quaternion")
    pose["mode"] = "hybrid"
    pose["rotation_space"] = "godot4_absolute_local_bone_pose"
    bones = pose.setdefault("bones", {})
    if not isinstance(bones, dict):
        raise ValueError("pose bones field is not an object")
    half_angle = math.radians(degrees) / 2.0
    local_roll = [0.0, math.sin(half_angle), 0.0, math.cos(half_angle)]
    desired_local = quaternion_multiply(hips_rest_quaternion, local_roll)
    bones["Hips"] = {
        "rotation_quaternion": [round(item, 8) for item in desired_local],
    }
    pose["orientation_hint"] = {
        "kind": "local_hips_axial_roll",
        "degrees": round(degrees, 6),
        "basis": "target_glb_rest_local",
    }


def force_pure_ik(pose: dict[str, object]) -> None:
    """Remove all FK orientation overrides and leave a target-only profile.

    A still image cannot reliably disambiguate the avatar's local torso roll.
    That correction belongs in the scene-level IK_character transform or in a
    later manual FK pass, not in an automatically generated profile. Keeping
    the generated result pure IK also means PoseControls remain editable after
    the profile is sent to Godot.
    """
    pose["mode"] = "ik"
    pose["bones"] = {}
    pose.pop("rotation_space", None)
    pose.pop("orientation_hint", None)


# Each generated control depends on one or more image landmarks.  When a
# detector reports an occluded joint with low visibility, omitting that control
# lets the template's carefully authored value remain in effect.
CONTROL_LANDMARKS: dict[str, tuple[str, ...]] = {
    "pelvis_target": ("left_hip", "right_hip"),
    "center_back_target": ("left_hip", "right_hip", "left_shoulder", "right_shoulder"),
    "neck_target": ("nose",),
    "head_target": ("nose",),
    "l_arm_marker": ("left_wrist",),
    "l_arm_pole": ("left_shoulder", "left_elbow", "left_wrist"),
    "r_arm_marker": ("right_wrist",),
    "r_arm_pole": ("right_shoulder", "right_elbow", "right_wrist"),
    "l_feet_marker": ("left_ankle",),
    "l_feet_pole": ("left_hip", "left_knee", "left_ankle"),
    "r_feet_marker": ("right_ankle",),
    "r_feet_pole": ("right_hip", "right_knee", "right_ankle"),
}

OCCLUSION_LANDMARK_NAMES = tuple(sorted({
    landmark
    for dependencies in CONTROL_LANDMARKS.values()
    for landmark in dependencies
}))


def mark_uncertain_landmarks(
    points: Mapping[str, Point], landmark_names: Iterable[str],
) -> dict[str, Point]:
    """Return points with explicit occlusions forced below any threshold.

    Official SAM 3D Body records do not always contain per-joint confidence.
    A reviewer can therefore mark visibly hidden, blended, or misassigned
    joints and make the converter retain the active template's controls.
    """
    result = dict(points)
    for name in landmark_names:
        if name not in result:
            raise ValueError(f"cannot mark absent landmark uncertain: {name}")
        point = result[name]
        result[name] = Point(point.x, point.y, point.z, 0.0)
    return result


def controls_affected_by_landmarks(landmark_names: Iterable[str]) -> list[str]:
    selected = set(landmark_names)
    return [
        control_name
        for control_name, dependencies in CONTROL_LANDMARKS.items()
        if selected.intersection(dependencies)
    ]


def retain_uncertain_template_controls(
    pose: dict[str, object], points: Mapping[str, Point],
    template_pose: Mapping[str, object] | None, threshold: float,
) -> list[str]:
    """Replace uncertain generated controls with the template values.

    Copying the fallback makes the named profile deterministic. Merely omitting
    the entry would make its result depend on whichever pose was applied first.
    """
    if template_pose is None:
        return []
    generated = pose.get("ik")
    fallback = template_pose.get("ik") if isinstance(template_pose, Mapping) else None
    if not isinstance(generated, dict) or not isinstance(fallback, Mapping):
        return []
    retained: list[str] = []
    for control_name, landmark_names in CONTROL_LANDMARKS.items():
        if control_name not in generated:
            continue
        if any(points.get(name, Point(0, 0, 0, 0)).confidence < threshold
               for name in landmark_names):
            if control_name in fallback:
                generated[control_name] = copy.deepcopy(fallback[control_name])
                retained.append(control_name)
    return retained


def write_json_atomic(path: Path, payload: object) -> None:
    """Write JSON beside the destination, then atomically replace it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=path.name + ".", suffix=".tmp", delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        temporary_path.chmod((path.stat().st_mode & 0o777) if path.exists() else 0o644)
        temporary_path.replace(path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def write_landmarks_json(path: Path, points: Mapping[str, Point]) -> None:
    payload = {"landmarks": {
        name: {"x": point.x, "y": point.y, "z": point.z,
               "confidence": point.confidence}
        for name, point in points.items()
    }}
    write_json_atomic(path, payload)


def write_debug_overlay(image_path: Path, output_path: Path,
                        points: Mapping[str, Point], threshold: float) -> None:
    """Write a simple diagnostic image; it is never used as pose input."""
    try:
        import cv2  # type: ignore
    except ImportError as error:
        raise RuntimeError("--debug-overlay needs OpenCV; install the image-pose requirements") from error
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"could not read image: {image_path}")
    height, width = image.shape[:2]
    for name, point in points.items():
        # MediaPipe x/y are normalized image coordinates; tolerate pixel input
        # in hand-authored JSON by only scaling values in the usual [0, 1] range.
        x = int(round(point.x * width if 0.0 <= point.x <= 1.0 else point.x))
        y = int(round(point.y * height if 0.0 <= point.y <= 1.0 else point.y))
        color = (0, 220, 0) if point.confidence >= threshold else (0, 80, 255)
        cv2.circle(image, (x, y), max(2, width // 160), color, -1)
        cv2.putText(image, name, (x + 3, y - 3), cv2.FONT_HERSHEY_SIMPLEX,
                    0.35, color, 1, cv2.LINE_AA)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), image):
        raise RuntimeError(f"could not write debug overlay: {output_path}")


def load_or_create_document(template: Path | None) -> dict[str, object]:
    if template:
        document = json.loads(template.read_text(encoding="utf-8"))
        if document.get("schema") != "godot-pose-document" or document.get("version") != 1:
            raise ValueError("template is not a godot-pose-document version 1 file")
        return document
    return {
        "schema": "godot-pose-document",
        "version": 1,
        "project_root": "..",
        "preview_scene": "res://demos/my_manual_rig_pose.tscn",
        "endpoint": {"host": "127.0.0.1", "port": 7007},
        "runtime_endpoint": {"host": "127.0.0.1", "port": 7008},
        "character": {
            "node_path": "IK_character",
            "skeleton_path": "Skeleton3D",
            "controls_path": "../PoseControls",
        },
        "poses": {},
    }


def install_pose(document: dict[str, object], name: str, pose: dict[str, object],
                 activate: bool) -> None:
    poses = document.setdefault("poses", {})
    if not isinstance(poses, dict):
        raise ValueError("document poses field is not an object")
    poses[name] = pose
    if activate or not document.get("active_pose"):
        document["active_pose"] = name


def send_pose(document: Mapping[str, object], pose_name: str, endpoint: str) -> dict[str, object]:
    host, separator, port_text = endpoint.rpartition(":")
    if not separator or not host:
        raise ValueError("--send must be HOST:PORT, for example 127.0.0.1:7007")
    poses = document["poses"]
    message = {
        "protocol": "godot-pose-stream",
        "version": 1,
        "type": "pose.apply",
        "request_id": "image-to-gdpose",
        "pose_name": pose_name,
        "character": document.get("character", {}),
        "pose": poses[pose_name],
    }
    with socket.create_connection((host, int(port_text)), timeout=3.0) as connection:
        stream = connection.makefile("rwb")
        stream.readline()  # Server hello.
        stream.write((json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8"))
        stream.flush()
        reply = stream.readline()
    if not reply:
        raise RuntimeError("Godot closed the pose stream without a response")
    return json.loads(reply)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path,
                        help="source image, MediaPipe landmark JSON, or SAM 3D/MHR JSON")
    parser.add_argument("--template", type=Path, help="existing .gdpose document to copy and extend")
    parser.add_argument("--output", type=Path, required=True, help="output .gdpose path")
    parser.add_argument("--pose-name", default="image_coarse_pose")
    parser.add_argument("--activate", action="store_true",
                        help="make the generated profile active (default preserves the template active_pose)")
    parser.add_argument("--height", type=float, default=1.70,
                        help="estimated nose-to-ankle height in Godot units (default: 1.70)")
    parser.add_argument("--floor-y", type=float, default=0.08,
                        help="lowest ankle height in character-local coordinates")
    parser.add_argument("--pole-distance", type=float, default=0.35)
    parser.add_argument("--confidence", type=float, default=0.35)
    parser.add_argument(
        "--uncertain", action="append", default=[], choices=OCCLUSION_LANDMARK_NAMES,
        metavar="LANDMARK",
        help=("mark one landmark as occluded/blended and retain every affected "
              "control from the active template pose; repeat for multiple joints"),
    )
    parser.add_argument("--mirror-x", action="store_true",
                        help="flip the estimated pose across the character X axis")
    parser.add_argument("--model-complexity", type=int, choices=(0, 1, 2), default=2)
    parser.add_argument("--format", choices=("auto", "mediapipe", "sam3d-mhr"), default="auto",
                        help="input estimator format; auto uses SAM 3D keys when present")
    parser.add_argument("--person-index", type=int, default=0,
                        help="SAM 3D output person to convert when JSON contains multiple records")
    parser.add_argument("--mhr-axis", choices=("mhr", "camera"), default="mhr",
                        help="SAM/MHR coordinate convention (default: Y-up MHR world coordinates)")
    parser.add_argument("--torso-roll-degrees", type=float, default=0.0,
                        help="local Hips Y roll; use 180 to change a horizontal body from belly-up to belly-down")
    parser.add_argument("--pure-ik", action="store_true",
                        help=("emit target-only IK with no FK bone overrides; "
                              "incompatible with --torso-roll-degrees"))
    parser.add_argument("--target-glb", type=Path,
                        help="exact Godot avatar GLB; required for nonzero torso roll")
    parser.add_argument("--send", metavar="HOST:PORT",
                        help="also apply the generated pose over the Godot pose stream")
    parser.add_argument("--landmarks-json", type=Path, metavar="PATH",
                        help="write detected, normalized landmarks for inspection or downstream tools")
    parser.add_argument("--debug-overlay", type=Path, metavar="PATH",
                        help="write an annotated copy of an image with detected landmarks")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        source_kind = "single_image_pose_estimate"
        axis_mode = "mediapipe"
        if args.input.suffix.lower() == ".json":
            raw_json = json.loads(args.input.read_text(encoding="utf-8"))
            looks_sam = False
            try:
                record = _first_output_record(raw_json)
                looks_sam = "pred_keypoints_3d" in record or "pred_joint_coords" in record
            except ValueError:
                pass
            use_sam = args.format == "sam3d-mhr" or (args.format == "auto" and looks_sam)
            if use_sam:
                raw_points = load_sam3d_json(args.input, args.person_index)
                source_kind = "sam3d_body_mhr70"
                axis_mode = "mhr" if args.mhr_axis == "mhr" else "mediapipe"
            else:
                raw_points = load_landmark_json(args.input)
        else:
            if args.format == "sam3d-mhr":
                raise ValueError("--format sam3d-mhr requires a SAM output JSON file")
            raw_points = estimate_mediapipe(args.input, args.model_complexity)
        raw_points = mark_uncertain_landmarks(raw_points, args.uncertain)
        normalized = normalize_landmarks(raw_points, args.height, args.floor_y,
                                         args.mirror_x, axis_mode)
        pose = make_ik_pose(normalized, args.pole_distance, args.confidence,
                            str(args.input), source_kind)
        if args.uncertain:
            source_metadata = pose.get("source")
            if isinstance(source_metadata, dict):
                source_metadata["uncertain_landmarks"] = sorted(set(args.uncertain))
        hips_rest = None
        if args.pure_ik and abs(args.torso_roll_degrees) >= 1e-6:
            raise ValueError("--pure-ik cannot be combined with --torso-roll-degrees; rotate IK_character in Godot instead")
        if abs(args.torso_roll_degrees) >= 1e-6:
            if args.target_glb is None:
                raise ValueError("--target-glb is required with --torso-roll-degrees")
            hips_rest = load_glb_rest_quaternion(args.target_glb, "Hips")
        apply_torso_roll(pose, args.torso_roll_degrees, hips_rest)
        if args.pure_ik:
            force_pure_ik(pose)
        document = load_or_create_document(args.template)
        template_pose = None
        if isinstance(document.get("poses"), dict):
            active_name = document.get("active_pose")
            candidate = document["poses"].get(active_name) if isinstance(active_name, str) else None
            template_pose = candidate if isinstance(candidate, Mapping) else None
        retained = retain_uncertain_template_controls(pose, normalized, template_pose, args.confidence)
        explicitly_affected = controls_affected_by_landmarks(args.uncertain)
        missing_fallbacks = [name for name in explicitly_affected if name not in retained]
        if missing_fallbacks:
            raise ValueError(
                "--uncertain needs an active template pose containing affected controls: "
                + ", ".join(missing_fallbacks)
            )
        if retained:
            pose["retained_template_controls"] = retained
        install_pose(document, args.pose_name, pose, args.activate)
        write_json_atomic(args.output, document)
        print(f"wrote coarse IK pose '{args.pose_name}' to {args.output}")
        if retained:
            print("retained template controls: " + ", ".join(retained))
        if args.landmarks_json:
            write_landmarks_json(args.landmarks_json, normalized)
        if args.debug_overlay:
            if args.input.suffix.lower() == ".json":
                raise ValueError("--debug-overlay requires an image input, not landmark JSON")
            write_debug_overlay(args.input, args.debug_overlay, raw_points, args.confidence)
        if args.send:
            reply = send_pose(document, args.pose_name, args.send)
            print("Godot reply: " + json.dumps(reply, ensure_ascii=False))
            if reply.get("type") == "error":
                return 2
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"image_to_gdpose: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
