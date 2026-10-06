---
name: migrate-mixamo-godot-motion
description: Retarget a Mixamo FBX animation into a Godot 4 humanoid without twisted knees, scale errors, root-motion double travel, or loop foot sliding. Use when a user provides a Mixamo FBX and wants any part of its motion—or the complete body motion—baked into a target Godot scene or AnimationLibrary.
---

# Migrate Mixamo Motion to Godot

Use this skill for a complete, reproducible Mixamo-to-Godot motion migration.
It is deliberately more careful than copying imported AnimationPlayer tracks:
Mixamo and a target GLB often have different rest-bone bases, armature object
scale, root hierarchy, and forward axes. A raw quaternion copy is therefore
not a retarget.

The deliverable is a new Godot `AnimationLibrary` (never overwrite an existing
clip unless the user explicitly asks), plus a short validation report covering
scale, bone mapping, root ownership, foot contacts, and loop behavior.

## Resources in this skill

- `scripts/mixamo_to_godot_root_motion.py` — Blender preprocessing. It keeps
  the FBX unchanged, normalizes the armature scale, removes duplicate
  armatures, and inserts a clean parent `Root` above Mixamo Hips.
- `scripts/retarget_mixamo_fbx.py` — Blender-evaluated per-bone retargeter.
  It computes first-pose-relative local rotations, calibrates every mapped
  rest basis, preserves pelvis sway, extracts real root travel, and enforces
  quaternion sign continuity.
- `scripts/bake_godot_motion_cache.gd` — rebases the cache onto the target
  scene's authored rest/pose and writes a Godot AnimationLibrary. It keeps
  root travel on a dedicated sampler so a trajectory controller does not move
  the character twice.
- [references/pipeline.md](references/pipeline.md) — complete commands and
  decision points.
- [references/troubleshooting.md](references/troubleshooting.md) — symptoms,
  causes, and safe fixes for the failures that commonly look like “bad gait”.

## Required workflow

1. **Inspect before editing.** Identify the source action, frame range, FPS,
   whether travel is on `Root`, `Hips`, or neither, and the target Skeleton3D
   path. Do not assume the first FBX armature or the default 1–250 frame range
   is correct. Record the target scene's authored pose and height.
2. **Preprocess a copy.** Run the Blender root preprocessor unless the FBX has
   already been verified to contain a correctly scaled clean root. Never alter
   the user's downloaded FBX in place. Preserve the action's exact frame range.
   A Mixamo armature object at `0.01` scale must be applied together with its
   animated location channels; applying object scale alone creates 100× root
   errors.
3. **Choose motion ownership.** Decide explicitly whether world travel belongs
   to the animation root or to a Godot `Path3D`/trajectory controller. There
   must be exactly one owner. For a free locomotion scene, include the root
   channel. For an OTS/carry scene with a predefined trajectory, bake root
   travel to `RootMotionSampler` or omit it and let the trajectory own travel;
   never key both the skeleton root and the trajectory.
4. **Retarget in Blender space, not by raw track copy.** Use
   `retarget_mixamo_fbx.py` with `--bone-set body` for a normal full-body
   migration, `--bone-set lower` when authored upper-body/IK motion must stay
   intact, and `--include-root` only when the root-motion owner is the clip.
   The retargeter maps both `mixamorig:*` and already-renamed Humanizer bones,
   computes a per-bone rest-basis calibration, and applies motion relative to
   the source clip's first pose. Do not “fix” a twisted knee by adding an
   arbitrary global Euler rotation; correct the source/target rest basis.
5. **Bake onto the target's authored pose.** The first captured frame is a
   delta reference. Rebase every driven bone onto the target Skeleton3D's
   current local rest/pose, including Hips position when pelvis bob is useful.
   This prevents a T-pose, source rest quaternion, or Mixamo shoulder pose
   from replacing the target character's deliberately authored pose.
6. **Handle full motion deliberately.** Full-body mode may drive hips, spine,
   chest, neck, head, shoulders, arms, hands, and any mapped auxiliary bones.
   Do not drive bones owned by runtime IK or a carry constraint in the same
   clip unless the user specifically wants the baked interaction. For fingers
   and twist bones, map only exact rest-compatible chains and validate them;
   silently guessing their axes is worse than leaving them to the target's
   authored pose.
7. **Make a loop only from matching phase.** For a looping gait, choose a
   source interval whose first and last frames have the same planted-foot
   phase. Keep the terminal frame as the loop boundary only when it is the
   true matching pose; otherwise blend a short quaternion seam window and
   close the final key to frame zero. Keep cumulative root distance separate
   from the repeated local pose. Never loop world translation back to zero.
8. **Match pace and contacts.** Measure horizontal root displacement divided by
   clip duration. Use that value to set the controller/path speed, or apply one
   common time scale to both the gait and root channel. Do not change only the
   trajectory speed: that produces foot sliding. Check heel/toe contact on both
   sides, pelvis height, knee direction, and lateral drift from behind.
9. **Validate in Godot.** Run the headless baker and a project validation
   script, then preview the resulting animation in the editor at its intended
   speed. Reopen the scene to ensure the authored pose survives. Test one
   straight segment and one turn separately. A successful bake must have no
   missing track paths, no 0.01/100× scale, no backwards knees, no sign-flip
   spins, and no root double-advance.
10. **Report provenance.** Store source FBX, source action/range, FPS, bone set,
    retarget mode, root owner, recommended speed, and seam method as animation
    metadata. Keep the source, preprocessed copy, cache, bake command, and
    validation output so the result can be regenerated.

## Non-negotiable invariants

- Never copy Mixamo local quaternions directly into a different rig.
- Never apply armature object scale without rescaling animated bone locations.
- Never let both animation root motion and a trajectory controller advance the
  same character.
- Never solve a rest-basis error by changing the target mesh scale or bone
  lengths; that changes the character rather than the motion.
- Never replace an existing user-authored animation or carry pose implicitly.
- Use absolute-local cache metadata
  `rotation_space: godot4_absolute_local_bone_pose`; reject ambiguous caches.
- Preserve quaternion sign continuity frame-to-frame to prevent 360° spins.
- Treat a user-requested “whole motion” as whole mapped body motion, not an
  excuse to override explicit IK/attachment ownership.

For exact command examples and the target-scene contract, read
[references/pipeline.md](references/pipeline.md). For diagnosis, read
[references/troubleshooting.md](references/troubleshooting.md).
