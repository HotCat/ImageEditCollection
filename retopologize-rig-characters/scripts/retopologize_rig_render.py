#!/usr/bin/env python3
"""Retopologize, rig, pose, render, and export an upright humanoid GLB.

Run inside Blender:
  blender --background --factory-startup --python retopologize_rig_render.py -- \
    --source person.glb --output-dir output
"""

import argparse
import bpy
import json
import math
import os
import sys
import time
from mathutils import Matrix, Vector


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Input GLB or GLTF")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--target-height", type=float, default=1.68)
    parser.add_argument("--voxel-size", type=float, default=0.004)
    parser.add_argument("--views", type=int, default=6)
    parser.add_argument("--resolution", type=int, default=768)
    parser.add_argument("--spine-bend", type=float, default=54.0)
    parser.add_argument("--chest-bend", type=float, default=31.0)
    parser.add_argument("--support-height", type=float, default=0.0)
    parser.add_argument("--camera-lens", type=float, default=58.0)
    parser.add_argument("--rotate-x", type=float, default=0.0, help="Pre-normalization rotation in degrees")
    parser.add_argument("--rotate-y", type=float, default=0.0, help="Pre-normalization rotation in degrees")
    parser.add_argument("--rotate-z", type=float, default=0.0, help="Pre-normalization rotation in degrees")
    parser.add_argument(
        "--rig-config",
        help="Optional JSON overriding template bone head/tail positions and IK offsets",
    )
    args = parser.parse_args(argv)
    args.source = os.path.abspath(args.source)
    args.output_dir = os.path.abspath(args.output_dir)
    if not os.path.isfile(args.source):
        parser.error(f"source does not exist: {args.source}")
    if not args.source.lower().endswith((".glb", ".gltf")):
        parser.error("source must be a .glb or .gltf file")
    if args.voxel_size <= 0 or args.target_height <= 0:
        parser.error("voxel size and target height must be positive")
    if args.views < 1 or args.resolution < 64:
        parser.error("views must be >= 1 and resolution must be >= 64")
    if args.rig_config:
        args.rig_config = os.path.abspath(args.rig_config)
        if not os.path.isfile(args.rig_config):
            parser.error(f"rig config does not exist: {args.rig_config}")
    return args


def load_rig_config(path):
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError("rig config must be a JSON object")
    return config


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in (
        bpy.data.meshes,
        bpy.data.armatures,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.curves,
    ):
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)


