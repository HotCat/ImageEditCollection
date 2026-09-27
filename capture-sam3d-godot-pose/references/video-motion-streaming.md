# Video motion capture and Godot `pose.frame` streaming

Use this mode when the input is a video and the desired result is a live, temporally stable FK preview rather than one `.gdpose` profile. The pipeline keeps inference outside Godot and does not create or modify an Animation resource.

## Inputs and compatibility

Provide all of the following explicitly:

- one motion video and one fixed full-resolution `X1 Y1 X2 Y2` box selecting a single person;
- an NLF TorchScript model with the `smpl_24` skeleton;
- the official SAM 3D Body repository, checkpoint, and its MHR model;
- the exact skinned target GLB used by Godot; and
- a Godot pose-stream receiver that accepts newline-delimited `godot-pose-stream/1` `pose.frame` messages.

The Python environment needs NumPy, OpenCV, Torch, and Torchvision plus the dependencies of NLF and SAM 3D Body. Model weights are external assets and must remain outside the skill and source repository. Follow their upstream licenses and access terms.

The target skin is 56 bones by default. Pass `--expected-bones 0` only when intentionally adapting another rig. The solver recognizes the humanoid names in `MHR_TO_GODOT`, including `Hips`, the spine, head, shoulders, arms, hands, legs, feet, and toes. Unrecognized bones are still emitted, but remain at their imported rest-local rotation.

## Solver architecture

`scripts/video_to_pose_stream.py` performs these stages:

1. Decode the selected duration at the requested output rate.
2. Run NLF densely, normally at 15 FPS, for SMPL-24 joint positions and uncertainty.
3. Run SAM 3D Body sparsely, normally at 1 FPS, for MHR orientation anchors.
4. Retarget SAM axial twist only for `Hips`, `Spine`, `Chest`, `UpperChest`, `Neck`, and `Head`.
5. Fit arms, hands, legs, and feet parent-first from NLF segment directions using minimal swing. Do not copy SAM limb roll into a differently oriented target rig.
6. Infer parent-node root displacement from pelvis motion and stabilize it with planted-foot contact constraints; keep pelvis wobble in the local Hips quaternion.
7. Optionally map cumulative gait distance to a cubic Bezier waypoint path and derive character heading from its tangent.
8. Interpolate observations, median/Gaussian-smooth positions, enforce quaternion hemisphere continuity, reject isolated quaternion outliers, apply bidirectional slerp smoothing, and damp foot rotation during inferred contacts.
9. Emit every target bone in every frame, using its actual rest-local quaternion when it is not observed.

On Apple Silicon, the official NLF multiperson wrapper may cast through float64, which MPS cannot execute. The included observer calls NLF's scripted crop model directly so dense inference stays float32/float16 on MPS. The MHR TorchScript used by SAM 3D Body also contains float64 operations, so `--sam3d-device cpu` is the safe default there. CUDA may be used when the installed upstream stack supports it.

## Absolute-local rotations are mandatory

Godot 4 `Skeleton3D.set_bone_pose_rotation()` replaces a bone's local pose rotation. Every quaternion sent by this pipeline is therefore an **absolute local bone rotation in parent space**:

```text
outgoing = desired_local
```

Never convert it to `inverse(rest_local) * desired_local`. Never emit identity for an unobserved bone unless the imported GLB rest quaternion is identity. A prior `reset_to_rest` does not change this setter contract. Rest-relative deltas interpreted as final rotations erase bone-roll axes and twist thighs, wrists, feet, fingers, and toes immediately.

Every generated cache and wire frame is labelled:

```json
"rotation_space": "godot4_absolute_local_bone_pose"
```

The replay client rejects legacy or unlabelled caches. When adapting a receiver, reject other rotation spaces too. Verify a new avatar once by comparing GLB rest-local quaternions with a Godot `pose.capture` taken after `reset_to_rest`.

## Fit and cache

Use the Python environment in which NLF and SAM 3D Body both import. Replace every path and box:

```bash
MOCAP_PYTHON=/absolute/path/to/mocap-environment/bin/python
SKILL_DIR=/absolute/path/to/capture-sam3d-godot-pose

"$MOCAP_PYTHON" "$SKILL_DIR/scripts/video_to_pose_stream.py" \
  /absolute/path/motion.mp4 \
  --duration 4 --fps 30 --nlf-fps 15 --sam3d-fps 1 \
  --bbox X1 Y1 X2 Y2 \
  --nlf-model /absolute/path/nlf_l_multi_0.3.2.torchscript \
  --nlf-device mps \
  --sam3d-repo /absolute/path/sam-3d-body \
  --sam3d-checkpoint /absolute/path/model.ckpt \
  --mhr-model /absolute/path/assets/mhr_model.pt \
  --sam3d-device cpu \
  --target-glb /absolute/path/target-avatar.glb \
  --output-dir /absolute/path/mocap-cache \
  --no-stream
```

The output directory contains `nlf_sam3d_observations.json` and `motion_pose_frames.json`. Re-run with the same inputs and `--reuse-observations` to tune solver or stream settings without repeating model inference. Review `diagnostics.post_filter_segment_error`, `driven_bones`, `rest_bones`, and inferred foot contacts before accepting the motion.

Omit `--no-stream` to connect immediately after fitting. Override `--character-path`, `--skeleton-path`, `--controls-path`, `--host`, and `--port` for the target scene.

## Replay a verified cache

Start the Godot editor or runtime receiver, then replay without loading either model:

```bash
python3 "$SKILL_DIR/scripts/video_to_pose_stream.py" \
  --stream-cache /absolute/path/mocap-cache/motion_pose_frames.json \
  --host 127.0.0.1 --port 7007 \
  --character-path IK_character \
  --skeleton-path Skeleton3D \
  --controls-path ../PoseControls
```

Use `--loop` for repeated preview. The client waits for the receiver's `hello`, streams at the cached FPS, sets `reset_to_rest` only on the first transmitted frame, and requests an acknowledgement on the final non-looped frame. Keep the unauthenticated socket on localhost.

The receiver must enter FK mode and keep IK modifiers from overwriting streamed bones. Each frame should apply all bone rotations in parent-local space. Missing bones or an unexpected count are compatibility failures, not warnings to ignore.

## Limits and repair strategy

- Root motion is a monocular estimate, not surveyed ground truth. Foot contacts reduce drift, but long occlusions, moving cameras, sliding shoes, and uncertain depth still require review.
- Monocular depth, axial roll, crossed limbs, fast motion blur, and long occlusion remain ambiguous. Use a tight stable box, inspect the observation cache, and prefer multi-view capture when exact depth matters.
- NLF does not observe finger articulation or detailed toe roll. Those bones intentionally preserve target rest rotations rather than receiving guessed deltas.
- Hair, garment, face, and accessory bones remain at rest unless another trusted source drives them.
- For two-person contact, solve each character independently and repair hand/body contact in Godot. Do not let one box alternate between subjects.
- Treat the result as a strong coarse motion layer. Use authored constraints, contact solving, or manual FK for production-quality hands, feet, and object interactions.

## Root motion and Bezier trajectory programs

`--root-motion foot-contact` is the default. It scales NLF geometry to the
target GLB, extracts pelvis displacement, and blends it with planted-foot
constraints. `--root-motion pelvis` uses raw pelvis displacement, and
`--root-motion off` keeps the character parent stationary. The local Hips
rotation still carries captured pelvic wobble in all three modes.

The optional `--trajectory PATH.json` treats gait distance like a feed axis:
captured footfalls determine progress over time while trajectory waypoints
determine the spatial toolpath. Bézier waypoint handles are vectors relative
to their position:

```json
{
  "type": "bezier",
  "distance_mode": "gait",
  "pace_scale": 1.0,
  "contact_correction": 1.0,
  "local_forward": [0, 0, -1],
  "waypoints": [
    {"position": [0, 0, 0], "out_handle": [0, 0, 1.2]},
    {"position": [1.5, 0, 2.8], "in_handle": [-0.8, 0, -0.9], "out_handle": [0.8, 0, 0.9]},
    {"position": [3, 0, 1], "in_handle": [-0.8, 0, 0.3]}
  ]
}
```

Set `type: "linear"` to join waypoint positions with true straight segments;
`in_handle` and `out_handle` are then ignored. This is useful for diagnosing
root-speed and foot-contact behavior without curve geometry. `type: "bezier"`
retains the cubic path shown above.

