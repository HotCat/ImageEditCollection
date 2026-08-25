---
name: build-makehuman-godot-character
description: Convert one full-body character A-pose image plus known height into identity-preserving multi-view references, a fitted MakeHuman/MPFB basemesh and editable human preset, a Godot 4-friendly game-engine humanoid rig and validated GLB, and an optional QA-gated facial texture bake. Use when Codex needs to reconstruct a real or generated character as editable MakeHuman-compatible topology rather than rigging a dense AI mesh directly, especially for runtime body proportions, animation, retargeting, or character placement in Godot 4.
---

# Build a MakeHuman Godot Character

Build an editable MPFB character first and treat texture projection as an optional, quarantined stage. Deliver the neutral realtime proxy whenever the identity bake fails visual QA.

## Read before execution

- Read `references/requirements.md` before installing or invoking Blender, MPFB, HeyRoute, or Godot.
- Read `references/prompt-templates.md` before generating views or changing prompts.
- Read `references/fit-config.md` before fitting body or face targets.
- Read `references/qa-gates.md` before accepting any generated reference, bake, rig, or GLB.
- Read `references/godot-import.md` before reporting the GLB as Godot-ready.

## Workflow

1. Inspect the source image. Require one unobstructed full body, an A-pose or relaxed T-pose, a level camera, low perspective distortion, visible feet, and known physical height. Reject an interaction pose, crossed limbs, wide-angle selfie, or garment-obscured body as the only measurement source.
2. Generate a full-body turnaround and separate high-resolution head references. Always edit the original image, make one request per view, and visually approve identity before generating or using the next view.
3. Analyze accepted views with Apple Vision or an equivalent local detector. Use masks and joints for proportions; do not turn image scanlines directly into anatomy where a skirt, coat, heels, or hair obscures the body.
4. Create a fit config that records MPFB macro values and conservative detail targets. Use front/back consensus for width, profiles for depth, and three-quarter views to catch asymmetry or identity drift.
5. Build the neutral MPFB proxy, fit evaluated visible body geometry to the known height, add the `game_engine` rig, serialize the editable human preset, render a turntable, export GLB, and calibrate export scale by fresh re-import.
6. Validate the raw GLB JSON and a fresh Blender import. Do not mistake Blender-created rig display shapes for payload geometry.
7. Optionally create the experimental front-face bake. Keep side/head references as geometry guides unless their cameras are explicitly calibrated. Render front, profiles, back, and close-up QA.
8. Record the visual texture decision. If any texture gate fails, retain the bake as experimental and deliver the clean neutral proxy plus the accepted photorealistic reference images.
9. Import the accepted GLB into Godot 4, create or assign a humanoid bone map, retarget a simple idle/walk animation, and inspect shoulders, hips, knees, feet, and scale.

## Generate reference views

Keep the credential only in `HEYROUTE_API_KEY`. Never pass, print, store, or commit it.

If the key is missing, follow the no-HeyRoute path in `references/requirements.md`: accept genuine user-supplied views or downgrade to an underconstrained neutral proxy. Do not promise an identity bake from one distant full-body image.

```bash
python scripts/generate_turnaround.py \
  --reference /absolute/path/character_a_pose.png \
  --kind body --view front \
  --output /absolute/path/work/turnaround/body_front.png
```

Accepted body views are `front`, `front-left-045`, `left-profile-090`, `back-180`, `right-profile-270`, and `front-right-315`. Generate the same view names with `--kind head`. Stop and regenerate a view if identity, hair, clothing, pose, body proportions, camera height, or crop changed.

## Analyze accepted views

On macOS, run the Vision analyzer for each view:

```bash
swift scripts/analyze_turnaround.swift \
  /absolute/path/work/turnaround/body_front.png \
  /absolute/path/work/analysis/body_front.json \
  /absolute/path/work/analysis/body_front_mask.png
```

Reject an unusable front pose before fitting:

```bash
python scripts/validate_a_pose.py \
  --analysis /absolute/path/work/analysis/body_front.json \
  --output /absolute/path/work/analysis/a_pose_validation.json
```

Summarize silhouette scanlines only after visual mask inspection:

```bash
python scripts/measure_turnaround_masks.py \
  --mask /absolute/path/work/analysis/body_front_mask.png \
  --mask /absolute/path/work/analysis/body_left_profile_090_mask.png \
  --output /absolute/path/work/analysis/measurements.json
```