def select_only(*objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.hide_set(False)
        obj.hide_viewport = False
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def object_bounds(objects, evaluated=False):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points = []
    for original in objects:
        obj = original.evaluated_get(depsgraph) if evaluated else original
        points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    low = Vector(tuple(min(point[index] for point in points) for index in range(3)))
    high = Vector(tuple(max(point[index] for point in points) for index in range(3)))
    return low, high


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_area(name, location, energy, size, color, target):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def add_bone(edit_bones, name, head, tail, parent=None, connected=False, deform=True):
    bone = edit_bones.new(name)
    bone.head = head
    bone.tail = tail
    bone.parent = parent
    bone.use_connect = connected
    bone.use_deform = deform
    return bone


def import_normalized_detail(source_path, target_height, rotations):
    bpy.ops.import_scene.gltf(filepath=source_path, import_pack_images=True)
    source_meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not source_meshes:
        raise RuntimeError("No mesh objects found in source")

    # Flatten every imported world transform while retaining materials and UVs.
    flattened = []
    for index, source in enumerate(source_meshes):
        data = source.data.copy()
        data.transform(source.matrix_world)
        obj = bpy.data.objects.new(f"Flattened_Source_{index:03d}", data)
        bpy.context.collection.objects.link(obj)
        flattened.append(obj)
    for obj in list(bpy.context.scene.objects):
        if obj not in flattened:
            bpy.data.objects.remove(obj, do_unlink=True)

    select_only(flattened[0], *flattened[1:])
    if len(flattened) > 1:
        bpy.ops.object.join()
    detail = flattened[0]
    detail.name = "Original_Detail_Hidden"
    detail.data.name = "Original_Detail_Surface"

    rotate_x, rotate_y, rotate_z = rotations
    rotation = (
        Matrix.Rotation(math.radians(rotate_z), 4, "Z")
        @ Matrix.Rotation(math.radians(rotate_y), 4, "Y")
        @ Matrix.Rotation(math.radians(rotate_x), 4, "X")
    )
    detail.data.transform(rotation)

    low, high = object_bounds([detail])
    center = (low + high) * 0.5
    scale = target_height / max(high.z - low.z, 1e-9)
    detail.data.transform(
        Matrix.Scale(scale, 4)
        @ Matrix.Translation(Vector((-center.x, -center.y, -low.z)))
    )
    return detail, len(source_meshes)


def make_retopology(detail, voxel_size):
    retopo = detail.copy()
    retopo.data = detail.data.copy()
    retopo.name = "Character_Retopologized"
    retopo.data.name = "Character_Quad_Dominant_Surface"
    bpy.context.collection.objects.link(retopo)
    select_only(retopo)

    retopo.data.remesh_voxel_size = voxel_size
    retopo.data.remesh_voxel_adaptivity = 0.0
    started = time.time()
    bpy.ops.object.voxel_remesh()
    print(
        "VOXEL_RETOPOLOGY",
        len(retopo.data.vertices),
        len(retopo.data.polygons),
        "SECONDS",
        round(time.time() - started, 2),
    )

    shrink = retopo.modifiers.new("Project_To_Original_Detail", "SHRINKWRAP")
    shrink.target = detail
    shrink.wrap_method = "NEAREST_SURFACEPOINT"
    shrink.wrap_mode = "ON_SURFACE"
    select_only(retopo)
    bpy.ops.object.modifier_apply(modifier=shrink.name)

    if detail.data.uv_layers or len(detail.material_slots) > 1:
        transfer = retopo.modifiers.new("Transfer_Original_UV_And_Materials", "DATA_TRANSFER")
        transfer.object = detail
    if detail.data.uv_layers:
        source_uv = detail.data.uv_layers.active.name
        retopo.data.uv_layers.new(name=source_uv)
        retopo.data.uv_layers.active = retopo.data.uv_layers[source_uv]
        transfer.use_loop_data = True
        transfer.data_types_loops = {"UV"}
        transfer.loop_mapping = "POLYINTERP_NEAREST"
        transfer.layers_uv_select_src = source_uv
        transfer.layers_uv_select_dst = source_uv
        print("UV_TRANSFERRED", source_uv)
    else:
        print("WARNING_NO_SOURCE_UV")
    if len(detail.material_slots) > 1:
        transfer.use_poly_data = True
        transfer.data_types_polys = {"MATERIAL_INDEX"}
        transfer.poly_mapping = "POLYINTERP_NEAREST"
    if detail.data.uv_layers or len(detail.material_slots) > 1:
        select_only(retopo)
        bpy.ops.object.modifier_apply(modifier=transfer.name)

    for polygon in retopo.data.polygons:
        polygon.use_smooth = True
    return retopo


def clean_materials(mesh):
    for slot in mesh.material_slots:
        if not slot.material:
            continue
        material = slot.material.copy()
        material.name = f"Retopology_{slot.material.name}"
        slot.material = material
        if not material.use_nodes:
            continue
        for node in material.node_tree.nodes:
            if node.type != "BSDF_PRINCIPLED":
                continue
            metallic = node.inputs.get("Metallic")
            if metallic:
                for link in list(metallic.links):
                    material.node_tree.links.remove(link)
                metallic.default_value = 0.0
            roughness = node.inputs.get("Roughness")
            if roughness and not roughness.is_linked:
                roughness.default_value = 0.46
            specular = node.inputs.get("Specular IOR Level")
            if specular:
                specular.default_value = 0.32
            subsurface = node.inputs.get("Subsurface Weight")
            if subsurface:
                subsurface.default_value = 0.03


def build_armature(target_height, config):
    scale = target_height / 1.68
    point = lambda x, y, z: (x * scale, y * scale, z * scale)
    data = bpy.data.armatures.new("Character_Retopology_Humanoid")
    armature = bpy.data.objects.new("Character_Retopology_Rig", data)
    bpy.context.collection.objects.link(armature)
    armature.show_in_front = True
    data.display_type = "OCTAHEDRAL"
    select_only(armature)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = data.edit_bones

    root = add_bone(eb, "root", point(0, 0, 0.02), point(0, 0, 0.18), deform=False)
    hips = add_bone(eb, "hips", point(0, 0, 0.82), point(0, 0, 0.96), root)
    spine = add_bone(eb, "spine", point(0, 0, 0.96), point(0, 0, 1.18), hips, True)
    chest = add_bone(eb, "chest", point(0, 0, 1.18), point(0, 0, 1.40), spine, True)
    neck = add_bone(eb, "neck", point(0, 0, 1.40), point(0, 0, 1.49), chest, True)
    add_bone(eb, "head", point(0, 0, 1.49), point(0, 0, 1.66), neck, True)

    for side, sign in (("L", 1), ("R", -1)):
        clavicle = add_bone(
            eb, f"clavicle.{side}", point(0, 0, 1.39), point(0.155 * sign, 0, 1.385), chest
        )
        upper = add_bone(
            eb,
            f"upper_arm.{side}",
            point(0.155 * sign, 0, 1.385),
            point(0.285 * sign, 0, 1.185),
            clavicle,
            True,
        )
        forearm = add_bone(
            eb,
            f"forearm.{side}",
            point(0.285 * sign, 0, 1.185),
            point(0.405 * sign, 0, 0.965),
            upper,
            True,
        )
        add_bone(
            eb,
            f"hand.{side}",
            point(0.405 * sign, 0, 0.965),
            point(0.43 * sign, -0.005, 0.835),
            forearm,
            True,
        )

        thigh = add_bone(
            eb,
            f"thigh.{side}",
            point(0.075 * sign, 0, 0.86),
            point(0.09 * sign, 0, 0.48),
            hips,
        )
        shin = add_bone(
            eb,
            f"shin.{side}",
            point(0.09 * sign, 0, 0.48),
            point(0.105 * sign, 0, 0.10),
            thigh,
            True,
        )
        add_bone(
            eb,
            f"foot.{side}",
            point(0.105 * sign, 0, 0.10),
            point(0.105 * sign, -0.15, 0.045),
            shin,
            True,
        )

    bone_overrides = config.get("bones", {})
    if not isinstance(bone_overrides, dict):
        raise ValueError("rig config 'bones' must be an object")
    for bone_name, override in bone_overrides.items():
        if bone_name not in eb:
            raise ValueError(f"unknown bone in rig config: {bone_name}")
        if not isinstance(override, dict):
            raise ValueError(f"bone override for {bone_name} must be an object")
        bone = eb[bone_name]
        if "head" in override:
            bone.head = tuple(float(value) * scale for value in override["head"])
        if "tail" in override:
            bone.tail = tuple(float(value) * scale for value in override["tail"])
        if (bone.tail - bone.head).length < 1e-5:
            raise ValueError(f"bone override collapses {bone_name}")

    for bone in eb:
        try:
            bone.align_roll(Vector((0, -1, 0)))
        except RuntimeError:
            pass
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def automatic_heat_weights(mesh, armature):
    select_only(armature, mesh)
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    modifiers = [
        modifier
        for modifier in mesh.modifiers
        if modifier.type == "ARMATURE" and modifier.object == armature
    ]
    if not modifiers:
        raise RuntimeError("Automatic bone heat did not create an armature modifier")
    modifiers[0].name = "Character_Continuous_Armature"
    modifiers[0].use_deform_preserve_volume = True
    print("AUTOMATIC_HEAT_WEIGHTS", len(mesh.vertex_groups))


def add_empty(name, location, display_type="SPHERE", size=0.045):
    empty = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(empty)
    empty.location = location
    empty.empty_display_type = display_type
    empty.empty_display_size = size
    empty.hide_render = True
    return empty


def pose_character(armature, args, config):
    scale = args.target_height / 1.68
    armature.location.z = args.support_height
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "XYZ"
    armature.pose.bones["spine"].rotation_euler.x = math.radians(args.spine_bend)
    armature.pose.bones["chest"].rotation_euler.x = math.radians(args.chest_bend)
    armature.pose.bones["neck"].rotation_euler.x = math.radians(8)
    armature.pose.bones["head"].rotation_euler.x = math.radians(-5)
    armature.pose.bones["thigh.L"].rotation_euler.x = math.radians(-7)
    armature.pose.bones["shin.L"].rotation_euler.x = math.radians(12)
    armature.pose.bones["thigh.R"].rotation_euler.x = math.radians(5)
    armature.pose.bones["shin.R"].rotation_euler.x = math.radians(7)
    bpy.context.view_layer.update()

    ik = config.get("ik", {})
    if not isinstance(ik, dict):
        raise ValueError("rig config 'ik' must be an object")
    wrist_out = float(ik.get("wrist_out", 0.075))
    wrist_forward = float(ik.get("wrist_forward", -0.015))
    wrist_drop = float(ik.get("wrist_drop", -0.49))
    pole_out = float(ik.get("pole_out", 0.34))
    pole_forward = float(ik.get("pole_forward", -0.22))
    pole_drop = float(ik.get("pole_drop", -0.22))

    for side, sign in (("L", 1), ("R", -1)):
        upper = armature.pose.bones[f"upper_arm.{side}"]
        shoulder = armature.matrix_world @ upper.head
        target = add_empty(
            f"hand_gravity_target.{side}",
            shoulder + Vector((wrist_out * sign * scale, wrist_forward * scale, wrist_drop * scale)),
        )
        pole = add_empty(
            f"elbow_gravity_pole.{side}",
            shoulder + Vector((pole_out * sign * scale, pole_forward * scale, pole_drop * scale)),
            "CUBE",
            0.035 * scale,
        )
        constraint = armature.pose.bones[f"forearm.{side}"].constraints.new("IK")
        constraint.name = "Gravity_Hanging_Arm"
        constraint.target = target
        constraint.pole_target = pole
        constraint.pole_angle = math.pi if side == "L" else 0.0
        constraint.chain_count = 2
        constraint.use_stretch = False
        constraint.iterations = 80
    bpy.context.view_layer.update()


def key_pose(armature):
    scene = bpy.context.scene
    scene.frame_start = scene.frame_end = 1
    scene.frame_set(1)
    action = bpy.data.actions.new("Retopology_OTS_Hanging_Arms_Pose")
    armature.animation_data_create()
    armature.animation_data.action = action
    for pose_bone in armature.pose.bones:
        pose_bone.keyframe_insert(data_path="location", frame=1, group=pose_bone.name)
        pose_bone.keyframe_insert(data_path="rotation_euler", frame=1, group=pose_bone.name)
        pose_bone.keyframe_insert(data_path="scale", frame=1, group=pose_bone.name)


def build_studio(mesh, resolution, lens):
    scene = bpy.context.scene
    low, high = object_bounds([mesh], evaluated=True)
    center = (low + high) * 0.5
    target = center + Vector((0, 0, 0.05))

    bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, -0.012))
    ground = bpy.context.object
    ground.name = "Studio_Ground"
    material = bpy.data.materials.new("Studio_Ground_Material")
    material.diffuse_color = (0.055, 0.065, 0.085, 1)
    material.roughness = 0.62
    ground.data.materials.append(material)
    add_area("Key", (3.3, -4.0, 3.4), 1050, 3.2, (1.0, 0.82, 0.70), target)
    add_area("Fill", (-3.3, -2.2, 2.6), 720, 3.8, (0.62, 0.76, 1.0), target)
    add_area("Rim", (1.5, 3.5, 3.0), 1150, 2.6, (0.68, 0.84, 1.0), target)
    add_area("Top_Softbox", (0, 0, 4.2), 650, 3.0, (1.0, 0.95, 0.90), target)

    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.012, 0.018, 0.035, 1)
    background.inputs["Strength"].default_value = 0.32

    camera_data = bpy.data.cameras.new("Camera_360")
    camera = bpy.data.objects.new("Camera_360", camera_data)
    bpy.context.collection.objects.link(camera)
    camera_data.lens = lens
    camera_data.sensor_width = 36
    scene.camera = camera
    # Blender renamed Eevee in 4.2. Assign by version to avoid an invalid enum.
    scene.render.engine = "BLENDER_EEVEE_NEXT" if bpy.app.version >= (4, 2, 0) else "BLENDER_EEVEE"
    scene.render.resolution_x = scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.view_settings.look = "AgX - Medium High Contrast"
    return camera, low, high, center


