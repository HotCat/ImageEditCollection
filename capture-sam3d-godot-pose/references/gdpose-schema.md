# Godot `.gdpose` mapping and compatibility

## What the converter produces

The output is a `godot-pose-document` version 1 JSON file. Each named pose may contain:

- `mode`: `fk`, `ik`, or `hybrid`;
- `reset_to_rest`: whether Godot resets local bone poses first;
- `modifiers`: named `SkeletonModifier3D` active states;
- `ik`: local transforms for scene-level PoseControls nodes;
- `bones`: optional local FK overrides keyed by bone name.

The SAM adapter produces these 12 generic humanoid controls:

```text
pelvis_target       center_back_target
neck_target         head_target
l_arm_marker        l_arm_pole
r_arm_marker        r_arm_pole
l_feet_marker       l_feet_pole
r_feet_marker       r_feet_pole
```

This naming matches the OTS Simulator PoseControls rig and can be adapted to another Godot receiver. MHR70 nose, shoulders, elbows, wrists, hips, knees, ankles, and big-toe tips determine the controls. Elbow and knee poles come from the observed bend direction. `center_back_target` uses the shoulder center because that IK chain ends at the upper chest. `neck_target` is a look direction toward the nose, not a neck position.

The representation does not encode an activity label. Standing, running, sitting, lying, crouching, jumping, and carried poses use identical fields.

## Full-rig compatibility boundary

A template may describe 56 bones—or another count—in top-level `rig.bones`. The generated pose remains compatible when Godot evaluates these pelvis, torso, neck, arm, and leg controls over the complete skeleton.

The converter does **not** infer independent local rotations for every bone. MHR70 does not resolve spine distribution, clavicle roll, forearm twist, finger articulation, hidden-joint depth, hair bones, or contact forces from one view. The generated `bones` object is normally empty or contains only a `Hips` axial-roll hint. Use FK controls, multi-view fitting, or later mocap/optimization for detailed local rotations.

Compatibility requires more than a bone count. The scene must expose the expected PoseControls and modifier names, or both converter and receiver must be adapted. Pass the real project document as `--template` to preserve rig metadata, character paths, endpoints, and existing profiles.

## Coordinates and orientation

- Default `--mhr-axis mhr`: MHR body/world convention, Y up.
- `--mhr-axis camera`: invert MHR Y and Z like the MediaPipe camera path. Use only when an exporter has converted points to that convention.
- `--mirror-x`: flip placement across character-local X. Use after visual comparison, not merely because the source is a selfie.
- `--height`: nose-to-ankle span in Godot units, not crown-to-sole anatomical height. Calibrate it against the target rig.
- `--floor-y`: lowest ankle target height. The default `0.08` matches the originating demo.
- `--pole-distance`: elbow/knee pole offset. Increase cautiously when a nearly straight limb produces an unstable bend plane.

Joint positions can leave rotation around the torso's long axis ambiguous, especially in prone, supine, side-lying, diving, or carried poses. `--torso-roll-degrees` adds a local `Hips` Y rotation and changes the profile to `hybrid`. It requires `--target-glb` so the converter can compose that correction onto the imported Hips rest-local quaternion and emit the resulting absolute-local quaternion. Treat it as an explicit visual correction, not an automatic classifier.

## Occlusion and template semantics

Without `--activate`, the converter preserves the template's `active_pose`. With `--activate`, it selects the new profile. Existing profiles and unknown top-level metadata are copied unchanged.

Detector-provided low-confidence controls are replaced with deep copies of the active template pose's corresponding controls when available. Official SAM records may contain no per-joint confidence, so use repeatable `--uncertain LANDMARK` flags after visual inspection. Every affected control must exist in the active template or conversion fails instead of silently accepting unreliable joints. The profile records copied controls in `retained_template_controls` and explicit joints in `source.uncertain_landmarks`.

For multiple people, run one inference per box and create one profile per target character. A bounding box reduces identity mixing but does not make hidden joints observable. Reject records where landmarks switch between people.

## Localhost streaming

`--send HOST:PORT` sends one newline-delimited JSON `pose.apply` message using protocol `godot-pose-stream/1`. The originating project uses editor port `7007` and runtime port `7008`.

The receiver should answer `pose.applied` and report applied or missing bones, controls, and modifiers. Treat missing required names as a compatibility failure. Keep this unauthenticated protocol bound to localhost; use an authenticated relay for remote input.

### Godot 4 FK rotation invariant

`Skeleton3D.set_bone_pose_rotation()` consumes the bone's **absolute local pose rotation** in parent space. It does not consume an animation delta relative to the imported rest rotation. Therefore an FK sender must:

- send the solved `desired_local` quaternion directly;
- send the target GLB/Godot rest-local quaternion for every unobserved bone;
- preserve quaternion order as `x, y, z, w`; and
- never substitute identity for a rest quaternion unless that imported rest rotation is actually identity.

Do not send `inverse(rest_local) * desired_local`. Resetting the skeleton to rest before applying a frame does not make delta quaternions or identity overrides valid: the subsequent setter replaces the local rotation. Violating this rule destroys imported bone-roll axes, most visibly on thighs, wrists, hands, feet, fingers, and toes from the first frame.

Motion caches produced by the video pipeline declare:

```json
"rotation_space": "godot4_absolute_local_bone_pose"
```

Reject an unlabelled or differently labelled cache instead of assuming it is safe to replay.
