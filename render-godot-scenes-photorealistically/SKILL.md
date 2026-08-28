---
name: render-godot-scenes-photorealistically
description: Render an established Godot 4 scene as a photorealistic image through HeyRoute while preserving the exact camera, pose, placement, metric character height, figure proportions, furniture scale, lighting direction, and multi-view character identity. Use when Codex needs to turn Godot beauty/depth/line-art exports into a final photograph, keep a skinned GLB actor recognizable across arbitrary scene cameras, correct AI-induced height or horizontal body warping, or produce a validated high-resolution still without replacing the 3D scene as geometric ground truth.
---

# Render Godot Scenes Photorealistically

Treat Godot as the geometric source of truth and HeyRoute as a material, identity, and photographic-detail renderer. Never claim that HeyRoute provides metric ControlNet constraints; verify its output against the Godot capture.

## Read before execution

- Read `references/prompt-templates.md` before composing either render pass.
- Read `references/qa-gates.md` before accepting or delivering an image.
- Read the available `heyroute-image-gen` skill completely before calling HeyRoute and follow any newer protocol or parameter guidance it provides. Use the bundled `scripts/run_heyroute_edit.py` for a portable ordered edit request; do not improvise an OpenAI SDK call because HeyRoute returns SSE rather than synchronous JSON.

## Establish source-truth roles

Record the following before generation:

- exact Godot scene and camera;
- beauty, depth, and line-art exports from the same settled frame;
- character GLB path and anatomical height in meters;
- character position, pose, and visible silhouette;
- identity references, preferably separate body and head turnarounds;
- known furniture dimensions and a useful scale landmark such as backrest height.

Assign each input one role. Do not let a reference silently override another:

1. **Godot beauty** — authoritative camera, framing, pose, placement, silhouette, lighting direction, and scene composition.
2. **Godot depth** — optional depth, occlusion, floor-contact, and spacing guide. It is a visual reference, not a true depth-control channel in HeyRoute.
3. **Godot line art** — optional contour and joint-placement guide. Require it not to appear in the result.
4. **Body turnaround** — clothing and body identity only when its morphology is known to match the GLB. Otherwise scope it to clothing only.
5. **Head turnaround** — face and hair identity only; never let it enlarge the head or change the body.
6. **Furniture reference** — material and style only; retain Godot dimensions and silhouette.

The GLB and Godot render always win conflicts about height, width, limb length, pose, placement, and object scale.

## Capture a stable Godot frame

Use the exact camera intended for the final still. Wait until animation, IK, physics, cloth, and editor-authored bone overrides have settled before exporting controls. Require beauty, depth, and line art to have identical dimensions and framing.

Do not infer metric height from pixels alone. Use the known GLB height and at least one measured scene landmark. For a character of height `H` and a couch back at `B`, state the ratio `B / H` in the prompt. Example: `1.00 / 1.81 = 0.552`, so the backrest reaches about 55% of stature, near the lower abdomen.

## Prepare the upload package

Keep the complete multipart request below HeyRoute's 30 MB input limit. Preserve the Godot beauty render losslessly and compact large turnaround sheets first:

Use an existing Python environment with Pillow. In Codex desktop, call the workspace-dependency loader and use its bundled Python path when system Python lacks Pillow. Do not install packages into the user's global Python without authorization.

```bash
python scripts/prepare_heyroute_inputs.py \
  --output-dir /absolute/path/render-work/compact \
  --fixed /absolute/path/beauty.png \
  --fixed /absolute/path/depth.png \
  --fixed /absolute/path/lineart.png \
  --reference body=/absolute/path/body_turnaround.png \
  --reference head=/absolute/path/head_turnaround.png \
  --max-long-edge 2048 \
  --jpeg-quality 92 \
  --budget-mib 29
```

Use the generated manifest to confirm dimensions, byte counts, and total upload size. Never compact depth or line-art maps as lossy JPEGs.

## Pass A: photorealistic reconstruction