def render_views(scene, camera, mesh, output_dir, views, lens):
    render_dir = os.path.join(output_dir, f"renders_{views}view")
    os.makedirs(render_dir, exist_ok=True)
    for stale in os.listdir(render_dir):
        if stale.lower().endswith(".png") and "azimuth_" in stale:
            os.remove(os.path.join(render_dir, stale))
    low, high = object_bounds([mesh], evaluated=True)
    center = (low + high) * 0.5 + Vector((0, 0, 0.02))
    extent = max((high - low).x, (high - low).y, (high - low).z)
    distance = max(3.0, extent * 2.55)
    report = []
    for index in range(views):
        angle = index * 360.0 / views
        radians = math.radians(angle)
        camera.location = (
            math.sin(radians) * distance,
            -math.cos(radians) * distance,
            center.z + 0.10,
        )
        look_at(camera, center)
        path = os.path.join(render_dir, f"azimuth_{round(angle):03d}.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        report.append(
            {
                "azimuth_degrees": angle,
                "camera_location": list(camera.location),
                "camera_rotation_euler": list(camera.rotation_euler),
                "lens_mm": lens,
                "target": list(center),
                "render": path,
            }
        )
        print("RENDERED", round(angle, 3), path)
    return report


def validate_export(glb_path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=glb_path, import_pack_images=True)
    imported = [obj for obj in bpy.data.objects if obj not in before]
    armatures = [obj for obj in imported if obj.type == "ARMATURE"]
    meshes = [obj for obj in imported if obj.type == "MESH"]
    skinned_meshes = [
        obj
        for obj in meshes
        if any(modifier.type == "ARMATURE" for modifier in obj.modifiers)
        or obj.parent in armatures
    ]
    materials = sum(len(obj.material_slots) for obj in meshes)
    actions = len(bpy.data.actions)
    result = {
        "armatures": len(armatures),
        "meshes": len(meshes),
        "skinned_meshes": len(skinned_meshes),
        "material_slots": materials,
        "actions_in_file": actions,
        "passed": len(armatures) >= 1 and len(meshes) >= 1 and len(skinned_meshes) >= 1,
    }
    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)
    if not result["passed"]:
        raise RuntimeError(f"GLB re-import validation failed: {result}")
    print("GLB_REIMPORT_VALID", json.dumps(result, sort_keys=True))
    return result


