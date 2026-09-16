# SAM 3D Body setup and subject selection

## Upstream components

Use the official repository and model access instructions:

- Repository: <https://github.com/facebookresearch/sam-3d-body>
- Default Hugging Face model id used by the wrapper: `facebook/sam-3d-body-vith`

SAM 3D Body, its dependencies, and model weights are not included in this skill. Follow their licenses and access terms. Keep checkpoints outside the Godot project and Git repository.

Create an isolated environment matching the Python and accelerator versions required by the upstream revision. Confirm imports before running the wrapper:

```bash
/absolute/path/to/sam3d-python -c "import torch; import sam_3d_body; print(torch.__version__)"
```

## Device compatibility patch

Some upstream revisions accept `device=cpu` or `device=mps` in the loader but later hard-code CUDA while preparing a batch or mesh grid. Check before patching:

```bash
git -C /absolute/path/to/sam-3d-body apply --check \
  /absolute/path/to/skill/scripts/sam3d_device.patch
```

Apply only when `--check` succeeds. If it reports that the patch is already applied or surrounding code changed, inspect upstream instead of forcing it:

```bash
git -C /absolute/path/to/sam-3d-body apply \
  /absolute/path/to/skill/scripts/sam3d_device.patch
```

On the Apple Silicon setup where this workflow was developed, the bundled MHR TorchScript uses float64 internally, which MPS does not support. Use CPU there. CUDA remains preferred when compatible.

## Select exactly one person

The wrapper intentionally includes no external person detector. Without `--bbox`, SAM 3D Body treats the full image as one subject. Use the source image's full-resolution pixel coordinates:

```text
--bbox X1 Y1 X2 Y2
```

Use an explicit box for every multi-person, overlapping, partly occluded, or unreliable crop. Include the visible head, torso, hands, and feet where possible. The box may overlap another person, but should center and cover the intended body. Run a separate pass and box for each character in carries, sports, dance, or other interactions.

`--person-index` on `sam3d_export_json.py` matters only if upstream returns multiple records. One manual box normally returns one record, so conversion uses `--person-index 0`.

## Inspect before conversion

The wrapper keeps compact pose fields by default. The converter needs `pred_keypoints_3d`, whose first 70 entries use MHR70 order. Avoid `--include-vertices` unless mesh inspection is required; vertices are large and unused by `.gdpose` conversion.

```bash
python3 - /absolute/path/person.mhr70.json <<'PY'
import json, sys
records = json.load(open(sys.argv[1], encoding="utf-8"))
print("records", len(records))
print("keypoints", len(records[0]["pred_keypoints_3d"]))
print("bbox", records[0].get("bbox"))
PY
```

Reject an empty record, fewer than 70 points, non-finite coordinates, impossible limb lengths, or landmarks belonging to different people. A plausible bounding box alone does not prove correct assignment.

Review both `pred_keypoints_2d` against the source and `pred_keypoints_3d` from useful viewpoints. Explicitly mark any hidden, blended, or misassigned mapped joints during conversion with repeatable `--uncertain` flags. This is essential when the SAM record has no confidence array.

## Pose-category guidance

- Standing and locomotion: inspect foot identity, crossed limbs, stride depth, and nearly straight knee poles.
- Sitting, crouching, and kneeling: inspect hip/knee depth ordering and floor or seat contacts.
- Lying, diving, and airborne poses: verify body axes and resolve prone/supine or axial-roll ambiguity visually.
- Carries and other interactions: infer each person separately; mark occluded joints and repair inter-character contact in Godot.

## Optional MediaPipe fallback

For a simple, mostly visible person, `image_to_gdpose.py` can estimate directly from the image with MediaPipe. Install `scripts/requirements-mediapipe.txt` in a separate environment. Prefer SAM 3D Body for challenging depth, horizontal bodies, crouches, overlap, and partial occlusion.
