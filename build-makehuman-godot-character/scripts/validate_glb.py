#!/usr/bin/env python3
"""Validate a humanoid GLB by raw JSON inspection and fresh Blender import."""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
from pathlib import Path

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-height", type=float)
    parser.add_argument("--height-tolerance", type=float, default=0.01)
    parser.add_argument(
        "--height-surface-index", type=int,
        help=(
            "Measure expected height from this imported material/surface index instead of "
            "the complete payload. Humanizer combined proxies put the anatomical body at "
            "surface 0, which excludes hair and other head equipment from stature."
        ),
    )
    parser.add_argument("--min-bones", type=int, default=20)
    parser.add_argument("--require-textures", action="store_true",
                        help="Require at least one embedded or resolvable image resource")
    parser.add_argument("--require-all-mesh-nodes-skinned", action="store_true",
                        help="Reject rigid/bone-parented mesh nodes such as detached eyes or hair")
    parser.add_argument("--require-single-payload-mesh", action="store_true",
                        help="Require one combined imported character mesh (Humanizer final proxy gate)")
    parser.add_argument("--min-surfaces", type=int, default=1,
                        help="Minimum primitive/material surfaces across raw GLB meshes")
    parser.add_argument("--require-animation", action="append", default=[],
                        help="Require an animation name; repeat for Idle, Run, etc.")
    return parser.parse_args(argv)


def raw_document(path: Path):
    with path.open("rb") as handle:
        magic, version, total = struct.unpack("<4sII", handle.read(12))
        if magic != b"glTF" or version != 2 or total != path.stat().st_size:
            raise ValueError("Invalid GLB header or declared length")
        json_length, json_kind = struct.unpack("<II", handle.read(8))
        if json_kind != 0x4E4F534A:
            raise ValueError("First GLB chunk is not JSON")
        document = json.loads(handle.read(json_length).decode("utf-8").rstrip("\x00 "))
    return document


def material_texture_indices(value):
    """Collect glTF texture indices referenced by nested material slots."""
    indices = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("Texture") and isinstance(item, dict) and isinstance(item.get("index"), int):
                indices.append(item["index"])
            indices.extend(material_texture_indices(item))
    elif isinstance(value, list):
        for item in value:
            indices.extend(material_texture_indices(item))
    return indices


