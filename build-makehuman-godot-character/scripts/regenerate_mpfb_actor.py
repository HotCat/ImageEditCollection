#!/usr/bin/env python3
"""Build a fitted MPFB human, game-engine rig, editable preset and GLB.

Run inside Blender with MPFB enabled. This script intentionally builds a clean
neutral realtime proxy. Experimental identity texture projection is a separate
stage and must never overwrite this proxy.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def blender_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--actor-id", default="actor")
    parser.add_argument("--height", type=float, required=True, help="Visible body height in metres")
    parser.add_argument("--config", type=Path, required=True,
                        help="JSON with macro values and detail_targets")
    parser.add_argument("--rig", default="game_engine")
    parser.add_argument("--views", type=int, default=6)
    parser.add_argument("--resolution", type=int, default=768)
    parser.add_argument("--export-scale", type=float,
                        help="Optional explicit rig-root correction; otherwise calibrate by GLB re-import")
    return parser.parse_args(argv)


def dynamic_import(suffix: str, symbol: str):
    for module_name in list(sys.modules):
        if module_name.endswith(suffix):
            module = importlib.import_module(module_name)
            if hasattr(module, symbol):
                return getattr(module, symbol)
    raise RuntimeError(
        "MPFB is not enabled in this Blender process. Enable the MPFB extension/add-on, "
        "restart Blender, and run without --factory-startup if that disables extensions."
    )


def services():
    return (
        dynamic_import("mpfb.services.humanservice", "HumanService"),
        dynamic_import("mpfb.services.targetservice", "TargetService"),
        dynamic_import("mpfb.services.locationservice", "LocationService"),
        dynamic_import("mpfb.entities.objectproperties", "HumanObjectProperties"),
    )


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def group_member_indices(obj, group_name: str) -> list[int]:
    group = obj.vertex_groups.get(group_name)
    if group is None:
        raise RuntimeError(f"MPFB basemesh is missing required vertex group: {group_name}")
    return [
        vertex.index for vertex in obj.data.vertices
        if any(item.group == group.index and item.weight > 0.01 for item in vertex.groups)
    ]


def evaluated_group_bounds(obj, group_name: str):
    members = group_member_indices(obj, group_name)
    mask_states = []
    for modifier in obj.modifiers:
        if modifier.type == "MASK":
            mask_states.append((modifier, modifier.show_viewport, modifier.show_render))
            modifier.show_viewport = False
            modifier.show_render = False
    bpy.context.view_layer.update()
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        points = [evaluated.matrix_world @ mesh.vertices[index].co for index in members]
    finally:
        evaluated.to_mesh_clear()
        for modifier, viewport, render in mask_states:
            modifier.show_viewport, modifier.show_render = viewport, render
        bpy.context.view_layer.update()
    if not points:
        raise RuntimeError(f"No evaluated vertices in {group_name!r}")
    return (
        [min(point[axis] for point in points) for axis in range(3)],
        [max(point[axis] for point in points) for axis in range(3)],
    )


def visible_height(obj) -> float:
    minimum, maximum = evaluated_group_bounds(obj, "body")
    return maximum[2] - minimum[2]


def fit_height(obj, target: float, target_service, object_properties):
    low, high = 0.0, 1.0
    trials = []
    for _ in range(16):
        value = (low + high) / 2.0
        object_properties.set_value("height", value, entity_reference=obj)
        target_service.reapply_macro_details(obj)
        measured = visible_height(obj)
        trials.append({"macro": value, "height_m": measured})
        if measured < target:
            low = value
        else:
            high = value
    best = min(trials, key=lambda item: abs(item["height_m"] - target))
    object_properties.set_value("height", best["macro"], entity_reference=obj)
    target_service.reapply_macro_details(obj)
    return best, trials


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config.get("macro", {}), dict):
        raise ValueError("config.macro must be an object")
    if not isinstance(config.get("detail_targets", []), list):
        raise ValueError("config.detail_targets must be a list")
    return config


def apply_macro(base: dict, supplied: dict) -> dict:
    result = dict(base)
    race = supplied.get("race")
    for key, value in supplied.items():
        if key != "race":
            result[key] = float(value)
    if race:
        result["race"] = {key: float(value) for key, value in race.items()}
    return result


def load_detail(obj, item: dict, target_service, location_service):
    relative = item["target"]
    root = location_service.get_mpfb_data("targets")
    path = os.path.join(root, relative + ".target.gz")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Unknown MPFB detail target: {path}")
    target_service.load_target(obj, path, weight=float(item["weight"]))


def neutral_material(body, color):
    material = bpy.data.materials.new("Neutral_Realtime_Skin")
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = tuple(color)
    bsdf.inputs["Roughness"].default_value = 0.55
    body.data.materials.clear()
    body.data.materials.append(material)
    for polygon in body.data.polygons:
        polygon.material_index = 0


def setup_render(output: Path, resolution: int):
    world = bpy.context.scene.world
    world.color = (0.025, 0.025, 0.025)
    for name, location, energy, size in [
        ("Key", (-2.5, -3.5, 2.5), 850, 3.5),
        ("Fill", (2.8, -2.0, 1.7), 500, 3.0),
        ("Rim", (0.0, 2.5, 2.2), 600, 2.5),
    ]:
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size = energy, "DISK", size
        light = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(light)
        light.location = location
        light.rotation_euler = (-light.location).to_track_quat("-Z", "Y").to_euler()
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = int(round(resolution * 4 / 3))
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    output.mkdir(parents=True, exist_ok=True)


def render_turntable(body, output: Path, count: int, resolution: int):
    setup_render(output, resolution)
    minimum, maximum = evaluated_group_bounds(body, "body")
    center = Vector((0.0, 0.0, (minimum[2] + maximum[2]) / 2.0))
    camera_data = bpy.data.cameras.new("QA_Camera")
    camera = bpy.data.objects.new("QA_Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = (maximum[2] - minimum[2]) * 1.10
    bpy.context.scene.camera = camera
    for index in range(count):
        angle = index * 360.0 / count
        radians = math.radians(angle)
        camera.location = Vector((4.0 * math.sin(radians), -4.0 * math.cos(radians), center.z))
        camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
        path = output / f"azimuth_{round(angle):03d}.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)


def select_export(objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[-1]


def export_glb(path: Path, body, rig):
    for pose_bone in rig.pose.bones:
        pose_bone.custom_shape = None
    select_export([body, rig])
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format="GLB", use_selection=True,
        export_skins=True, export_animations=False, export_apply=False,
    )


def imported_bounds(glb: Path) -> tuple[float, dict]:
    clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(glb))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    # Blender may generate editor display helpers during import; the raw GLB
    # inspection below decides whether they are actual payload geometry.
    payload = [obj for obj in meshes if obj.name not in {"Icosphere"}]
    points = [obj.matrix_world @ Vector(corner) for obj in payload for corner in obj.bound_box]
    if not points:
        raise RuntimeError("No character meshes found after GLB re-import")
    minimum = [min(point[axis] for point in points) for axis in range(3)]
    maximum = [max(point[axis] for point in points) for axis in range(3)]
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    return maximum[2] - minimum[2], {
        "bounds_min": minimum, "bounds_max": maximum,
        "meshes": [obj.name for obj in meshes],
        "armatures": [obj.name for obj in armatures],
        "bone_counts": {obj.name: len(obj.data.bones) for obj in armatures},
    }


def raw_glb(glb: Path) -> dict:
    with glb.open("rb") as handle:
        magic, version, total = struct.unpack("<4sII", handle.read(12))
        length, kind = struct.unpack("<II", handle.read(8))
        doc = json.loads(handle.read(length).decode("utf-8").rstrip("\x00 "))
    names = [node.get("name", "") for node in doc.get("nodes", [])]
    meshes = [mesh.get("name", "") for mesh in doc.get("meshes", [])]
    return {
        "magic": magic.decode("ascii"), "version": version, "declared_length": total,
        "node_count": len(names), "mesh_count": len(meshes),
        "contains_icosphere": "Icosphere" in names or "Icosphere" in meshes,
    }


def main():
    args = blender_args()
    if args.height <= 0.5 or args.height >= 2.6:
        raise SystemExit("--height must be a plausible human height in metres (0.5 to 2.6)")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    config = load_config(args.config)
    human_service, target_service, location_service, object_properties = services()
    clear_scene()
    macro = apply_macro(target_service.get_default_macro_info_dict(), config.get("macro", {}))
    body = human_service.create_human(
        mask_helpers=True, detailed_helpers=True, extra_vertex_groups=True,
        feet_on_ground=True, scale=0.1, macro_detail_dict=macro,
    )
    body.name = f"{args.actor_id}_Basemesh"
    initial_best, initial_trials = fit_height(body, args.height, target_service, object_properties)
    for item in config.get("detail_targets", []):
        load_detail(body, item, target_service, location_service)
    final_best, final_trials = fit_height(body, args.height, target_service, object_properties)
    rig = human_service.add_builtin_rig(body, args.rig, import_weights=True)
    rig.name = f"{args.actor_id}_{args.rig}"
    native_rig_bones = len(rig.data.bones)
    native_vertices = len(body.data.vertices)
    native_faces = len(body.data.polygons)
    color = config.get("neutral_skin_rgba", [0.46, 0.27, 0.19, 1.0])
    neutral_material(body, color)
    render_turntable(body, args.output_dir / "proxy_turntable", args.views, args.resolution)

    preset = args.output_dir / f"human.{args.actor_id}.json"
    human_service.serialize_to_json_file(body, str(preset), save_clothes=True)
    blend = args.output_dir / f"{args.actor_id}_realtime_proxy.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    probe = args.output_dir / f".{args.actor_id}_probe.glb"
    export_glb(probe, body, rig)
    imported_height, first_import = imported_bounds(probe)
    correction = args.export_scale if args.export_scale is not None else args.height / imported_height

    bpy.ops.wm.open_mainfile(filepath=str(blend))
    body = bpy.data.objects[f"{args.actor_id}_Basemesh"]
    rig = bpy.data.objects[f"{args.actor_id}_{args.rig}"]
    rig.scale = (correction, correction, correction)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    glb = args.output_dir / f"{args.actor_id}_realtime_proxy.glb"
    export_glb(glb, body, rig)
    final_imported_height, final_import = imported_bounds(glb)
    probe.unlink(missing_ok=True)

    report = {
        "actor_id": args.actor_id,
        "config": str(args.config.resolve()),
        "target_height_m": args.height,
        "native_visible_height_m": final_best["height_m"],
        "probe_import_height_m": imported_height,
        "glb_root_export_scale": correction,
        "final_import_height_m": final_imported_height,
        "height_error_m": final_imported_height - args.height,
        "rig": args.rig,
        "rig_bones": native_rig_bones,
        "vertices": native_vertices,
        "faces": native_faces,
        "initial_height_fit": initial_best,
        "final_height_fit": final_best,
        "initial_height_trials": initial_trials,
        "final_height_trials": final_trials,
        "detail_targets": config.get("detail_targets", []),
        "first_import": first_import,
        "final_import": final_import,
        "raw_glb": raw_glb(glb),
        "preset": str(preset), "blend": str(blend), "glb": str(glb),
    }
    report_path = args.output_dir / f"{args.actor_id}_build_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("MPFB_BUILD_REPORT", json.dumps(report))


if __name__ == "__main__":
    main()
