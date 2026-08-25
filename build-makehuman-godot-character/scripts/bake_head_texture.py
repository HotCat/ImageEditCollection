#!/usr/bin/env python3
"""Create a quarantined experimental front-face texture bake for an MPFB actor.

Run inside Blender after opening the neutral proxy .blend. The output names
contain ``experimental`` and never overwrite the clean proxy. Generated side
views guide geometry; they are not treated as calibrated projection cameras.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


def args_after_separator():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--actor-id", required=True)
    parser.add_argument("--front-image", type=Path, required=True)
    parser.add_argument("--front-analysis", type=Path, required=True,
                        help="JSON produced by analyze_turnaround.swift")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--texture-size", type=int, default=4096)
    parser.add_argument("--views", type=int, default=6)
    parser.add_argument("--resolution", type=int, default=768)
    parser.add_argument("--body-name")
    parser.add_argument("--rig-name")
    return parser.parse_args(argv)


def evaluated_positions(obj):
    states = []
    for modifier in obj.modifiers:
        if modifier.type == "MASK":
            states.append((modifier, modifier.show_viewport, modifier.show_render))
            modifier.show_viewport = modifier.show_render = False
    bpy.context.view_layer.update()
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        return [evaluated.matrix_world @ vertex.co for vertex in mesh.vertices]
    finally:
        evaluated.to_mesh_clear()
        for modifier, viewport, render in states:
            modifier.show_viewport, modifier.show_render = viewport, render
        bpy.context.view_layer.update()


def group_members(obj, name: str, threshold=0.01):
    group = obj.vertex_groups.get(name)
    if group is None:
        raise RuntimeError(f"Missing MPFB group {name!r}")
    return {
        vertex.index for vertex in obj.data.vertices
        if any(item.group == group.index and item.weight > threshold for item in vertex.groups)
    }


def group_center(obj, positions, name: str):
    members = group_members(obj, name)
    points = [positions[index] for index in members]
    return sum(points, Vector()) / len(points)


def image_landmarks(analysis: dict):
    face = analysis.get("face", {})
    box = face.get("bounding_box")
    if not box:
        raise RuntimeError("No face bounding box in Vision analysis")

    def centroid(key):
        points = face.get(key, [])
        if not points:
            raise RuntimeError(f"No {key} landmarks in Vision analysis")
        x = sum(point["x"] for point in points) / len(points)
        y = sum(point["y"] for point in points) / len(points)
        return Vector((box["x"] + x * box["width"], box["y"] + y * box["height"]))

    eyes = sorted([centroid("left_eye"), centroid("right_eye")], key=lambda point: point.x)
    mouth = centroid("outer_lips")
    return eyes, mouth


def projection_uv(body, positions, analysis):
    image_eyes, image_mouth = image_landmarks(analysis)
    model_eyes = sorted([
        group_center(body, positions, "joint-l-eye"),
        group_center(body, positions, "joint-r-eye"),
    ], key=lambda point: point.x)
    model_mouth = group_center(body, positions, "joint-mouth")
    image_eye_y = (image_eyes[0].y + image_eyes[1].y) / 2.0
    model_eye_z = (model_eyes[0].z + model_eyes[1].z) / 2.0
    model_eye_span = model_eyes[1].x - model_eyes[0].x
    image_eye_span = image_eyes[1].x - image_eyes[0].x
    if model_eye_span <= 0 or image_eye_span <= 0 or model_eye_z <= model_mouth.z:
        raise RuntimeError("Degenerate eye/mouth calibration; reject this head reference")
    layer = body.data.uv_layers.get("IdentityFront") or body.data.uv_layers.new(name="IdentityFront")
    model_mid_x = (model_eyes[0].x + model_eyes[1].x) / 2.0
    image_mid_x = (image_eyes[0].x + image_eyes[1].x) / 2.0
    for loop in body.data.loops:
        point = positions[loop.vertex_index]
        u = image_mid_x + (point.x - model_mid_x) * image_eye_span / model_eye_span
        v = image_mouth.y + (point.z - model_mouth.z) * (
            image_eye_y - image_mouth.y
        ) / (model_eye_z - model_mouth.z)
        layer.data[loop.index].uv = (u, v)
    return {
        "image_eyes": [list(point) for point in image_eyes],
        "image_mouth": list(image_mouth),
        "model_eyes": [list(point) for point in model_eyes],
        "model_mouth": list(model_mouth),
    }


def bake_material(body, source_image, target_image, positions, calibration):
    fallback = bpy.data.materials.new("ExperimentalBakeFallback")
    fallback.use_nodes = True
    fallback_nodes = fallback.node_tree.nodes
    fallback_links = fallback.node_tree.links
    fallback_nodes.clear()
    fallback_output = fallback_nodes.new("ShaderNodeOutputMaterial")
    fallback_emission = fallback_nodes.new("ShaderNodeEmission")
    fallback_emission.inputs["Color"].default_value = (0.46, 0.27, 0.19, 1.0)
    fallback_links.new(fallback_emission.outputs[0], fallback_output.inputs[0])
    target = fallback_nodes.new("ShaderNodeTexImage")
    target.image = target_image
    target.select = True
    fallback_nodes.active = target

    projected = bpy.data.materials.new("ExperimentalFrontFaceProjection")
    projected.use_nodes = True
    nodes, links = projected.node_tree.nodes, projected.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    links.new(emission.outputs[0], output.inputs[0])
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = "IdentityFront"
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = source_image
    texture.interpolation = "Linear"
    texture.extension = "CLIP"
    links.new(uv.outputs[0], texture.inputs[0])
    geometry = nodes.new("ShaderNodeNewGeometry")
    dot = nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    dot.inputs[1].default_value = (0.0, -1.0, 0.0)
    links.new(geometry.outputs[1], dot.inputs[0])
    weight = nodes.new("ShaderNodeMath")
    weight.operation = "MULTIPLY"
    weight.inputs[1].default_value = 1.4
    weight.use_clamp = True
    links.new(dot.outputs[1], weight.inputs[0])
    neutral = nodes.new("ShaderNodeRGB")
    neutral.outputs[0].default_value = (0.46, 0.27, 0.19, 1.0)
    mix = nodes.new("ShaderNodeMixRGB")
    links.new(weight.outputs[0], mix.inputs[0])
    links.new(neutral.outputs[0], mix.inputs[1])
    links.new(texture.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], emission.inputs[0])
    bake_target = nodes.new("ShaderNodeTexImage")
    bake_target.image = target_image
    bake_target.select = True
    nodes.active = bake_target

    body.data.materials.clear()
    body.data.materials.append(fallback)
    body.data.materials.append(projected)
    mouth_z = calibration["model_mouth"][2]
    eye_z = sum(point[2] for point in calibration["model_eyes"]) / 2.0
    eye_front_y = sum(point[1] for point in calibration["model_eyes"]) / 2.0
    eye_mid_x = sum(point[0] for point in calibration["model_eyes"]) / 2.0
    eye_span = abs(calibration["model_eyes"][1][0] - calibration["model_eyes"][0][0])
    for polygon in body.data.polygons:
        center = sum((positions[index] for index in polygon.vertices), Vector()) / len(polygon.vertices)
        is_front_face_patch = (
            mouth_z - 0.025 < center.z < eye_z + 0.075
            and abs(center.x - eye_mid_x) < eye_span * 1.8
            and center.y < eye_front_y + 0.045
        )
        polygon.material_index = int(is_front_face_patch)


def skin_only_copy(body):
    clone = body.copy()
    clone.data = body.data.copy()
    clone.name = "SkinOnly_ExperimentalBakeSource"
    bpy.context.collection.objects.link(clone)
    for modifier in list(clone.modifiers):
        clone.modifiers.remove(modifier)
    keep = group_members(body, "body")
    mesh = bmesh.new()
    mesh.from_mesh(clone.data)
    mesh.verts.ensure_lookup_table()
    bmesh.ops.delete(mesh, geom=[vertex for vertex in mesh.verts if vertex.index not in keep], context="VERTS")
    mesh.to_mesh(clone.data)
    mesh.free()
    clone.data.update()
    return clone


def apply_baked_skin(body, image):
    material = bpy.data.materials.new("Experimental_Identity_Skin")
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    links.new(uv.outputs[0], texture.inputs[0])
    links.new(texture.outputs[0], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.54
    body.data.materials.clear()
    body.data.materials.append(material)
    for polygon in body.data.polygons:
        polygon.material_index = 0


def render_views(body, output, count, resolution):
    output.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = int(round(resolution * 4 / 3))
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    camera_data = bpy.data.cameras.new("ExperimentalBakeQACamera")
    camera = bpy.data.objects.new("ExperimentalBakeQACamera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 2.05
    scene.camera = camera
    target = Vector((0.0, 0.0, 0.92))
    for index in range(count):
        angle = index * 360.0 / count
        radians = math.radians(angle)
        camera.location = Vector((4 * math.sin(radians), -4 * math.cos(radians), target.z))
        camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = str(output / f"azimuth_{round(angle):03d}.png")
        bpy.ops.render.render(write_still=True)
    camera.data.type = "PERSP"
    camera.data.lens = 100
    camera.location = Vector((0.0, -1.2, 1.66))
    camera.rotation_euler = (Vector((0.0, 0.0, 1.66)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.resolution_x = scene.render.resolution_y = max(1024, resolution)
    scene.render.filepath = str(output / "face_closeup.png")
    bpy.ops.render.render(write_still=True)


def main():
    args = args_after_separator()
    body_name = args.body_name or f"{args.actor_id}_Basemesh"
    rig_name = args.rig_name or f"{args.actor_id}_game_engine"
    body, rig = bpy.data.objects.get(body_name), bpy.data.objects.get(rig_name)
    if body is None or rig is None:
        raise SystemExit(f"Open the neutral proxy blend first; missing {body_name!r} or {rig_name!r}")
    if not args.front_image.is_file() or not args.front_analysis.is_file():
        raise SystemExit("Front head image or Vision analysis is missing")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    analysis = json.loads(args.front_analysis.read_text(encoding="utf-8"))
    positions = evaluated_positions(body)
    calibration = projection_uv(body, positions, analysis)
    texture_path = args.output_dir / f"{args.actor_id}_experimental_head_albedo.png"
    target = bpy.data.images.new(
        f"{args.actor_id}_ExperimentalHeadAlbedo", width=args.texture_size,
        height=args.texture_size, alpha=False, float_buffer=False,
    )
    target.generated_color = (0.46, 0.27, 0.19, 1.0)
    target.filepath_raw = str(texture_path)
    target.file_format = "PNG"
    source = bpy.data.images.load(str(args.front_image), check_existing=True)
    bake_material(body, source, target, positions, calibration)
    clone = skin_only_copy(body)
    clone.data.uv_layers["UVMap"].active = True
    clone.data.uv_layers["UVMap"].active_render = True
    bpy.ops.object.select_all(action="DESELECT")
    clone.select_set(True)
    bpy.context.view_layer.objects.active = clone
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 1
    scene.render.bake.margin = 24
    bpy.ops.object.bake(type="EMIT", use_clear=True, margin=24)
    target.save()
    mesh = clone.data
    bpy.data.objects.remove(clone, do_unlink=True)
    bpy.data.meshes.remove(mesh)
    apply_baked_skin(body, target)

    render_dir = args.output_dir / "experimental_texture_qa"
    render_views(body, render_dir, args.views, args.resolution)
    blend = args.output_dir / f"{args.actor_id}_experimental_textured.blend"
    glb = args.output_dir / f"{args.actor_id}_experimental_textured.glb"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True,
                              export_skins=True, export_animations=False, export_apply=False)
    report = {
        "status": "experimental_pending_visual_qa",
        "warning": "AI views are not calibrated cameras; do not promote this GLB until every QA gate passes.",
        "front_image": str(args.front_image.resolve()),
        "front_analysis": str(args.front_analysis.resolve()),
        "calibration": calibration,
        "texture": str(texture_path), "renders": str(render_dir),
        "blend": str(blend), "glb": str(glb),
    }
    path = args.output_dir / f"{args.actor_id}_experimental_bake_report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("EXPERIMENTAL_BAKE_REPORT", json.dumps(report))


if __name__ == "__main__":
    main()
