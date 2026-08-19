# Audio-to-lyric alignment

## Choose the timing source

1. Search by exact title, artist, version label, and one distinctive lyric phrase.
2. Prefer timestamps published for the same recording duration and arrangement.
3. Compare the lyric order and repeated sections with the user's excerpt.
4. Treat an LRC for the original recording as unsuitable for a remix until two distant anchors confirm constant offset and tempo.

## Establish the video clock

Extract a mono analysis track without modifying the source:

```bash
ffmpeg -y -i input.mp4 -vn -ac 1 -ar 16000 analysis.wav
```

Listen or inspect a waveform/spectrogram around distinctive line starts. Record:

- the first supplied line's start in the video;
- a middle phrase start;
- a chorus or late phrase start.

For an LRC anchor at song time `S` heard at video time `V`, the clock offset is `V - S`. Two anchors should agree to within roughly 0.15–0.30 seconds for a short clip. Growing disagreement indicates a different tempo or edit.

## Handle tempo differences

If `V = a*S + b` fits several anchors, transform every LRC timestamp with that affine mapping before ASS generation. Use at least three anchors spanning the excerpt. A value of `a` other than approximately `1.0` means the audio is speed-changed.

Create a transformed LRC as a separate working file; preserve the downloaded/original LRC for auditability. Do not stretch the video or audio merely to fit subtitles.

## Work without an exact LRC

1. Extract the 16 kHz mono analysis WAV.
2. Use a capable Chinese ASR model with word timestamps and previous-text conditioning disabled.
3. Supply only a short title prompt, if any. A full lyric prompt can force repetitive hallucinations.
4. Use ASR timestamps, audible consonant onsets, waveform energy, and beat structure to mark line starts and ends.
5. Enter reviewed timings in TSV and render a draft.
6. Watch the full draft with sound. Correct timing in the TSV, regenerate, and repeat.

Never display hallucinated ASR wording. The user's lyrics remain authoritative.

## Visual QA

Extract representative frames after burning:

```bash
ffmpeg -y -i output_karaoke.mp4 \
  -vf "select='eq(n,90)+eq(n,600)+eq(n,1050)+eq(n,1350)',scale=800:-2,tile=2x2" \
  -frames:v 1 karaoke_contact.jpg
```

Check that text stays inside the frame, CJK glyphs render correctly, inactive text is white, completed text is gold, and the sweep is partially advanced on mid-line samples.
