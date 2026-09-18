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
6. Interpolate observations, median/Gaussian-smooth positions, enforce quaternion hemisphere continuity, reject isolated quaternion outliers, apply bidirectional slerp smoothing, and damp foot rotation during inferred contacts.
7. Emit every target bone in every frame, using its actual rest-local quaternion when it is not observed.

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

- The current stream solves rotations, not world/root translation. Foot contacts damp rotation but do not perform full foot locking or root-motion recovery.
- Monocular depth, axial roll, crossed limbs, fast motion blur, and long occlusion remain ambiguous. Use a tight stable box, inspect the observation cache, and prefer multi-view capture when exact depth matters.
- NLF does not observe finger articulation or detailed toe roll. Those bones intentionally preserve target rest rotations rather than receiving guessed deltas.
- Hair, garment, face, and accessory bones remain at rest unless another trusted source drives them.
- For two-person contact, solve each character independently and repair hand/body contact in Godot. Do not let one box alternate between subjects.
- Treat the result as a strong coarse motion layer. Use authored constraints, contact solving, or manual FK for production-quality hands, feet, and object interactions.
