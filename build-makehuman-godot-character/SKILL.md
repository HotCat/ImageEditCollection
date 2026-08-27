---
name: build-makehuman-godot-character
description: Convert one full-body character A-pose image plus known height into identity-preserving multi-view references, an editable MakeHuman/MPFB preset, and a Humanizer-native Godot 4 realtime proxy with one combined skinned Avatar, calibrated body proportions, fitted eyes/hair, humanoid animations, and strict attachment/deformation QA. Use for female or male character reconstruction when Codex needs reusable MakeHuman topology, runtime-safe Godot rigging, reliable head attachments, retargeting, or optional quarantined facial texture experiments instead of directly rigging a dense AI mesh.
---

# Build a MakeHuman Godot Character

Use a two-stage architecture:

1. Fit and preserve the actor as an editable MPFB/MakeHuman preset.
2. Reconstruct that preset inside Humanizer and export one combined skinned Avatar as the final Godot proxy.

Treat the MPFB GLB as an intermediate diagnostic bridge. The production proxy must come from Humanizer when a compatible project is available. Never add final eyes, hair, or eyelashes as Blender bone-parented objects; that structure can pass Blender re-import while detaching in another GLB consumer.

## Read before execution

- Read `references/requirements.md` before invoking Blender, MPFB, HeyRoute, Humanizer, or Godot.
- Read `references/prompt-templates.md` before generating views or changing prompts.
- Read `references/fit-config.md` before fitting female or male body/face targets.
- Read `references/humanizer-export.md` before converting the MPFB preset into the final proxy.
- Read `references/qa-gates.md` before accepting any view, body fit, attachment, animation, texture, or GLB.
- Read `references/godot-import.md` before reporting the proxy as Godot-ready.

## Core workflow

1. Inspect the source. Require a largely unobstructed full body, A-pose or relaxed T-pose, level camera, low perspective distortion, visible feet, known anatomical height, and an explicit sex/body-shape interpretation supported by the image or user.
2. Generate separate full-body and high-resolution head views. Edit the original image, make one request per view, and approve identity before using the next view.
3. Analyze accepted views with Apple Vision or an equivalent detector. Inspect masks visually before measuring them. Do not infer hidden anatomy from skirts, coats, loose clothing, heels, or hair.
4. Fit global MPFB macros and conservative detail targets. Use front/back consensus for width, exact profiles for depth, and three-quarter views to expose identity drift.
5. Fit anatomical height after every segment-length change, add the MPFB `game_engine` rig, save the editable human preset, render clay geometry QA, and export an intermediate MPFB GLB.
6. Convert the saved preset into Humanizer. Translate gender semantics explicitly, apply every recognized detail target, calibrate the fitted body mesh's sole-to-crown height by Humanizer morphology, fit Humanizer-native eyes/hair/equipment, and export one combined skinned Avatar.
7. Validate raw GLB structure and a fresh Blender import. Require a single payload mesh, every raw mesh node skinned, enough surfaces and bones, Idle/Run animations, and no editor helper payload.
8. Render the freshly imported GLB in rest, run, and a deliberate head turn. Reject detached eyes/hair and joint collapse visually.
9. Import into Godot 4 and retarget idle/walk/run. Inspect scale, axes, root, shoulders, hips, thighs, knees, feet, and head accessories in motion.
10. Optionally perform the quarantined facial bake. Never promote it unless all texture gates pass; it is separate from the reliable neutral proxy.

## Generate and analyze references

Keep credentials only in `HEYROUTE_API_KEY`. Never pass, print, store, or commit them.

```bash
python scripts/generate_turnaround.py \
  --reference /absolute/path/character_a_pose.png \
  --kind body --view front \
  --output /absolute/path/work/turnaround/body_front.png

swift scripts/analyze_turnaround.swift \
  /absolute/path/work/turnaround/body_front.png \
  /absolute/path/work/analysis/body_front.json \
  /absolute/path/work/analysis/body_front_mask.png

python scripts/validate_a_pose.py \
  --analysis /absolute/path/work/analysis/body_front.json \
  --output /absolute/path/work/analysis/a_pose_validation.json
```

Accepted view names are `front`, `front-left-045`, `left-profile-090`, `back-180`, `right-profile-270`, and `front-right-315`. Generate the same names with `--kind head`. Regenerate any view whose identity, body, hairstyle, outfit, pose, crop, camera height, or lens character changes.

Summarize silhouettes only after inspecting their masks:

```bash
python scripts/measure_turnaround_masks.py \
  --mask /absolute/path/work/analysis/body_front_mask.png \
  --mask /absolute/path/work/analysis/body_left_profile_090_mask.png \
  --output /absolute/path/work/analysis/measurements.json
```

## Build the editable MPFB source

