# Workflow and node contract

## Tested configuration

- RunningHub workflow ID: `2091756366166839297`
- Successful reference task: `2091764776253485058`
- Source contract: H.264 MP4, 241 frames, 24 fps, 1280x720
- Final observed result: 241 frames, 24 fps, 10.041667 seconds, 1280x704 H.264 with AAC audio
- Local depth model: `depth-anything/Depth-Anything-V2-Small-hf`
- CrossView-Warp revision: `3266a83a84eaa6833a9ebc38ac7cdd8789e44f5b`

The generated height can become 704 because LTX latent dimensions are aligned internally. Treat 1280x704 as valid for this deployed graph even though both uploaded controls are 1280x720.

## Required RunningHub overrides

| Node | Field | Value |
|---|---|---|
| 441 | `video` | uploaded normalized source filename |
| 447 | `video` | uploaded CrossView warp filename |
| 447 | `force_rate` | requested fps |
| 447 | `frame_load_cap` | requested frame count |
| 301 | `value` | requested frame count |
| 300 | `value` | requested fps |
| 314 | `value` | width |
| 299 | `value` | height |
| 303 | `value` | prompt beginning with `crossview.` |
| 319 | `vae_name` | `LTX23_video_vae_bf16.safetensors` |
| 320 | `vae_name` | `LTX23_audio_vae_bf16.safetensors` |
| 324 | `clip_name1` | `gemma_3_12B_it_fp8_e4m3fn.safetensors` |
| 324 | `clip_name2` | `ltx-2.3_text_projection_bf16.safetensors` |

The four model-name overrides are essential. The tutorial graph used local subfolder prefixes that do not resolve on RunningHub.

## Camera path schema

Use 1-based frame numbers. Required fields are `frame`, `azimuth`, and `elevation`. Optional fields are `distance`, `vertical_shift`, `pivot_x`, `pivot_y`, and `pivot_z`.

- Negative azimuth: orbit toward camera-left.
- Positive azimuth: orbit toward camera-right.
- Positive elevation: crane/rise above the subject.
- Negative elevation: lower the camera.
- Distance `1.0`: retain source distance. Lower values move in; higher values pull back.
- Default pivot: `(0, 0, 1.05)` in normalized depth space.
- Before the first and after the last keyframe, hold the nearest keyframe.
- `interpolation` may be `linear`, `ease_in`, `ease_out`, `ease_in_out`, or `smooth`.

Example interpretation: “orbit from -45 to +45 degrees and add a 20-degree crane” becomes frames `(1, -45, 0)`, `(121, 0, 10)`, `(241, +45, 20)` with smooth interpolation.

## Frame count rules

LTX video lengths follow `8n+1`. The tested 241-frame clip is `8*30+1`. Normalize by sampling at the target fps, holding the final frame if the source is short, and trimming if it is long. Do not loop the clip.

## Fidelity expectations

The warp establishes camera direction and coarse parallax. LTX-2.3 fills magenta disocclusion holes and re-synthesizes novel content. A wider orbit reveals more unknown geometry and increases identity, anatomy, clothing, and background drift. Relative Depth Anything depth is adequate for concept validation; MoGe or another metric geometry source should improve parallax accuracy when exact geometry matters.
