---
name: segment-overlapping-people
description: Separate two heavily overlapping or touching people in a raster image into distinct identity masks and flat-color silhouettes while preserving visible-surface occlusion. Use for carries, hugs, wrestling, dancing, seated embraces, or other multi-person composites where ordinary person-instance segmentation merges both bodies, swaps limbs, or invents hidden anatomy; especially when preparing masks for diffusion, ControlNet, inpainting, depth-guided generation, or visual QA.
---

# Segment Overlapping People

Create two mutually exclusive visible-pixel masks, a red/blue diagnostic silhouette, and an overlay on the source image. Treat hidden anatomy as unknown; do not reconstruct it into the segmentation.

## Core workflow

1. Inspect the source at full resolution. Identify unambiguous pixels for each person and list foreground contact parts such as a supporting arm crossing the other body.
2. Generate a clean union mask covering both people. On macOS 14+, run `scripts/person_union_mask.swift`. If an instance model merges the pair, keep the merged result: the union is still useful.
3. Run `scripts/sam2_prompt_masks.py` once per identity. Place positive points on several distinct regions of that person and negative points on the other person. Include a loose box when background objects are nearby.
4. Inspect all three SAM2 candidates. Prefer correct ownership at contact boundaries over the highest score. Add or move one prompt at a time and rerun when needed.
5. Use the more reliable identity mask as subject B. Derive subject A as `union - B` with `scripts/compose_visible_masks.py`.
6. If A has a foreground limb crossing B, create an A mask with SAM2 and pass it as `--a-foreground-mask`. Restrict that cue with `--a-foreground-box` so it cannot steal unrelated pixels elsewhere.
7. Inspect both the flat-color result and the source overlay. Iterate until the contact boundary is anatomically plausible.

## Prompt placement

- Express every point and box in the exact input image's full-resolution pixel coordinates. Check the source dimensions first and never reuse coordinates from another frame or a resized preview.
- Put positive points well inside face, torso, clothing, and separated limbs; avoid antialiased boundaries.
- Put negative points on the other person's most distinctive regions, particularly across the overlap.
- Use at least two positive points when the visible body is split into disconnected regions by occlusion.
- Do not place points on guessed hidden body parts.
- When one person's clothing is visually distinctive, isolate that person first and obtain the other by subtraction from the union.

Illustrative example for one 1280×720 frame; replace every coordinate for a different image:

```bash
PYTHONPATH=/path/to/sam2 python scripts/sam2_prompt_masks.py \
  --image frame.jpg \
  --checkpoint /path/to/sam2.1_hiera_large.pt \
  --config configs/sam2.1/sam2.1_hiera_l.yaml \
  --output-dir work/girl \
  --name girl \
  --positive 575,260 --positive 587,465 \
  --negative 742,202 --negative 702,355 --negative 575,390 \
  --box 445,145,690,660 \
  --color 0,0,255
```

The script saves all candidates, an overlay contact sheet, and the selected candidate. Use `--select 0`, `1`, or `2` after visual inspection; `--select auto` chooses the highest SAM2 score.

## Compose and validate

```bash
python scripts/compose_visible_masks.py \
  --image frame.jpg \
  --union-mask work/person_union.png \
  --b-mask work/girl/girl_candidate_2.png \
  --a-foreground-mask work/man/man_candidate_2.png \
  --a-foreground-box 430,270,690,430 \
  --a-name man --b-name girl \
  --output-dir output
```

The compositor writes separate binary masks, separate color silhouettes, a combined silhouette, and an overlay. It enforces:

- pure black, red, and blue in the combined diagnostic;
- identical dimensions across all outputs;
- zero overlap between A and B;
- assignment only inside the union mask.

Inspect the grayscale union before composition. The default `--union-threshold 112` is conservative. Lower it gradually toward `64` when dim faces or limbs disappear; raise it when background pixels leak into the union.

## Occlusion rules

- Segment visible surfaces only. A fully hidden torso or limb contributes no pixels.
- Give a foreground contact limb ownership over the body behind it.
- Leave true background holes black; do not fill spaces between an arm and torso.
- Fill only small enclosed compression holes. Do not bridge disconnected regions across an occluder.
- Interpret a red or blue halo around the other subject as an ownership error, not harmless antialiasing.

## Failure recovery

- **Both people remain merged:** add negatives on the other face and torso, tighten the box, and prompt the visually distinctive identity first.
- **A limb is assigned to the wrong person:** generate a mask for the foreground owner and restrict it to the contact area with `--a-foreground-box`.
- **Thin edge halo:** use `--absorb-b-edge 1`; do not exceed two pixels without inspecting the overlay.
- **Lower limb becomes fragmented:** reduce foreground dilation or restrict the foreground box; the override mask may be stealing pixels outside the contact.
- **Union misses a body part:** fix the union before identity composition. Subtraction cannot recover pixels absent from the union.
- **Union contains the part faintly but composition drops it:** lower `--union-threshold` while watching for background leakage in the overlay.
- **Source is too blurred:** report uncertain regions and keep a diagnostic overlay. Do not present guessed hidden anatomy as ground truth.
- **SAM2 paths are unknown:** run `python -c "import sam2, torch; print(sam2.__file__); print(torch.__version__)"`, then locate a compatible checkpoint and config in that SAM2 installation. Pass its repository root through `PYTHONPATH` when `import sam2` fails.

## Dependencies

- `person_union_mask.swift`: macOS 14+ with Vision, CoreImage, and ImageIO.
- Python scripts: Python 3.10+, NumPy, Pillow, and OpenCV.
- `sam2_prompt_masks.py`: additionally PyTorch and Meta SAM2 with a compatible checkpoint and config.

Use a deterministic segmentation path for this task. Do not use a generative image editor to redraw masks because it can change pose, silhouette, or contact geometry.
