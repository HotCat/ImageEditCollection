#!/usr/bin/env python3
"""Render fresh-import rest, run, and head-turn QA for a humanoid GLB.

Run in Blender with --factory-startup. The script deliberately imports the GLB
from disk rather than opening the authoring Blend: export/import transform and
attachment bugs often remain invisible in the source scene. Renders are evidence
for a human/agent visual decision; this script never auto-declares visual success.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=768)
    parser.add_argument("--head-yaw", type=float, default=40.0)
    return parser.parse_args(argv)


def point_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def find_action(fragment: str):
    fragment = fragment.lower()
    return next((action for action in bpy.data.actions if fragment in action.name.lower()), None)


def reset_pose(rig):
    rig.animation_data_clear()
    for bone in rig.pose.bones:
        bone.rotation_mode = "QUATERNION"
        bone.rotation_quaternion.identity()
        bone.location = (0.0, 0.0, 0.0)
        bone.scale = (1.0, 1.0, 1.0)
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()


def apply_action(rig, action):
    reset_pose(rig)
    rig.animation_data_create()
    rig.animation_data.action = action
    start, end = action.frame_range
    bpy.context.scene.frame_set(round((start + end) * 0.5))
    bpy.context.view_layer.update()


def apply_head_turn(rig, degrees):
    reset_pose(rig)
    head = rig.pose.bones.get("Head") or rig.pose.bones.get("head")
    if head is None:
        raise RuntimeError("Imported skeleton has no Head/head bone")
    # The retargeted Humanizer skeleton rotates left/right around local Y after
    # glTF re-import. The rendered test catches eyes/hair that fail to follow it.
    head.rotation_mode = "XYZ"
    head.rotation_euler.y = math.radians(degrees)
    bpy.context.view_layer.update()


def setup_scene(output_dir: Path, resolution: int, character_height: float):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = round(resolution * 1.5)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.028, 0.030, 0.038)

    target_z = character_height * 0.50
    camera_data = bpy.data.cameras.new("Proxy_QA_Camera")
    camera_data.lens = 58
    camera = bpy.data.objects.new("Proxy_QA_Camera", camera_data)
    camera.location = (0.0, -character_height * 1.75, target_z)
    point_at(camera, (0.0, 0.0, target_z))
    bpy.context.collection.objects.link(camera)
    scene.camera = camera

    for name, location, energy, size in [
        ("QA_Key", (-2.2, -2.4, 3.0), 1100, 2.0),
        ("QA_Fill", (2.1, -1.6, 2.0), 650, 2.5),
        ("QA_Rim", (0.2, 2.0, 2.7), 900, 1.5),
    ]:
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size = energy, "DISK", size
        light = bpy.data.objects.new(name, data)
        light.location = location
        point_at(light, (0.0, 0.0, target_z))
        bpy.context.collection.objects.link(light)

    bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 0, -0.02))
    floor = bpy.context.object
    floor.name = "QA_Floor"
    material = bpy.data.materials.new("QA_Floor_Material")
    material.diffuse_color = (0.10, 0.11, 0.14, 1.0)
    floor.data.materials.append(material)
    output_dir.mkdir(parents=True, exist_ok=True)
    return camera


def render(path: Path):
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main():
    args = parse_args()
    if not args.glb.is_file():
        raise SystemExit(f"GLB does not exist: {args.glb}")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(args.glb))

    payload = [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH" and obj.name != "Icosphere"
    ]
    rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if len(payload) != 1:
        raise SystemExit(
            f"Expected one combined payload mesh for portable head attachments; got {len(payload)}"
        )
    if len(rigs) != 1:
        raise SystemExit(f"Expected one armature; got {len(rigs)}")
    rig = rigs[0]
    points = [payload[0].matrix_world @ Vector(corner) for corner in payload[0].bound_box]
    height = max(point.z for point in points) - min(point.z for point in points)
    setup_scene(args.output_dir, args.resolution, height)

    rest_path = args.output_dir / "rest_front.png"
    reset_pose(rig)
    render(rest_path)

    run_path = args.output_dir / "run_front.png"
    run_action = find_action("run")
    if run_action is None:
        raise SystemExit("GLB contains no Run animation for deformation QA")
    apply_action(rig, run_action)
    render(run_path)

    head_path = args.output_dir / "head_turn_front.png"
    apply_head_turn(rig, args.head_yaw)
    render(head_path)

    report = {
        "glb": str(args.glb.resolve()),
        "payload_mesh_count": len(payload),
        "payload_mesh": payload[0].name,
        "armature": rig.name,
        "bone_count": len(rig.data.bones),
        "actions": sorted(action.name for action in bpy.data.actions),
        "head_yaw_degrees": args.head_yaw,
        "renders": {
            "rest": str(rest_path),
            "run": str(run_path),
            "head_turn": str(head_path),
        },
        "visual_review": "pending",
        "review_requirements": [
            "eyes, eyebrows, eyelashes, scalp hair, and hair tail remain on the head",
            "shoulders, elbows, hips, thighs, knees, ankles, and feet do not collapse in Run",
            "no body surface is replaced by helper geometry",
        ],
    }
    report_path = args.output_dir / "deformation_qa.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PROXY_DEFORMATION_QA", json.dumps(report))


if __name__ == "__main__":
    main()
