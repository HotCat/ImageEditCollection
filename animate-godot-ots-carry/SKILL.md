---
name: animate-godot-ots-carry
description: Build a reusable Godot 4 over-the-shoulder carry reference animation from a male gait video. Use when Codex must invoke capture-sam3d-godot-pose, bake an in-place carrier gait, attach a carried character's pelvis to either shoulder with tunable lag, add foot-rhythm secondary motion and optional carrier hand IK, and advance the carrier along a planned trajectory with planted-foot root correction.
---

# Animate Godot OTS Carry

Produce a stable render-agnostic carry block for downstream video generation.
Treat the captured male gait as the primary motion. Keep the female's authored
carry pose, contact constraints, and secondary motion procedural.

## Required dependency

Use the sibling `capture-sam3d-godot-pose` skill for video inference and
retargeting. Read its `SKILL.md` and `references/video-motion-streaming.md`
before running inference. Do not copy or reimplement its NLF/SAM3D solver.

The essential invariant is absolute local Godot bone rotation:
`godot4_absolute_local_bone_pose`. Reject unlabelled or rest-delta caches.

## Workflow

1. Inspect the gait video and select the male carrier with one stable bounding
   box. Feet must remain visible often enough to infer contacts.
2. Use `capture-sam3d-godot-pose` to create `motion_pose_frames.json` with
   foot-contact root motion against the exact male target GLB.
3. For reusable walking, choose two same-foot strikes at matching phase and run
   the dependency's `extract_motion_cycle.py`. Preserve its contact arrays and
   `recommended_speed_mps`. Do not loop absolute world translation.
4. Pose and align both characters at frame zero in a dedicated carry scene.
   Keep the female FK pose serialized independently of the gait library.
5. Bake only the intended male bones with `scripts/bake_pose_cache.gd`. Rebase
   captured deltas onto the authored frame-zero carrier pose. Normally omit arm
   tracks because carrier hand IK owns those bones.
6. Copy `assets/ots_carry_controller.gd` into the Godot project and wire the
   scene contract. Calibrate the female pelvis to `LeftShoulder` or
   `RightShoulder`, then tune position and orientation lag separately.
7. Tune foot-contact-driven female leg, arm, head, and torso motion as small
   additive offsets from her authored FK baseline.
8. Add optional male two-bone arm IK: one hand targets a female hip marker and
   the other targets a thigh marker. Enable it only after the carry attachment
   is stable.
9. Author a `Path3D`. Advance at the captured recommended speed, anchor each
   planted male foot in world space, and correct progress along the path tangent.
   Average both anchors during double support.
10. Preview in the editor, verify contacts and reopening behavior, then expose
    the tunable parameters needed for shot-specific iteration.

Read [references/pipeline.md](references/pipeline.md) for commands, bake config,
and acceptance gates. Read [references/scene-contract.md](references/scene-contract.md)
when creating or repairing the Godot hierarchy, controller paths, or hand IK.

## Non-negotiable constraints

- Capture only the male gait from the input video. Do not try to solve the
  carried female from the same monocular gait clip.
- The female pelvis is constrained to the evaluated carrier shoulder in world
  space. Apply orientation around the pelvis pivot, never around world origin.
- Secondary motion is additive to a saved female FK baseline and driven by male
  contact rhythm. It must not reset her to T-pose or a neutral pose.
- Keep repeated in-place bone motion separate from trajectory travel.
- Use actual left and right foot contact states for root correction. Do not
  infer forward distance from pelvis bob or lateral sway.
- Hand IK is optional and reversible. Disabling it must not alter the gait,
  pelvis attachment, or female baseline.
- Describe the result as a coarse H3/reference animation, not physically exact
  simulation or production mocap.

## Included resources

- `scripts/bake_pose_cache.gd`: bake absolute-local motion JSON to an
  AnimationLibrary and preserve contact/speed metadata.
- `assets/ots_carry_controller.gd`: editor/runtime pelvis follow, secondary
  motion, hand-contact targets, Path3D travel, and planted-foot progress solve.
- `references/pipeline.md`: inference, cycle extraction, bake, tuning, and QA.
- `references/scene-contract.md`: hierarchy and solver ownership contract.
