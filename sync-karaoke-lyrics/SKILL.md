---
name: sync-karaoke-lyrics
description: Synchronize authoritative song lyrics to a video's real audio, generate editable ASS subtitles with progressive per-character karaoke highlighting, burn them into a new MP4, and verify timing and media properties. Use when a user asks to add, overlay, time, align, or burn karaoke lyrics/subtitles onto a music video, especially when the clip starts mid-song, uses a remix or sped-up version, or must preserve the original wording and audio.
---

# Sync Karaoke Lyrics

Create a new karaoke video plus an editable `.ass` file. Preserve the input video and the user's lyric wording.

## Workflow

1. Probe the source with `ffprobe`. Record duration, frame rate, frame count, dimensions, and audio format.
2. Save the supplied lyrics exactly, one display line per line, in UTF-8. Do not silently replace words with an ASR transcript or an online lyric variant.
3. Identify the exact recording: artist/version, remix, speed, and where the clip begins in the song.
4. Prefer a timestamped LRC for that exact recording. Read [references/alignment.md](references/alignment.md) before aligning a remix, partial clip, or source without an exact LRC.
5. Establish at least two audio anchors: one near the beginning and one near the final third. Reject a timing source if drift grows across the clip.
6. Generate ASS subtitles with `scripts/build_karaoke_ass.py`.
7. Burn and verify the output with `scripts/burn_karaoke.py`.
8. Extract a contact sheet with frames from the opening verse, middle, chorus, and last lyric. Inspect legibility, safe margins, correct CJK glyphs, and progressive highlighting.

## Build from LRC

Use this path when an exact or closely matching timed LRC exists:

```bash
python scripts/build_karaoke_ass.py \
  --lyrics lyrics.txt \
  --lrc exact_version.lrc \
  --first-line-at 0.00 \
  --width 1600 --height 900 \
  --output output_karaoke.ass
```

`--first-line-at` is the time in the video where the first supplied lyric line starts. The script semi-globally aligns all authoritative lyric characters to the LRC, so it tolerates small wording differences and can locate a contiguous excerpt inside a full song. It reports the normalized match ratio; inspect alignment below `0.82` and do not trust it below `0.70`.

Use `--offset` instead when the exact LRC-to-video clock offset is already known. Do not pass both options.

## Build from reviewed timings

When no trustworthy LRC exists, create a UTF-8 tab-separated file with `start`, `end`, and exact display text. A header is optional:

```text
start	end	text
0.000	5.620	对月饮 一杯寂寥
5.620	9.250	剑起江湖恩怨 拂袖罩明月
```

Then run:

```bash
python scripts/build_karaoke_ass.py \
  --timings reviewed_timings.tsv \
  --width 1600 --height 900 \
  --output output_karaoke.ass
```

Within a reviewed line, the script distributes the sweep evenly by visible character. For phrase- or word-level timing, split a line into multiple LRC entries before building; the LRC path preserves those internal timing boundaries.

## Burn and verify

```bash
python scripts/burn_karaoke.py \
  --video input.mp4 \
  --ass output_karaoke.ass \
  --output output_karaoke.mp4
```

The burner uses H.264 CRF 18, copies the original audio without re-encoding, moves MP4 metadata to the front, and verifies resolution, frame rate, frame count, duration, and audio presence. Use `--preset` or `--crf` only when the user requests a different speed/quality tradeoff.

## Style rules

- Use a bold CJK font, bottom-center alignment, white inactive text, warm yellow/gold completed text, and a dark outline.
- Keep lyrics within the active picture, not in blurred padding, unless the user explicitly prefers padding placement.
- Choose font size and bottom margin relative to output height. Defaults are tuned for 900p and scale automatically.
- Keep one line on screen unless a line is too wide. Prefer a deliberate two-line split over shrinking below comfortable mobile readability.
- Keep spaces unhighlighted; sweep visible characters from left to right with ASS `\kf` tags.
- End the final lyric naturally instead of extending it through a long instrumental gap.

## Timing rules

- Treat singing ASR as evidence for anchors, not authoritative text. Singing recognition commonly hallucinates repeated phrases.
- Do not guess equal line durations across the full song.
- A constant clock shift fixes an excerpt start; it does not fix tempo mismatch. If early and late anchors require different offsets, locate the correct version or time-warp the LRC timestamps before generation.
- Preserve repeated lyric occurrences in sequence. Align the whole supplied excerpt, not only its first line, to avoid selecting the wrong chorus.
- For clips truncated mid-line, clamp the subtitle event to the video end.
- Report uncertainty if vocals are buried, the version is unknown, or anchors conflict.

## Deliverables

Return both files:

- burned-in karaoke video, using a `_karaoke.mp4` suffix;
- editable ASS subtitle track, using the same basename and `.ass`.

Report the verified resolution, fps, frame count, duration, and whether original audio was stream-copied.

## Dependencies

- Python 3.10+ standard library
- FFmpeg and FFprobe with libass and libx264 support
- A locally installed font covering the lyric script