Create `fit-config.json` using `references/fit-config.md`. Pass anatomical/barefoot height to `--height`; hair and footwear do not count. Do not describe the visual fit as automatic inverse reconstruction.

```bash
BLENDER="/Applications/Blender 4.5.app/Contents/MacOS/Blender"
"$BLENDER" --background \
  --python scripts/regenerate_mpfb_actor.py -- \
  --output-dir /absolute/path/work/actor \
  --actor-id character_name \
  --height 1.82 \
  --config /absolute/path/work/fit-config.json \
  --rig game_engine --views 6 --resolution 768
```

Do not use `--factory-startup` here if it disables MPFB. Preserve these outputs:

- `human.character_name.json`: editable MPFB/MakeHuman source of truth;
- `character_name_realtime_proxy.blend`: intermediate MPFB authoring scene;
- `character_name_realtime_proxy.glb`: intermediate GLB diagnostic, not the preferred final proxy;
- `character_name_build_report.json`: fit and fresh-import evidence;
- `proxy_turntable/`: geometry QA.

Validate the intermediate GLB generically:

```bash
"$BLENDER" --background --factory-startup \
  --python scripts/validate_glb.py -- \
  --glb /absolute/path/work/actor/character_name_realtime_proxy.glb \
  --output /absolute/path/work/actor/mpfb_glb_validation.json \
  --expected-height 1.82 --height-tolerance 0.01 --min-bones 20
```

## Export the Humanizer-native final proxy

Use the calibrated builder. It installs the exporter into the exact Humanizer
project, exports, measures a fresh Blender import, and iterates Humanizer morphology
until the runtime GLB reaches the requested stature:

```bash
python scripts/build_humanizer_proxy.py \
  --project /absolute/path/Humanizer \
  --preset /absolute/path/work/actor/human.character_name.json \
  --height 1.82 \
  --gender-map invert \
  --hair Hair-Short01 \
  --output /absolute/path/work/actor/character_name_humanizer_proxy.glb \
  --report /absolute/path/work/actor/humanizer_proxy_report.json
```

For advanced debugging, `install_humanizer_exporter.py` and the installed Godot scene
may be run directly. Direct export calibrates source body arrays; the wrapper remains
canonical because it also closes the residual glTF skin/rest-transform height error.

For a male generated by this skill, MPFB preset gender `0` maps to Humanizer gender `1`. For a female, MPFB `1` maps to Humanizer `0`. Verify the report's `source_gender_value`, `humanizer_gender_value`, `sex_label`, `body_material`, and `hair_equipment` before accepting geometry.

The builder already runs the structural validator on every calibration trial and a
strict height-aware pass at completion. Re-run it independently when moving the GLB:

```bash
"$BLENDER" --background --factory-startup \
  --python scripts/validate_glb.py -- \
  --glb /absolute/path/work/actor/character_name_humanizer_proxy.glb \
  --output /absolute/path/work/actor/humanizer_glb_validation.json \
  --expected-height 1.82 --height-tolerance 0.001 --height-surface-index 0 \
  --min-bones 50 \
  --require-all-mesh-nodes-skinned --require-single-payload-mesh \
  --min-surfaces 8 --require-animation Idle --require-animation Run

"$BLENDER" --background --factory-startup \
  --python scripts/render_proxy_deformation_qa.py -- \
  --glb /absolute/path/work/actor/character_name_humanizer_proxy.glb \
  --output-dir /absolute/path/work/actor/deformation_qa
```

Open the three QA renders at full resolution. The structural validator cannot prove that eyes sit inside sockets, hair follows the scalp, or limbs deform aesthetically.

## Bake facial identity experimentally

Use only an accepted high-resolution front head image and its Vision analysis. Side/generated views remain geometry guides unless their cameras are calibrated.

```bash
"$BLENDER" --background \
  /absolute/path/work/actor/character_name_realtime_proxy.blend \
  --python scripts/bake_head_texture.py -- \
  --actor-id character_name \
  --front-image /absolute/path/work/turnaround/head_front.png \
  --front-analysis /absolute/path/work/analysis/head_front.json \
  --output-dir /absolute/path/work/actor/identity_bake
```

Record `pass` only after supplying every gate listed by `python scripts/record_texture_qa.py --help`. If it fails, retain it as experimental and deliver the Humanizer neutral proxy. Do not bake hair into skin.

## Report

Report accepted source views, anatomical height, inferred/confirmed sex, MPFB macro and detail fit, recognized/rejected Humanizer targets, MPFB and Humanizer gender values, fitted body-geometry height, fresh-import body and hair-inclusive visual heights, helper head height, calibrated Humanizer height macro, selected body/hair equipment, one-mesh/skinning evidence, surface and bone counts, animations, rest/run/head-turn QA, Godot retarget result, texture decision, selected deliverable, and remaining identity, hair, garment, or deformation limitations.