def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    blend_path = os.path.join(args.output_dir, "character_retopo_rigged.blend")
    glb_path = os.path.join(args.output_dir, "character_retopo_rigged.glb")
    report_path = os.path.join(args.output_dir, "camera_views.json")
    config = load_rig_config(args.rig_config)

    clear_scene()
    detail, source_mesh_count = import_normalized_detail(
        args.source,
        args.target_height,
        (args.rotate_x, args.rotate_y, args.rotate_z),
    )
    source_vertices = len(detail.data.vertices)
    source_faces = len(detail.data.polygons)
    retopo = make_retopology(detail, args.voxel_size)
    clean_materials(retopo)
    armature = build_armature(args.target_height, config)
    automatic_heat_weights(retopo, armature)
    pose_character(armature, args, config)
    key_pose(armature)
    detail.hide_render = True
    detail.hide_viewport = True
    detail.hide_set(True)

    scene = bpy.context.scene
    camera, low, high, center = build_studio(retopo, args.resolution, args.camera_lens)
    views = render_views(scene, camera, retopo, args.output_dir, args.views, args.camera_lens)
    report = {
        "source": args.source,
        "blender_version": bpy.app.version_string,
        "source_meshes": source_mesh_count,
        "source_vertices": source_vertices,
        "source_faces": source_faces,
        "retopology_vertices": len(retopo.data.vertices),
        "retopology_faces": len(retopo.data.polygons),
        "voxel_size": args.voxel_size,
        "target_height": args.target_height,
        "support_height": args.support_height,
        "source_rotation_degrees": [args.rotate_x, args.rotate_y, args.rotate_z],
        "rig_config": args.rig_config,
        "bones": len(armature.data.bones),
        "resolution": [args.resolution, args.resolution],
        "blend_path": blend_path,
        "glb_path": glb_path,
        "views": views,
    }

    if views:
        camera.location = views[0]["camera_location"]
        camera.rotation_euler = views[0]["camera_rotation_euler"]
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    select_only(armature, retopo)
    bpy.ops.export_scene.gltf(
        filepath=glb_path,
        export_format="GLB",
        use_selection=True,
        export_animations=True,
        export_frame_range=True,
        export_skins=True,
        export_morph=False,
        export_apply=False,
        export_force_sampling=True,
    )
    report["glb_reimport_validation"] = validate_export(glb_path)
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print("SAVED", blend_path)
    print("EXPORTED", glb_path)
    print("REPORT", report_path)


if __name__ == "__main__":
    main()
