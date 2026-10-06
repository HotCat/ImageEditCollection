# Mixamo → Godot migration pipeline

This reference is read when the user has supplied a Mixamo FBX and a target
Godot project. Replace every example path, skeleton path, and animation name.
Run tools from a temporary work directory outside the Godot project when
possible; Godot's file indexer should not scan intermediate frame caches.

## 1. Inventory the two rigs

Before running an importer, inspect the FBX in Blender and the target GLB/scene.
Record:

- source armature name, action name, exact frame range, FPS, and object scale;
- whether the source has `Root`, `mixamorig:Hips`, or travel only on Hips;
- target Skeleton3D path, bone names, scene-unit height, and authored pose;
- target animation owner: scene root, `RootMotionSampler`, or a path/trajectory.

The source and target must both be evaluated in their rest pose before mapping.
Do not infer this from bone names alone. A matching name can still have a
different local basis or a mirrored knee axis.

## 2. Preprocess a copy in Blender

```bash
blender -b --python /absolute/path/migrate-mixamo-godot-motion/scripts/mixamo_to_godot_root_motion.py -- \
  --input '/absolute/path/Walking.fbx' \
  --output '/absolute/path/work/Walking.godot-root.fbx'
```

The script applies an armature object scale such as `0.01` and scales animated
bone-location keys with it, removes duplicate armatures, adds a non-connected
`Root` above `mixamorig:Hips`, preserves the Hips rest matrix, and exports only
the selected armature/meshes. It also restores the action's actual frame range
so Blender does not append a frozen tail.

Use `--no-normalize-scale` only when inspection proves the FBX is already at
unit scale. Use `--hips-name` or `--root-name` for a nonstandard rig. Never
overwrite the downloaded FBX.

## 3. Retarget to the target rig

For a complete body migration:

```bash
blender -b --python /absolute/path/migrate-mixamo-godot-motion/scripts/retarget_mixamo_fbx.py -- \
  --source '/absolute/path/work/Walking.godot-root.fbx' \
  --target '/absolute/path/project/assets/models/male.glb' \
  --output '/absolute/path/work/walking-body.godot-pose-motion.json' \
  --bone-set full \
  --include-root \
  --application-mode additive \
  --animation-name mixamo_walking_body
```

Use `--bone-set body` for hips through hands/head without optional fingers, or
`--bone-set lower` when the target scene has an authored OTS/carry torso and
runtime hand IK. `--bone-set full` additionally maps explicit Mixamo finger and
toe aliases when both rigs expose them. Use `--application-mode absolute` only when the target
scene must reproduce the source's rest-relative pose exactly; for a posed
character, `additive` is usually correct because it rebases the clip's first
frame onto the authored pose.

The retargeter calculates, for each mapping, `target_rest⁻¹ × source_rest`,
then transforms the source first-pose-relative local delta through that basis.
It does not copy the source quaternion. It writes:

- `rotation_space: godot4_absolute_local_bone_pose`;
- sign-continuous local quaternion tracks;
- `hip_position` for lateral/vertical pelvis motion;
- `root_position` only when real horizontal travel is detected;
- source action/range, mapping, FPS, pace, and root ownership metadata.

If the target uses different names, extend `MIXAMO_TO_TARGET` in the script
with an explicit mapping. Do not use a fuzzy name match for twist or finger
bones. Map those only after checking their rest chains and local axes.

## 4. Bake into an independent AnimationLibrary

Copy `scripts/bake_godot_motion_cache.gd` into the Godot project as a tool
script, then set its target scene and Skeleton3D constants (or adapt them to
CLI arguments before use). The required bake invocation is:

```bash
/Applications/Godot.app/Contents/MacOS/Godot --headless \
  --path '/absolute/path/project' \
  --script res://tools/bake_godot_motion_cache.gd -- \
  '/absolute/path/work/walking-body.godot-pose-motion.json' \
  'res://animations/mixamo_walking_body.tres' \
  mixamo_walking_body \
  res://demos/target_scene.tscn
```

The baker captures the target scene's current bone rotations and positions,
rebases each captured frame against frame zero, and writes tracks under the
target Skeleton3D. It includes Hips position when present, because omitting
pelvis bob while keeping leg rotations causes knee overextension and floating
feet. If `root_position` is present, it is keyed on
`RootMotionSampler:position` (change this path for a different scene contract)
and is not also applied to `Skeleton3D:Root` or the carrier Node3D.

The output animation name must be new. Keep `ots_carry_walk_cycle` and other
user-authored clips intact unless replacement was explicitly requested.

## 5. Direct-import path (only for identical rigs)

If the source FBX is a re-export of the exact target skeleton, compare the
target and imported Skeleton3D rest matrices, bone lengths, object scale, and
forward axis. Only if all four match may a project-specific Godot importer copy
lower-body tracks after import. It must pin the target Hips parent frame and
preserve the root sampler. A direct copy is not a substitute for the Blender
retargeter when a character was uploaded to Mixamo or has a different rest
pose.

## 6. Looping a gait

Choose a start and end at equivalent foot-contact phase (for example, the same
left heel strike). Do not simply use the whole downloaded action. If the final
pose is not the same phase, blend a short window of quaternion keys and set the
last local pose to the first. The repeated local animation can be looped, but
the cumulative root displacement must remain monotonic. A loop that resets the
root to zero every cycle will slide or teleport.

For a travelling clip, set animation length to `(frame_count - 1) / fps` so the
terminal root key is the seam boundary. For an in-place clip, use the full
sample period and a closing key only when the first/last local pose is actually
continuous. Verify the seam at 400% editor zoom and from behind the character.

## 7. Pace, trajectory, and foot contact

Compute `horizontal_root_distance / duration` from the cache. If a trajectory
owns travel, set its speed to that value or apply the same time scale to the
animation and trajectory. Never slow only the route while leaving the clip's
cadence unchanged. For a predefined trajectory, keep root motion as a neutral
sampler and project progress onto the route tangent; do not add root translation
to the carrier transform a second time.

Inspect both feet in a straight segment before testing a turn. A turn can show
sliding even when the straight segment is correct, because the route heading
and character-local forward axes are being mixed. Smooth the route heading or
use planted-foot correction; do not alter the mesh or bone lengths.

## 8. Validation checklist

Run `git diff --check` for generated project changes and the project's Godot
headless validation script. Then confirm:

1. source and target heights/scales are plausible;
2. every animation track path resolves to the target Skeleton3D;
3. knees bend backward and both feet contact the same floor plane;
4. there are no quaternion sign-flip spins or one-sided toe-outs;
5. the authored first-frame pose remains after closing/reopening Godot;
6. root travel has exactly one owner;
7. the same gait speed gives the same foot-contact timing in preview and export;
8. full-body mode does not fight enabled IK, attachment, or secondary-motion
   controllers.

Keep the cache and commands beside the output until the user accepts the clip;
they are the evidence needed to distinguish a bad source animation from a
retarget or scene-ownership error.
