---
name: retopologize-rig-characters
description: Rebuild dense, fragmented, non-manifold, or fused AI-generated humanoid GLB/GLTF meshes into a unified quad-dominant deformation surface; transfer the original UV/material appearance; create and weight a humanoid armature; pose independently hanging arms and a deep waist bend; and render evenly spaced 360-degree QA views. Use for Hi3D, Hunyuan3D, SAM body-to-3D, photogrammetry, or similar character meshes that tear, stretch, or drag clothing when rigged directly, especially when preparing an over-the-shoulder carry, limp body, forward bend, or other large deformation in Blender.
---

# Retopologize and Rig Characters

Use the bundled Blender script for a repeatable deformation-proxy workflow. Treat its voxel remesh as a unified quad-dominant production proxy, not animation-studio edge-loop retopology.

## Preconditions

- Require Blender 4.0 or newer and an upright humanoid in an A-pose or relaxed T-pose.
- Expect world Z to be up, X to run left/right, and the character to face toward negative Y. Render or inspect the source before rigging. Use `--rotate-x`, `--rotate-y`, and `--rotate-z` when it does not match this convention.
- Inspect the source texture and silhouette before processing. Do not judge preservation only from vertex counts.
- Use this workflow for fused clothing when the goal is stable large deformation. Use manual garment separation, corrective shape keys, or cloth simulation when accurate cloth-body collision is required.

## Core workflow

1. Resolve the source file, Blender executable, output directory, and desired real-world height.
2. Run `scripts/retopologize_rig_render.py` inside Blender. Start with the 4 mm voxel default for a 1.68 m character.
3. Inspect the six-view contact sheet, individual full-resolution renders, shoulders, armpits, elbows, waist, skirt hem, knees, ankles, hands, and texture seams.
4. Iterate on voxel size, rig proportions, arm IK targets, or pose angles when defects remain. Never accept a run solely because Blender completed without an error.
5. Re-import the exported GLB into a clean Blender scene. Confirm one skinned mesh, one armature, embedded or resolved materials, and the intended pose.

## Run the workflow

```bash
SKILL_DIR=/absolute/path/to/retopologize-rig-characters
BLENDER="/Applications/Blender 4.0.app/Contents/MacOS/Blender"
"$BLENDER" --background --factory-startup \
  --python "$SKILL_DIR/scripts/retopologize_rig_render.py" -- \
  --source /absolute/path/character.glb \
  --output-dir /absolute/path/character_retopology \
  --target-height 1.68 \
  --voxel-size 0.004 \
  --support-height 0.30 \
  --views 6 \
  --resolution 768
```

Use `--support-height 0.30` for the suspended carried-person half of an OTS pose. Omit it or use `--support-height 0` for a grounded bend.

The script writes:

- `character_retopo_rigged.blend`: authoritative editable project, including hidden source detail and IK controls;
- `character_retopo_rigged.glb`: selected retopologized mesh, skin, pose sampling, and textures;
- `renders_Nview/`: freshly cleared evenly divided azimuth views beginning at 0 degrees;
- `camera_views.json`: camera, topology, Blender-version, output-path, and GLB re-import-validation metadata.

Create the diagnostic sheet after rendering:

```bash
python "$SKILL_DIR/scripts/make_contact_sheet.py" \
  --input-dir /absolute/path/character_retopology/renders_6view \
  --output /absolute/path/character_retopology/contact_sheet.png
```

Use a Python environment with Pillow for the contact-sheet script.

For a body whose proportions differ from the 1.68 m adult template, create a rig override JSON in normalized 1.68 m coordinates:

```json
{
  "bones": {
    "upper_arm.L": {"head": [0.17, 0.0, 1.40], "tail": [0.31, 0.0, 1.18]},
    "upper_arm.R": {"head": [-0.17, 0.0, 1.40], "tail": [-0.31, 0.0, 1.18]}
  },
  "ik": {
    "wrist_out": 0.075,
    "wrist_forward": -0.015,
    "wrist_drop": -0.49,
    "pole_out": 0.34,
    "pole_forward": -0.22,
    "pole_drop": -0.22
  }
}
```

Pass it with `--rig-config /absolute/path/rig.json`. Adjust paired left/right landmarks symmetrically in the normalized source A-pose, then inspect the bones in the saved Blender file before trusting the deformation.

## Retopology and texture-transfer rules

- Preserve a hidden normalized copy of the original scan as the detail and UV-transfer source.
- Use voxel remesh to fuse overlapping patches and create continuous topology before skinning.
- Shrinkwrap the remesh back to the source surface before transferring UVs.
- Transfer UVs with nearest polygon interpolation. Transfer material indices when multiple source materials exist.
- Keep the Blender file authoritative. GLB supports at most four joint influences per exported vertex and may normalize the four strongest weights.
- Do not call a simple decimation pass retopology. Decimation preserves the original deformation defects and does not create continuous shoulder or waist flow.

## Rigging and pose rules

- Use continuous automatic bone-heat weights on the unified mesh. The same solver often fails on the original fragmented scan.
- Enable preserve-volume deformation on the armature modifier.
- Use separate mirrored IK targets and poles for gravity-hanging arms. Mirror the left pole angle by 180 degrees; otherwise one shoulder can flip inward.
- Keep wrists below their shoulders with a slight side offset and small asymmetry. Avoid perfectly rigid bilateral symmetry for a limp pose.
- Distribute a deep bend across spine and chest rather than rotating one bone through the whole angle.
- Suspend the body with a positive `--support-height` only when representing the carried-person half of an over-the-shoulder pose. Add the carrier later and adjust abdomen/pelvis contact against the shoulder.

## Quality gates

Reject and iterate if any view shows:

- long triangular strips from sleeves, hands, skirt, hair, or shoes;
- an inverted or ballooned shoulder;
- an arm following the torso instead of gravity;
- a hard seam caused by discontinuous vertex weights;
- collapsed elbows, missing fingers, severe UV streaking, or background-facing texture projection;
- clipping that would make the support contact implausible.

Accept only when all requested views have identical dimensions, the arms deform independently, contact-critical geometry is readable, and `camera_views.json` reports `glb_reimport_validation.passed: true`.

## Failure recovery

- **Long strips or vertex explosions:** replace nearest-bone or hard-region weights with continuous bone heat. Do not hide the defect by changing the camera.
- **One shoulder folds inward:** rotate that side's IK pole angle by 180 degrees and render both oblique sides again.
- **Texture smears after remesh:** reduce voxel size, verify UV transfer uses the original normalized detail object, and inspect whether the source UV islands overlap.
- **Hands or skirt tiers disappear:** reduce voxel size gradually, for example from `0.004` to `0.003`; expect higher memory and slower weighting.
- **Automatic weights fail:** check that voxel remesh actually produced one continuous mesh, apply object transforms, remove duplicate armature modifiers and retry.
- **Clothes intersect the body:** fused clothing cannot provide independent cloth dynamics. Separate garments or use a dedicated clothed base mesh for final animation.
- **Anatomy still looks wrong despite clean deformation:** adjust skeleton landmark proportions. Retopology cannot compensate for misplaced shoulder, hip, knee, or elbow joints.
- **Character lies sideways or faces the wrong axis:** rerun with source rotation flags; for example, try `--rotate-x 90` for a Y-up source, then inspect a low-resolution single view before the full run.

Report the source topology, retopologized topology, voxel size, rig bone count, camera angles, render dimensions, Blender/GLB paths, and any remaining deformation limitations.