Use HeyRoute image edit, not text-to-image. Upload the Godot beauty render first. Upload depth, line art, and scoped appearance references after it in the exact order described in the prompt.

Build the request from the initial template in `references/prompt-templates.md`. Explicitly state:

- every input role;
- exact camera and scene invariants;
- anatomical height and measured object-height ratio;
- pose, floor contact, body silhouette, and clothing;
- identity features and hair;
- photographic material, skin, lens, and lighting requirements;
- forbidden additions and visible control-map artifacts.

Make one high-quality request. Read the complete SSE stream through `completed` or `error`; do not duplicate a slow request while heartbeat events continue.

Write the completed Pass A prompt to a temporary text file, then run:

```bash
HEYROUTE_API_KEY="$(pbpaste)" python scripts/run_heyroute_edit.py \
  --prompt-file /absolute/path/render-work/pass-a-prompt.txt \
  --image /absolute/path/beauty.png \
  --image /absolute/path/depth.png \
  --image /absolute/path/lineart.png \
  --image /absolute/path/compact/body_2048.jpg \
  --image /absolute/path/compact/head_2048.jpg \
  --size 3840x2160 --quality high \
  --output /absolute/path/render-work/pass-a.png
pbcopy </dev/null
```

Use a hidden prompt or another process-scoped environment method when the key is not on the clipboard. Never put a literal key in a command, prompt file, or shell script.

## Inspect before iterating

Open the Godot beauty render, full-resolution output, body reference, and head reference. Apply every gate in `references/qa-gates.md`.

Separate failure classes:

- **identity failure** — face or hair drifted;
- **morphology failure** — apparent height, head-to-body ratio, torso, hips, or limbs differ from the GLB;
- **scene failure** — camera, couch, room, or lighting changed;
- **anatomy failure** — hands, feet, joints, clothing, or contacts are malformed;
- **delivery failure** — returned dimensions differ from the requested size.

Do not correct all classes in one prompt. Make the next pass surgical.

## Pass B: correct height or figure proportions

Run this pass only if Pass A is photorealistic and identity is acceptable but the figure no longer matches the GLB.

Use this input hierarchy:

1. Pass A image — edit target; preserve room, couch, lighting, face, hair, and clothing.
2. Godot beauty — authoritative metric silhouette, projected joint positions, pose, and floor contact.
3. Body turnaround — clothing reference only.
4. Head turnaround — face and hair identity only.

Exclude the furniture reference unless furniture appearance itself is wrong. Use the proportion-correction template in `references/prompt-templates.md`. Change only body geometry. Lock character height, object-height ratio, shoulder and hip widths, torso length, leg length, joint positions, head size, pose, and floor contact. Explicitly forbid horizontal stretching and copying body proportions from the photographed turnaround.

Run the same edit command with Pass A first, Godot beauty second, compact body third, and compact head fourth.

## Validate and deliver

Check actual returned dimensions; a successful high-resolution request may return a smaller native image. Preserve that native PNG. If an exact delivery size is required, create a clearly labeled resampled copy and do not describe it as native generation.

```bash
python scripts/validate_render_package.py \
  --godot-beauty /absolute/path/beauty.png \
  --render /absolute/path/final.png \
  --expected-aspect 16:9 \
  --requested-size 3840x2160 \
  --report /absolute/path/render-validation.json
```

Report:

- source scene, camera, and frame;
- GLB path and anatomical height;
- measured furniture landmark and ratio;
- input-role order;
- native output path and dimensions;
- any resampled delivery path and dimensions;
- identity, morphology, pose, camera, furniture, anatomy, and lighting QA;
- remaining mismatch and the fact that Godot remains metric ground truth.

## Credential and artifact rules

- Keep the HeyRoute key only in `HEYROUTE_API_KEY` for the process that needs it.
- Never print, commit, embed, or save the key in prompts, manifests, shell history, or skill files.
- Never commit user GLBs, source photographs, generated renders, or compact reference copies to this skill repository.
- Commit only reusable instructions, scripts, templates, and synthetic configuration examples.
