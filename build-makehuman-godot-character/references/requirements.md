# Requirements and environment

## Input

- One full-body A-pose or relaxed T-pose reference with feet visible.
- A known anatomical/barefoot height in metres. Hair never counts. If the only measurement includes footwear, subtract the known vertical sole/heel contribution; when that contribution is unknown, label the height uncertain and do not claim centimetre accuracy.
- Prefer a level 70–135 mm-equivalent view. A wide-angle phone image distorts head, hand, and foot scale.
- Use additional close face images as identity references when available, but keep the original full-body image as the primary turnaround edit reference.

## Software

- Blender 4.2 or newer. MPFB 2.0.x requires Blender 4.2+; Blender 4.0 is not a safe default for the current extension.
- MPFB enabled in the Blender process and its MakeHuman target data available.
- Godot 4.x for final import and retarget verification.
- A compatible Humanizer project with generated target, body, eye, eyebrow,
  eyelash, hair, rig, material, and animation resources. The final exporter runs
  inside this project; a standalone Godot binary without those assets is insufficient.
- Python 3 with Pillow and NumPy for contact sheets and mask measurements.
- macOS with Swift, Vision, AppKit, and CoreImage for `analyze_turnaround.swift`. On another OS, substitute a pose, face-landmark, and person-segmentation detector that writes equivalent evidence.
- HeyRoute access only when generating identity-preserving views. Store the token in `HEYROUTE_API_KEY`; never put it in JSON, shell history arguments, source, logs, or Git.

## Blender/MPFB execution

On macOS, discover installed Blender applications before choosing a version:

```bash
find /Applications -maxdepth 2 -type d -name 'Blender*.app' -print
```

MPFB is a Blender extension. If `regenerate_mpfb_actor.py` reports that MPFB is not enabled:

1. Open Blender interactively.
2. Install or enable the MPFB extension/add-on.
3. Confirm a human can be created from the MPFB panel and its data paths resolve.
4. Close Blender and rerun the background command without `--factory-startup`.

Use `--factory-startup` for independent GLB validation because validation must not depend on MPFB.

## No-HeyRoute path

When `HEYROUTE_API_KEY` is unavailable, do not synthesize missing views through another paid service without user authorization. Use genuine user-supplied front/profile/back/head photographs when available. With only one full-body front image, build only a conservative neutral MPFB proxy, label depth and identity fit underconstrained, and skip the facial bake unless a separate high-resolution front face image is supplied. Ask for the missing key or genuine reference views before claiming identity reconstruction.

## Scope boundaries

- The process fits a parametric human to image evidence; it is not metric single-view 3D reconstruction.
- The generated turnaround is identity-conditioned synthesis, not calibrated photogrammetry.
- The MPFB stage preserves editable MakeHuman topology and a human preset. The final stage creates a Humanizer-native neutral proxy using bundled body/head equipment and a combined skinned Avatar.
- The process does not automatically create identity-perfect Humanizer garments, MakeClothes `.mhclo` clothing, equipment sockets, facial blendshapes, facial animation, or production hair cards.
- Loose garments, coats, skirts, heels, and hair must not drive hidden anatomy. Create them as separate assets after the body fit.
- Female and male builds share one workflow but require explicit gender-semantic translation and visually selected body/hair equipment. A successful female preset is not a male template.
