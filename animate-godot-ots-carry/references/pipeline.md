# Gait video to reusable OTS carry animation

Use this workflow after reading the video instructions in the sibling
`capture-sam3d-godot-pose` skill. Paths below are placeholders.

## 1. Fit one carrier

Use a stable box around the male carrier only. The input video should show the
feet whenever possible; foot contact timing is more important than finger or
facial detail for this workflow.

```bash
MOCAP_PYTHON=/absolute/path/to/mocap-env/bin/python
CAPTURE_SKILL=/absolute/path/to/capture-sam3d-godot-pose

"$MOCAP_PYTHON" "$CAPTURE_SKILL/scripts/video_to_pose_stream.py" \
  /absolute/path/male-gait.mp4 \
  --fps 24 --nlf-fps 15 --sam3d-fps 1 \
  --bbox X1 Y1 X2 Y2 \
  --nlf-model /absolute/path/nlf-model.torchscript \
  --nlf-device mps \
  --sam3d-repo /absolute/path/sam-3d-body \
  --sam3d-checkpoint /absolute/path/model.ckpt \
  --mhr-model /absolute/path/mhr_model.pt \
  --sam3d-device cpu \
  --target-glb /absolute/path/male-carrier.glb \
  --root-motion foot-contact \
  --foot-lock-strength 1.0 \
  --output-dir /absolute/path/mocap/male-gait \
  --no-stream
```

Reject a fit if left/right identity flips, the cache is not labelled
`godot4_absolute_local_bone_pose`, foot contacts fire on lifted feet, or the
target rig's knees visibly twist. Tune from `--reuse-observations` rather than
rerunning both neural models for every solver adjustment.

## 2. Extract a periodic cycle

Choose two same-foot strikes at the same phase. The interval is half-open:
`start-frame` is included and `end-frame` is the matching seam frame.

```bash
"$MOCAP_PYTHON" "$CAPTURE_SKILL/scripts/extract_motion_cycle.py" \
  /absolute/path/mocap/male-gait/motion_pose_frames.json \
  /absolute/path/mocap/male-gait/carrier-cycle.json \
  --start-frame START --end-frame END \
  --animation-name ots_carrier_gait \
  --fit-planted-feet \
  --target-rig /absolute/path/male-carrier.glb \
  --skeleton-origin-y SKELETON_CHILD_Y \
  --ground-clearance 0.045
```

Keep `--ik-strength 0` initially. Increase it only when visual inspection shows
that captured leg rotations are worse than the analytical planting correction.
The cycle contains contact arrays and `recommended_speed_mps`; horizontal root
travel is intentionally removed because the Godot controller advances the
carrier along the authored trajectory.

For a deliberately non-periodic shot, skip cycle extraction and bake the full
cache with `loop: false`. The bake helper estimates average speed from cached
root positions when the cache has no explicit recommendation.

## 3. Bake the AnimationLibrary

Create a JSON bake config:

```json
{
  "base_scene": "res://shots/ots_carry.tscn",
  "skeleton_node_path": "CarryRigRoot/MaleCarrier/Skeleton3D",
  "track_skeleton_path": "CarryRigRoot/MaleCarrier/Skeleton3D",
  "animation_name": "ots_carrier_gait",
  "loop": true,
  "rebase_to_authored_pose": true,
  "bones": [
    "Hips", "LeftUpperLeg", "LeftLowerLeg", "LeftFoot",
    "RightUpperLeg", "RightLowerLeg", "RightFoot",
    "Spine", "Chest", "UpperChest", "Neck", "Head"
  ]
}
```

`skeleton_node_path` is resolved from the instantiated base scene.
`track_skeleton_path` is resolved from the AnimationPlayer. They may differ if
the player is nested. Restrict `bones` to the gait layer when the authored
carrier arms must remain available for contact IK.

```bash
GODOT=/absolute/path/to/Godot
OTS_SKILL=/absolute/path/to/animate-godot-ots-carry

"$GODOT" --headless --path /absolute/path/project \
  --script "$OTS_SKILL/scripts/bake_pose_cache.gd" -- \
  /absolute/path/mocap/male-gait/carrier-cycle.json \
  /absolute/path/mocap/male-gait/bake-config.json \
  res://animations/ots_carrier_gait.tres
```

The baked Animation metadata carries source FPS, left/right contacts,
recommended speed, local forward axis, and bake mode. The runtime controller
uses those values rather than guessing cadence from a generic walk cycle.

## 4. Install and tune the procedural controller

Copy `assets/ots_carry_controller.gd` into the project, attach it to a shot
controller Node3D, and wire the paths described in
[scene-contract.md](scene-contract.md). Do not enable carrier hand IK until the
pelvis attachment and secondary motion are stable.

Tune in this order:

1. Carrier gait and trajectory speed.
2. Left/right shoulder selection and pelvis calibration.
3. Position lag, then orientation lag and weight.
4. Legs, arms, head, and torso secondary amplitudes.
5. Female hip/thigh contact offsets.
6. Carrier hand targets, poles, and IK influences.

The female FK pose at the calibration frame is an authored input. Capture it
as the controller baseline before playback. Procedural motion must be additive
to that baseline and must never replace it with a neutral pose.

## Acceptance gates

- The baked animation drives the male skeleton only.
- Frame zero preserves the authored carrier carry pose when rebasing is enabled.
- The female pelvis remains attached through turns without orbiting around the
  scene origin.
- Pelvis lag trails motion without visible separation from the shoulder.
- Secondary motion responds to actual left/right contact metadata.
- A planted male foot has little world-space slip while trajectory progress
  continues through the opposite swing phase.
- Both-feet contact averages the two anchors instead of choosing one foot.
- Hand IK can be disabled without changing the male gait or female baseline.
- The output remains a coarse reference animation suitable for video generation;
  it does not claim physical simulation or production-quality contact forces.