## Build the MPFB proxy

Create `/absolute/path/work/fit-config.json` using `references/fit-config.md`, then run Blender with MPFB enabled. Do not use `--factory-startup` if it disables the installed MPFB extension.

Pass anatomical/barefoot height to `--height`; never include hair. Subtract known footwear height first. Treat the fit config as documented visual fitting, not an automatic one-photo optimizer.

```bash
BLENDER="/Applications/Blender 4.5.app/Contents/MacOS/Blender"
"$BLENDER" --background \
  --python scripts/regenerate_mpfb_actor.py -- \
  --output-dir /absolute/path/work/actor \
  --actor-id character_name \
  --height 1.81 \
  --config /absolute/path/work/fit-config.json \
  --rig game_engine --views 6 --resolution 768
```

The authoritative clean outputs are:

- `human.character_name.json`: editable MPFB/MakeHuman-compatible human preset;
- `character_name_realtime_proxy.blend`: clean neutral Blender source;
- `character_name_realtime_proxy.glb`: fallback and realtime bridge;
- `character_name_build_report.json`: target fitting, root-scale calibration, topology, rig, and fresh-import evidence;
- `proxy_turntable/`: visual geometry QA.

Never claim this creates a fully native Humanizer character. It creates MakeHuman/MPFB topology, a built-in game-engine rig, and a Godot GLB bridge. Creating Humanizer equipment definitions, `.mhclo` garments, or runtime body morph targets remains separate work.

## Validate the GLB

Run validation in a fresh Blender process:

```bash
"$BLENDER" --background --factory-startup \
  --python scripts/validate_glb.py -- \
  --glb /absolute/path/work/actor/character_name_realtime_proxy.glb \
  --output /absolute/path/work/actor/glb_validation.json \
  --expected-height 1.81 --height-tolerance 0.01 --min-bones 20
```

Reject a GLB with no raw skin, no armature after re-import, too few bones, no weighted mesh, actual helper payload, or height outside tolerance.

## Bake the facial identity experimentally

Use the accepted high-resolution front head image and its Vision analysis. The script derives a front projection from detected eyes and mouth to MPFB eye/mouth groups; it does not pretend AI side views are calibrated cameras.

```bash
"$BLENDER" --background \
  /absolute/path/work/actor/character_name_realtime_proxy.blend \
  --python scripts/bake_head_texture.py -- \
  --actor-id character_name \
  --front-image /absolute/path/work/turnaround/head_front.png \
  --front-analysis /absolute/path/work/analysis/head_front.json \
  --output-dir /absolute/path/work/actor/identity_bake
```

Create a contact sheet and inspect the full-resolution source renders too:

```bash
python scripts/make_contact_sheet.py \
  --input-dir /absolute/path/work/actor/identity_bake/experimental_texture_qa \
  --output /absolute/path/work/actor/identity_bake/texture_contact_sheet.png
```

Record a failed decision with explicit reasons. Record `pass` only after supplying every check listed by `python scripts/record_texture_qa.py --help` and `references/qa-gates.md`.

```bash
python scripts/record_texture_qa.py \
  --render-dir /absolute/path/work/actor/identity_bake/experimental_texture_qa \
  --output /absolute/path/work/actor/identity_bake/texture_qa.json \
  --decision fail --reason "face projection extends onto neck"
```

After a texture decision passes, validate the experimental textured GLB independently and require embedded/resolved texture images:

```bash
"$BLENDER" --background --factory-startup \
  --python scripts/validate_glb.py -- \
  --glb /absolute/path/work/actor/identity_bake/character_name_experimental_textured.glb \
  --output /absolute/path/work/actor/identity_bake/textured_glb_validation.json \
  --expected-height 1.81 --height-tolerance 0.01 --min-bones 20 --require-textures
```

Promote the textured GLB only when both texture QA and this GLB validation pass. Godot-ready status still requires the manual import and retarget test in `references/godot-import.md`; no bundled script automates Godot's BoneMap UI.

Do not bake hair onto skin. Preserve hairstyle as separate scalp/hair geometry and material; model or fit it as a distinct asset after the body and face geometry pass.

## Report

Report the source and accepted views, known height, MPFB macro/detail fit, visible native and re-imported heights, topology counts, rig name and bone count, raw GLB mesh/skin state, Godot retarget result, texture QA decision, selected deliverable, and remaining identity, hair, garment, or deformation limitations.