def evaluated_points(objects, *, surface_index=None):
    """Return deformed world-space vertices, optionally limited to one surface.

    Reading ``obj.data.vertices`` would inspect the pre-skin base mesh and can differ
    from what Godot or Blender actually renders after the imported armature modifier.
    Material indices survive glTF import, so Humanizer's first combined surface can
    be measured independently from hair, eyes, brows, and lashes.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points = []
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            vertex_indices = {
                vertex_index
                for polygon in mesh.polygons
                if surface_index is None or polygon.material_index == surface_index
                for vertex_index in polygon.vertices
            }
            points.extend(evaluated.matrix_world @ mesh.vertices[index].co for index in vertex_indices)
        finally:
            evaluated.to_mesh_clear()
    return points


def main():
    args = parse_args()
    if not args.glb.is_file():
        raise SystemExit(f"GLB does not exist: {args.glb}")
    document = raw_document(args.glb)
    raw_nodes = [node.get("name", "") for node in document.get("nodes", [])]
    raw_meshes = [mesh.get("name", "") for mesh in document.get("meshes", [])]
    raw_has_icosphere = "Icosphere" in raw_nodes or "Icosphere" in raw_meshes
    raw_mesh_nodes = [node for node in document.get("nodes", []) if isinstance(node.get("mesh"), int)]
    unskinned_mesh_nodes = [
        node.get("name", "unnamed mesh node") for node in raw_mesh_nodes
        if not isinstance(node.get("skin"), int)
    ]
    raw_surface_count = sum(len(mesh.get("primitives", [])) for mesh in document.get("meshes", []))
    raw_animation_names = [animation.get("name", "") for animation in document.get("animations", [])]
    image_resources = []
    unresolved_images = []
    for image in document.get("images", []):
        uri = image.get("uri")
        embedded = "bufferView" in image or (isinstance(uri, str) and uri.startswith("data:"))
        resolved = embedded or (isinstance(uri, str) and (args.glb.parent / uri).is_file())
        item = {"name": image.get("name"), "uri": uri, "embedded": embedded, "resolved": resolved}
        image_resources.append(item)
        if not resolved:
            unresolved_images.append(uri or image.get("name") or "unnamed image")
    textures = document.get("textures", [])
    referenced_texture_indices = sorted({
        index for material in document.get("materials", [])
        for index in material_texture_indices(material)
    })
    bad_texture_indices = [index for index in referenced_texture_indices if not 0 <= index < len(textures)]
    referenced_image_indices = sorted({
        textures[index].get("source") for index in referenced_texture_indices
        if 0 <= index < len(textures) and isinstance(textures[index].get("source"), int)
    })
    bad_image_indices = [index for index in referenced_image_indices if not 0 <= index < len(image_resources)]

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(args.glb))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    helpers = [obj for obj in meshes if obj.name == "Icosphere" and not raw_has_icosphere]
    payload = [obj for obj in meshes if obj not in helpers]
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    visual_points = evaluated_points(payload)
    measurement_points = (
        evaluated_points(payload, surface_index=args.height_surface_index)
        if args.height_surface_index is not None
        else visual_points
    )
    visual_minimum = (
        [min(point[axis] for point in visual_points) for axis in range(3)]
        if visual_points else None
    )
    visual_maximum = (
        [max(point[axis] for point in visual_points) for axis in range(3)]
        if visual_points else None
    )
    minimum = (
        [min(point[axis] for point in measurement_points) for axis in range(3)]
        if measurement_points else None
    )
    maximum = (
        [max(point[axis] for point in measurement_points) for axis in range(3)]
        if measurement_points else None
    )
    height = maximum[2] - minimum[2] if measurement_points else None
    visual_height = (
        visual_maximum[2] - visual_minimum[2] if visual_points else None
    )
    bone_counts = {obj.name: len(obj.data.bones) for obj in armatures}
    weighted_meshes = [
        obj.name for obj in payload
        if obj.vertex_groups and any(modifier.type == "ARMATURE" for modifier in obj.modifiers)
    ]
    imported_animation_names = sorted(action.name for action in bpy.data.actions)

    failures = []
    if not document.get("meshes"):
        failures.append("raw GLB contains no meshes")
    if not document.get("skins"):
        failures.append("raw GLB contains no skin")
    if args.require_all_mesh_nodes_skinned and unskinned_mesh_nodes:
        failures.append("raw mesh nodes without a skin: " + ", ".join(unskinned_mesh_nodes))
    if args.require_single_payload_mesh and len(payload) != 1:
        failures.append(f"fresh import has {len(payload)} payload meshes; expected one combined Avatar")
    if raw_surface_count < args.min_surfaces:
        failures.append(
            f"raw GLB has {raw_surface_count} primitive surfaces; expected at least {args.min_surfaces}"
        )
    # Godot replaces slashes in animation names with underscores on some export/import
    # paths. Compare normalized suffixes as well as exact names to avoid false failures.
    available_animations = set(raw_animation_names) | set(imported_animation_names)
    normalized_animations = {
        name.replace("/", "_").lower() for name in available_animations
    }
    for required in args.require_animation:
        normalized_required = required.replace("/", "_").lower()
        if not any(
            name == normalized_required or name.endswith("_" + normalized_required)
            for name in normalized_animations
        ):
            failures.append(f"required animation is missing: {required}")
    if raw_has_icosphere:
        failures.append("raw GLB contains an Icosphere helper")
    if unresolved_images:
        failures.append("unresolved image resources: " + ", ".join(unresolved_images))
    if bad_texture_indices:
        failures.append("materials reference invalid texture indices: " + ", ".join(map(str, bad_texture_indices)))
    if bad_image_indices:
        failures.append("textures reference invalid image indices: " + ", ".join(map(str, bad_image_indices)))
    if args.require_textures and not referenced_image_indices:
        failures.append("textured GLB has no material texture slot backed by an image")
    if not armatures:
        failures.append("fresh import contains no armature")
    if not bone_counts or max(bone_counts.values()) < args.min_bones:
        failures.append(f"armature has fewer than {args.min_bones} bones")
    if not payload:
        failures.append("fresh import contains no payload mesh")
    if args.height_surface_index is not None and not measurement_points:
        failures.append(
            f"fresh import has no vertices on height surface {args.height_surface_index}"
        )
    if not weighted_meshes:
        failures.append("no imported mesh has both vertex groups and an armature modifier")
    if args.expected_height is not None and height is not None:
        if abs(height - args.expected_height) > args.height_tolerance:
            failures.append(
                f"height {height:.6f} m differs from expected {args.expected_height:.6f} m "
                f"by more than {args.height_tolerance:.6f} m"
            )

    report = {
        "passed": not failures, "failures": failures,
        "glb": str(args.glb.resolve()), "file_size_bytes": os.path.getsize(args.glb),
        "raw": {
            "node_count": len(raw_nodes), "mesh_count": len(raw_meshes),
            "skin_count": len(document.get("skins", [])),
            "material_count": len(document.get("materials", [])),
            "image_count": len(image_resources), "images": image_resources,
            "texture_count": len(textures),
            "material_texture_indices": referenced_texture_indices,
            "referenced_image_indices": referenced_image_indices,
            "contains_icosphere": raw_has_icosphere,
            "mesh_nodes": [
                {"name": node.get("name"), "mesh": node.get("mesh"), "skin": node.get("skin")}
                for node in raw_mesh_nodes
            ],
            "unskinned_mesh_nodes": unskinned_mesh_nodes,
            "surface_count": raw_surface_count,
            "animation_names": raw_animation_names,
        },
        "fresh_import": {
            "mesh_objects": [obj.name for obj in meshes],
            "payload_meshes": [obj.name for obj in payload],
            "importer_helpers": [obj.name for obj in helpers],
            "armatures": [obj.name for obj in armatures], "bone_counts": bone_counts,
            "weighted_meshes": weighted_meshes,
            "animation_names": imported_animation_names,
            # ``height_m`` remains the value used by the expected-height gate for
            # backward compatibility. The explicit fields prevent callers from
            # confusing anatomical body height with hair-inclusive visual height.
            "bounds_min": minimum, "bounds_max": maximum, "height_m": height,
            "height_surface_index": args.height_surface_index,
            "height_surface_vertex_count": len(measurement_points),
            "visual_bounds_min": visual_minimum,
            "visual_bounds_max": visual_maximum,
            "visual_height_m": visual_height,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("GLB_VALIDATION", json.dumps(report))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
