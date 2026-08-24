---
name: reframe-video-camera-runninghub
description: Reframe a source video with a described virtual camera move by normalizing it to an LTX-compatible clip, estimating monocular depth locally, building a CrossView-Warp control video, uploading the source and control to a corrected LTX-2.3 workflow on RunningHub, downloading the result, and validating the target video. Use when Codex needs to orbit, crane, dolly, or otherwise change the apparent camera path of an existing video through the tested local-plus-RunningHub pipeline, especially from natural-language camera directions and without browser-operated ComfyUI.
---

# Reframe Video Camera on RunningHub

Translate the requested move into an explicit camera path, run deterministic local preprocessing, then leave heavy LTX-2.3 inference to RunningHub.

## Execute the pipeline

1. Read `references/workflow-and-nodes.md` before changing frame counts, model names, node overrides, or camera conventions.
2. Read `references/environment.md` before creating or repairing the local runtime.
3. Read the sibling `../run-runninghub-workflows/SKILL.md` completely before using the RunningHub API. Follow its credential handling exactly.
4. Inspect the source with `ffprobe`. Default to 241 frames at 24 fps and 1280x720 unless the user requests otherwise. Require an LTX length of `8n+1`; do not exceed 241 without confirming the deployed workflow and available compute can handle it.
5. Convert the natural-language camera description into a JSON keyframe path. Use `assets/camera-path-example.json` as the schema. State any inferred direction, pivot, lens, distance, or timing before spending RunningHub credits.
6. Bootstrap or check the local runtime:

   ```bash
   python3.12 scripts/bootstrap_environment.py \
     --runtime-dir /absolute/path/to/crossview-runtime
   ```

7. Keep the API key only in `RUNNINGHUB_API_KEY`. Never persist or print it. Execute:

   ```bash
   /absolute/path/to/crossview-runtime/venv/bin/python \
     scripts/run_reframe_pipeline.py \
     --source /absolute/path/to/source.mp4 \
     --camera-path /absolute/path/to/camera-path.json \
     --output-dir /absolute/path/to/output \
     --crossview-root /absolute/path/to/crossview-runtime/ComfyUI-CrossViewWarp
   ```

8. Clear clipboard contents immediately if the key came from the clipboard. Preserve the local and RunningHub manifests; neither contains the key.
9. Visually inspect the start, middle, and end of the output. Report the camera path, task ID, final path, frame count, fps, duration, resolution, audio presence, identity/pose consistency, and invented regions.

## Guardrails

- Treat the result as view-conditioned video synthesis, not genuine metric 3D reconstruction. Newly revealed surfaces are hallucinated.
- Prefer orbits within about +/-30 degrees for fidelity. Use +/-45 degrees when broader exploration matters more than exact hidden geometry. Warn before moves beyond +/-45 degrees, large pull-backs, or steep elevation changes.
- Keep the subject visible in the source. Monocular depth cannot recover fully occluded geometry.
- Normalize source and warp to identical frame count, fps, dimensions, and crop. Reject mismatches before upload.
- Run one camera path at a time until it succeeds. A repeated submission can incur duplicate cost.
- Do not commit source videos, generated videos, model weights, depth memmaps, API keys, or runtime environments. Commit only scripts, manifests without secrets, small configuration examples, and the workflow JSON.

## Reuse and modification

- Use `scripts/normalize_video.py` independently when only timing/crop normalization is needed.
- Use `scripts/build_crossview_control.py` independently to preview the warp before paid inference.
- Use `scripts/validate_video.py` to verify any downloaded candidate.
- Import `assets/ltx23-crossview-241-runninghub.json` into RunningHub if workflow `2091756366166839297` is unavailable in the current account, then pass the new ID with `--workflow-id`.
- Adjust semantic generation guidance with `--prompt`; keep `crossview.` at the beginning because the IC-LoRA workflow expects that task cue.
