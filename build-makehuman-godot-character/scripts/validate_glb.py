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
from mathutils import Vector


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-height", type=float)
    parser.add_argument("--height-tolerance", type=float, default=0.01)
    parser.add_argument("--min-bones", type=int, default=20)
    parser.add_argument("--require-textures", action="store_true",
                        help="Require at least one embedded or resolvable image resource")
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


def main():
    args = parse_args()
    if not args.glb.is_file():
        raise SystemExit(f"GLB does not exist: {args.glb}")
    document = raw_document(args.glb)
    raw_nodes = [node.get("name", "") for node in document.get("nodes", [])]
    raw_meshes = [mesh.get("name", "") for mesh in document.get("meshes", [])]
    raw_has_icosphere = "Icosphere" in raw_nodes or "Icosphere" in raw_meshes
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
    points = [obj.matrix_world @ Vector(corner) for obj in payload for corner in obj.bound_box]
    minimum = [min(point[axis] for point in points) for axis in range(3)] if points else None
    maximum = [max(point[axis] for point in points) for axis in range(3)] if points else None
    height = maximum[2] - minimum[2] if points else None
    bone_counts = {obj.name: len(obj.data.bones) for obj in armatures}
    weighted_meshes = [
        obj.name for obj in payload
        if obj.vertex_groups and any(modifier.type == "ARMATURE" for modifier in obj.modifiers)
    ]

    failures = []
    if not document.get("meshes"):
        failures.append("raw GLB contains no meshes")
    if not document.get("skins"):
        failures.append("raw GLB contains no skin")
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
        },
        "fresh_import": {
            "mesh_objects": [obj.name for obj in meshes],
            "payload_meshes": [obj.name for obj in payload],
            "importer_helpers": [obj.name for obj in helpers],
            "armatures": [obj.name for obj in armatures], "bone_counts": bone_counts,
            "weighted_meshes": weighted_meshes,
            "bounds_min": minimum, "bounds_max": maximum, "height_m": height,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("GLB_VALIDATION", json.dumps(report))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