Use `distance_mode: "gait"` (the default) and `pace_scale: 1.0` to preserve
captured stride distance and cadence. A longer path remains partially
traversed after one clip. `distance_mode: "fit"` forces the entire path into
the clip. Set `speed_profile: "constant"` when a shot requires equal root
distance per frame, or `"captured"` to retain source speed changes. A project editor may add
`scene_origin_node` so its receiver starts the character at the visible first
waypoint instead of its previous runtime position.

Trajectory feed is directed root displacement, not cumulative pelvis variation.
Vertical bob and lateral hip sway do not become forward distance, while small
backward planted-foot corrections remain in the feed to counter local foot
movement. Accumulating every variation creates visible sliding even when the
contact solver itself is stable.

After absolute-local FK retargeting and temporal filtering, the solver evaluates
the target rig's actual `LeftFoot` and `RightFoot` origins. During each detected
contact it corrects distance only along the curve tangent. This second contact
pass accounts for target limb proportions without moving the character sideways
off the authored path. `contact_correction` ranges from `0.0` to `1.0`; use
`1.0` for the strongest lock. `local_forward` must match the avatar convention,
normally Godot `-Z`, or the correction will be evaluated in the wrong direction.
The accumulated correction persists when support changes between feet, which is
essential when the source camera tracks the walker and raw pelvis displacement
therefore under-reports actual travel.

In `fit` mode, contact locking can otherwise leave the character short of the
last waypoint. The solver restores the residual endpoint distance primarily in
frames where neither foot is planted, with a small planted-frame contribution
to avoid velocity bursts. Use `gait` mode when preserving source pace matters
more than reaching the authored endpoint.

Walking scenes may set `upright_root: true` to remove pitch/roll inherited from
an earlier static pose. With `ground_lock: true`, the solver evaluates the
retargeted target rig's Foot and Toes origins after FK filtering and emits
vertical root offsets that place the lowest support sole at `ground_y`.
`skeleton_origin_y` is the target scene's Skeleton3D child offset. Optional
`max_torso_tilt_degrees` and `max_head_up_degrees` limits correct monocular
axial-anchor bias without changing the fitted upper-leg global rotations.

Ground lock fixes floating, but horizontal slide is separate. Set
`foot_ik: true` to run target-rig analytical two-bone IK after root planning.
Each contact interval anchors the ankle in world XZ, rotates UpperLeg and
LowerLeg while preserving the inferred knee bend plane, and restores the
fitted Foot global orientation. Grounding is then recalculated from the
corrected Foot and Toes. This removes lateral and tangent support-foot drift
without moving the character root away from the authored line.

Use `--trajectory-heading tangent` to turn the character along the path or
`--trajectory-heading none` to preserve its initial facing direction. Tangent
mode sends an explicit parent-space `heading_direction` and a local
`local_forward` axis rather than assuming the character's authored scene yaw is
already aligned. The default forward axis is Godot's `-Z`; the receiver rotates
that axis onto the tangent while preserving the character's initial pitch and
roll. The wire message also carries `pose.root_motion.position`, `rotation_y`,
and `space: "character_parent"`, applied relative to the starting Node3D
transform.

### Reuse periodic locomotion

Walking and running should not loop a long absolute root-motion cache: the
loop boundary would teleport the character from the path end to its start.
Choose two frames at the same gait phase, normally consecutive strikes of the
same foot, then extract the half-open interval:

```bash
python3 scripts/extract_motion_cycle.py \
  /absolute/path/motion_pose_frames.json \
  /absolute/path/walk_cycle.json \
  --start-frame START --end-frame END \
  --animation-name walk_cycle \
  --fit-planted-feet \
  --skeleton-origin-y SKELETON_CHILD_Y \
  --ground-clearance 0.045
```

The extractor averages the two boundary quaternions for an exact seam and
zeros horizontal root translation. With `--fit-planted-feet`, it derives stance
from target-avatar sole height and backward foot speed, measures
`recommended_speed_mps`, and solves three repeated copies before retaining the
middle one. The default `--ik-strength 0` uses this information only for speed
and grounding so the captured thighs, shins, and feet remain intact. Set a
non-zero strength only after visually validating that positional planting does
not distort the captured knee motion. A Godot project
should loop these absolute-local bone rotations while a separate editor-capable
locomotion controller advances the character at the recorded speed.
