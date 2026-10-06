# Mixamo migration troubleshooting

Diagnose the first visible failure, not the final symptom. A “zombie gait” is
often a rest-basis or scale error upstream.

| Symptom | Likely cause | Corrective action |
|---|---|---|
| Both knees point forward/backward or one knee twists | Raw Mixamo quaternion copied into target basis; mirrored rest chain | Retarget through per-bone rest calibration. Compare source and target rest matrices. Do not rotate the mesh or add a global Euler patch. |
| Character is 100× too large, tiny, or feet are kilometres away | FBX armature object scale was applied without scaling animated location keys | Re-run `mixamo_to_godot_root_motion.py` on a fresh copy. Verify armature scale is 1.0 and the source action frame range is preserved. |
| Gait plays but feet slide | Route speed differs from root/clip pace, or root is reset at loop seam | Use measured root distance / duration. Scale gait and travel together. Keep cumulative root displacement monotonic. |
| Character advances twice as far | Both animation root and trajectory/controller move the carrier | Choose one root owner. For a path scene, consume root on `RootMotionSampler` or omit it; never also translate the carrier from the same channel. |
| Character does not advance at all | In-place Mixamo clip has no root travel; trajectory was disabled | Either enable the trajectory owner or use a genuinely travelling clip with `--include-root`. Do not invent root travel from pelvis bob. |
| Pelvis looks frozen and legs overextend | Hips position track was omitted | Preserve `hip_position` as a target Hips position track, rebased onto the authored target pose. |
| Whole body snaps to T-pose or Mixamo stance | Absolute source pose was baked over the target's authored pose | Use additive first-frame rebasing. Capture the target scene pose before baking and keep the first source frame as the delta reference. |
| Upper body jerks while lower body is acceptable | Two animation/IK systems own the same spine/arms, or partial tracks leave stale keys | Use `--bone-set body` for a single full-body owner, or lower-only plus explicitly authored upper body. Disable competing IK while validating the bake. |
| Hands or fingers explode | Finger/twist rest axes differ or names were fuzzy-matched | Leave them unmapped unless exact rest-compatible chains are verified. Let target finger presets or IK own them. |
| One-frame spin at a seam | Quaternion signs alternate even though rotations are equivalent | Enforce dot-product sign continuity for every bone before baking; close the seam with the first quaternion. |
| Loop pauses or slides at the boundary | Wrong frame range, duplicated frozen tail, or nonmatching foot phase | Read the action's actual frame range, choose same-contact endpoints, and set travelling clip length to `(N-1)/fps`. |
| Imported animation has no visible tracks | Track paths refer to source node names, not target Skeleton3D paths | Rebuild paths as `TargetSkeletonPath:BoneName`, then inspect `Animation.get_track_path()` in Godot. |
| Character walks sideways or backwards | Blender/Godot forward-axis conversion was assumed instead of measured | Inspect source root displacement and target forward direction. Apply the documented axis conversion once, not once per stage. |
| Root motion looks right in Blender but not Godot | FBX import conversion, node scale, or target local basis differs | Use Blender only to evaluate and retarget; bake target-local rotations and preview the Godot result. Do not trust the Blender viewport orientation as the target basis. |
| Turning a corner causes slide or wobble | Route tangent/heading changes abruptly; local gait is fine | Test straight travel first, smooth route heading or planted-foot progress at corners, then retest. Do not “fix” a route turn by changing bone lengths. |
| Reopening the scene loses the starting pose | Pose existed only in editor state or an external `.gdpose` was not baked | Serialize the authored target pose in the scene or bake it as the animation's first-frame base; verify after reopening. |

## Stop conditions

Stop and ask for the target scene/rig when any of these is missing:

- a target Skeleton3D or target GLB with the actual bone hierarchy;
- the target scene's intended animation/root-motion owner;
- a source action with a readable frame range;
- enough information to distinguish a full-body migration from a lower-body or
  IK-owned migration.

Do not silently export a plausible-looking animation onto the wrong skeleton.
