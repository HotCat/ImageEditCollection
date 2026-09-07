---
name: sam3-neutralized-h3-character-replacement
description: Build a SAM3 neutralized full-frame video reference and a MiniMax H3 prompt for replacing one visible character—or only the character's head and hair—while preserving the source motion, scene, props, and audio.
---

# SAM3 Neutralized H3 Character Replacement

Use this skill when the user provides a reference video and a replacement-character image and wants the original visible character replaced without losing the original performance. It also supports head-only edits: replace the face and visible hair while retaining the original body, neck transition, clothing, hands, and props.

## Inputs and outputs

Resolve these inputs before editing:

- `source_video`: the original full-frame video, including its audio when audio should be retained.
- `character_image`: the appearance/identity reference for the replacement character.
- `subject_mask_video`: a full-frame, per-frame SAM3 mask for only the character being replaced. Generate this locally with the installed ComfyUI/SAM3 video-segmentation workflow when it is not supplied.
- `mask_scope`: the intended replacement scope, either `full_subject` (default) or `head`. For `head`, the mask must include only visible face and hair pixels; the neck, torso, clothing, hands, held props, captions, and background remain protected.

Produce:

1. A `neutralized_fullframe.mp4` with the subject region filled by a flat neutral matte and every non-matte pixel untouched.
2. A MiniMax H3 full-reference prompt that treats the neutral matte as the edit region and the character image as the sole appearance authority.
3. A validation report covering dimensions, FPS, frame count, duration, audio presence, and visual mask boundaries.

## Core procedure

1. Probe the source first with `ffprobe`. Preserve its width, height, FPS, frame count, duration, orientation, and audio unless the user explicitly requests a change.
2. Create or inspect the SAM3 mask. It must match the source width, height, FPS, and frame count. The mask should contain only visible pixels belonging to the target character; leave the girl, hands, held props, captions, stickers, and background outside it whenever those must be retained.
   - For `mask_scope=head`, seed SAM3 on the first-frame head with a tight bounding box or positive head points and negative points on the neck, blazer, hands, car, and background. Track that seed through the video (`SAM3_VideoTrack` with `initial_mask`) instead of text-detecting the whole person on every frame.
   - A head mask may follow loose hair, but its lower boundary must stop at the jaw/neck transition. If it touches the collar or a protected prop, shrink or manually clean the mask; do not authorize H3 to redraw the neck, clothing, hands, or prop.
   - Inspect at least the first, middle, and final mask frames. A full-body silhouette is a failure for `head` scope and must be regenerated before neutralization.
3. Build the neutralized full-frame reference with `scripts/build_neutralized_reference.py`. The script overlays a flat gray matte only inside the mask and copies the source audio without re-encoding it. The neutralized file is a generation reference, not the final composite.
4. Write the H3 prompt using the six-section Ref2VA structure in [references/h3-prompt-template.md](references/h3-prompt-template.md). Use stable labels:
   - `<Picture 1>` = the replacement character image.
   - `<Video 1>` = the neutralized full-frame video.
   - `<Audio 1>` = the source audio when it is reused.
   - `<Subject 1>` = the replacement character's appearance.
   - `<Subject 2>` = the original character's motion, expression timing, gaze, gestures, and prop interaction only.
   - `<Subject 3>` = the girl, props, scene, captions, stickers, and non-matte pixels.
5. Tell H3 explicitly that the flat gray silhouette is an animated hard edit matte, not a person, costume, lighting style, or appearance reference. Instruct it to replace every matte pixel and only those pixels with the new character. For `head` scope, explicitly say “head and visible hair only” and preserve the original body-to-neck transition.
6. Preserve the source's camera, framing, scene, girl, held props, captions, stickers, motion blur, lighting direction, timing, and audio. Explicitly prohibit the source character's face, hair, ethnicity, clothing, and identity from being copied or blended.
7. If the H3 workflow returns a full-frame video, use that output directly. Do not paste it back through the mask: doing so creates seams and can reintroduce untouched source pixels. Only use a local composite when the workflow is explicitly configured to return an isolated crop.

## Prompt requirements

The prompt must include:

- exact target duration and FPS;
- the matte's role and priority rules when it overlaps a protected prop;
- appearance authority from the character image only;
- motion-only transfer from the source performance;
- identity, matte-edge, anatomy, background, caption, and audio negative constraints;
- `overall_soundscape` and `non_diegetic_music` sections, with `N/A` when appropriate.

For an ice-cream or hand-held-prop shot, state that the prop and the girl's hand remain source-authentic and take priority over the replacement matte if the mask overlaps them.

## Validation

Run:

```bash
python scripts/build_neutralized_reference.py \
  --source /absolute/source.mp4 \
  --mask /absolute/subject_mask.mp4 \
  --mask-scope head \
  --output /absolute/neutralized_fullframe.mp4
```

Then compare `ffprobe` output for source and neutralized files. They should have matching width, height, FPS, frame count, duration, and audio stream. Inspect at least the first frame, a mid-shot frame, and the final frame with the matte overlaid. Stop and correct the mask if it covers another person, a protected prop, captions, or large background regions. For `head`, also confirm that no torso, blazer, collar, neck, hands, or held object is gray.

## Failure recovery

- If the output retains the source identity, verify that H3 actually received the neutralized video rather than the original or an old crop, and verify that the identity image is uploaded to the intended reference-image field.
- If the output leaves gray pixels, strengthen the instruction that the matte must disappear and that every gray pixel is editable.
- If the output changes the girl, prop, captions, or background, tighten the SAM3 mask and state that all non-matte pixels are immutable.
- If the output has seams, confirm that a full-frame H3 result was not locally pasted through the mask.
- If duration or FPS changes, fix the workflow's length and output-FPS controls before another paid run.
- If a head-only result still carries the source identity, verify that the replacement image is supplied as the appearance reference and that the neutralized video—not the original video—is supplied to H3. Tighten the head matte and state that source appearance is forbidden while source head motion remains required.
