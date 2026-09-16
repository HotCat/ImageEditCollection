---
name: capture-sam3d-godot-pose
description: Capture one explicitly selected person's coarse 3D pose from a still image with Meta SAM 3D Body/MHR70 and append an editable IK or hybrid profile to a Godot 4 `.gdpose` document. Use for standing, walking, running, sitting, lying, crouching, kneeling, jumping, diving, carried, or assisted poses, including multi-person images with partial occlusion. Supports manual subject boxes, explicit occlusion fallbacks, coordinate and body-facing correction, template preservation, validation, and localhost preview streaming. Produces controls for a full humanoid rig but does not claim to infer every local bone rotation from one image.
---

# Capture SAM 3D Godot Pose

Turn one selected person's MHR70 landmarks into a coarse Godot pose that can be previewed immediately and refined with IK markers and FK controls. Apply the same pipeline to standing, locomotion, seated, recumbent, crouched, airborne, and carried poses; pose category does not change the data format.

## Read before execution

- Read [references/sam3d-setup.md](references/sam3d-setup.md) before installing, patching, or running SAM 3D Body.
- Read [references/gdpose-schema.md](references/gdpose-schema.md) before adapting control names, changing axes, or making rig-compatibility claims.

## Core workflow

1. Inspect the full-resolution image and select exactly one person. Record one explicit `X1 Y1 X2 Y2` box when there is more than one person, overlap, partial occlusion, or an unreliable automatic crop. A box—not a sex or role label—selects the subject.
2. Run `scripts/sam3d_export_json.py` once for that person. Use another inference pass and box for every other character. Do not treat a two-person image as one combined skeleton.
3. Inspect the resulting 2D/3D landmarks. Require at least 70 `pred_keypoints_3d` entries and confirm that the shoulders, wrists, hips, knees, and ankles all belong to the selected person. Reject blended or anatomically impossible output.
4. Identify visibly hidden, blended, or misassigned joints. Because official SAM output may omit joint confidence, pass each known uncertainty explicitly, for example `--uncertain left_wrist --uncertain right_ankle`. These controls are copied from the active template pose, making the result deterministic.
5. Convert with `scripts/image_to_gdpose.py`. Supply the target project's existing `.gdpose` with `--template`. Write a candidate file first so the tracked document remains recoverable during review.
6. Resolve coordinate ambiguity by visual comparison. Use `--mirror-x` only for a true left/right reversal, `--mhr-axis camera` only for camera-convention JSON, and `--torso-roll-degrees` only to correct body-facing ambiguity around the torso's long axis.
7. Validate with `scripts/validate_gdpose.py`, using the target rig's expected bone count. Preview the candidate in Godot and treat missing controls or modifiers in the receiver reply as a failed retarget.
8. Refine hidden limbs, depth, contacts, spine curvature, head direction, hands, feet, and detailed FK manually. Preserve the source image, bounding box, MHR JSON, and candidate `.gdpose` for reproducibility.

## General pose coverage

The control mapping is independent of the activity. Use it for:

- standing, walking, running, and asymmetric locomotion frames;
- sitting, squatting, crouching, kneeling, and starts;
- lying, prone, supine, side-lying, diving, and airborne poses;
- carried or assisted poses such as over-the-shoulder and piggyback carries.

For multi-person and carried poses, infer each character separately. Tight subject boxes reduce identity mixing but cannot reconstruct hidden joints. Mark uncertain joints, retain a neutral or nearby authored template for them, and repair contacts in Godot after both characters are present.

## Commands

Set `SKILL_DIR` to this skill folder and replace every example path and bounding box:

```bash
SAM_PYTHON=/absolute/path/to/sam3d-environment/bin/python
SAM_REPO=/absolute/path/to/sam-3d-body
SKILL_DIR=/absolute/path/to/capture-sam3d-godot-pose

"$SAM_PYTHON" "$SKILL_DIR/scripts/sam3d_export_json.py" \
  /absolute/path/reference.png \
  --sam3d-repo "$SAM_REPO" \
  --checkpoint-path /absolute/path/model.ckpt \
  --mhr-path /absolute/path/assets/mhr_model.pt \
  --bbox X1 Y1 X2 Y2 \
  --inference-type body --device cpu \
  --output /absolute/path/work/selected-person.mhr70.json
```

Append and validate a named candidate while preserving the template's current `active_pose`:

```bash
python3 "$SKILL_DIR/scripts/image_to_gdpose.py" \
  /absolute/path/work/selected-person.mhr70.json \
  --format sam3d-mhr --person-index 0 \
  --template /absolute/path/project/poses/character-poses.gdpose \
  --output /absolute/path/work/character-poses.candidate.gdpose \
  --pose-name seated_profile \
  --uncertain left_wrist \
  --mhr-axis mhr

python3 "$SKILL_DIR/scripts/validate_gdpose.py" \
  /absolute/path/work/character-poses.candidate.gdpose \
  --pose-name seated_profile \
  --expected-rig-bones 56 --require-sam3d-source
```

Omit `--uncertain` when every mapped joint is trusted. Add `--activate` only when the new profile should become active. Add `--send 127.0.0.1:PORT` to preview through a compatible localhost pose server without replacing the project file.

## Acceptance gates

- The SAM record represents the selected person and does not blend limbs from another person.
- Explicitly uncertain joints fall back to controls from a complete active template pose.
- The candidate preserves all pre-existing template profiles and metadata.
- Validation passes with the expected rig bone count and all required control names.
- Godot reports no missing controls or modifiers.
- Pelvis, shoulder center, wrists, ankles, elbow poles, and knee poles resemble the source in useful orthographic and perspective views.
- Left/right identity and prone/supine or other body-facing orientation are visually correct.
- The result is described as a coarse pose. A single image cannot recover hidden joints, exact depth, hand articulation, contact forces, or every local FK rotation of a full rig.

## Included resources

- `scripts/sam3d_export_json.py`: run official SAM 3D Body and serialize compact portable output.
- `scripts/image_to_gdpose.py`: map MHR70, MediaPipe, or external landmarks into `.gdpose` PoseControls and optionally stream the pose.
- `scripts/validate_gdpose.py`: validate document, rig, controls, transforms, and source metadata.
- `scripts/sam3d_device.patch`: compatibility patch for upstream revisions that still hard-code CUDA.
- `scripts/requirements-mediapipe.txt`: optional fallback for simple, mostly visible single-person images.
- `scripts/test_image_to_gdpose.py`: deterministic converter tests requiring only Python's standard library.
