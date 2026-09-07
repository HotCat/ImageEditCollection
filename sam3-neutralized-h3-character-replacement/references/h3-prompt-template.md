# MiniMax H3 neutralized-reference template

Use this as a scaffold, then fill in concrete appearance, actions, props, timing, and scene details from the supplied files. Keep the six sections and label meanings stable.

```text
subject_definitions:
<Subject 1> is the replacement character shown in <Picture 1>. The face, hair, skin tone, body proportions, clothing, and visible accessories come only from <Picture 1>.
<Subject 2> is the source character's motion performance in <Video 1>: pose, gestures, head turns, gaze, facial-expression timing, lip movement, camera-relative position, and interaction timing. Use motion only; do not copy appearance.
<Subject 3> is the protected girl, props, environment, captions, stickers, camera, lighting, and every non-matte pixel in <Video 1>.
<Picture 1> is the sole appearance authority for <Subject 1>.
<Video 1> is the neutralized full-frame video, [WIDTH]x[HEIGHT], [FPS] fps, [DURATION] seconds. Its flat neutral-gray silhouette is an explicit animated replacement matte, not a person or appearance reference.
<Audio 1> is the synchronized source audio embedded in <Video 1>, reused 1:1 when available.

summary:
[video editing + reference generation + audio reuse] Edit <Video 1> by replacing every pixel inside the neutral-gray silhouette with <Subject 1> from <Picture 1>. Transfer only <Subject 2>'s motion, expressions, gaze, lip timing, and prop interaction. Preserve <Subject 3>, every non-matte pixel, camera, framing, captions, stickers, duration, FPS, and <Audio 1>. The gray silhouette must disappear completely.

retention_analysis:
<Subject 1> (inside the matte throughout [Shot 1]): attribute_transfer - preserve the replacement identity and wardrobe from <Picture 1> consistently through all views and occlusions.
<Subject 2> (motion throughout [Shot 1]): attribute_transfer - transfer motion and timing only; do not transfer the source face, hair, ethnicity, clothing, or identity.
<Subject 3> (non-matte content throughout [Shot 1]): fully_preserved - preserve the girl, hands, held props, background, captions, stickers, camera, and lighting.
<Picture 1>: fully_preserved - use only for replacement appearance; do not copy its background or static pose.
<Video 1>: partially_preserved - preserve source timing, camera, scene, motion, and non-matte pixels while replacing the matte.
<Audio 1>: fully_copy - use as the complete final audio track.

detailed_description:
The target is a realistic full-frame video at exactly [WIDTH]x[HEIGHT], [FPS] fps, and [DURATION] seconds. Treat the neutral-gray silhouette in <Video 1> as a precise animated hard edit matte. Every gray pixel and only the gray silhouette must become the new character; the gray color must never remain visible. Do not use the silhouette as an appearance reference.

[Shot 1] Start from the exact first frame of <Video 1>. Place <Subject 1> exactly inside the matte at the source screen-space position, scale, depth, and occlusion. Use <Picture 1> as the sole authority for face identity, hair, skin tone, body, clothing, and accessories. Apply <Subject 2>'s exact pose, gestures, head movement, gaze, facial-expression timing, lip-sync timing, and interaction with the protected prop. Match the source scene's lighting, shadows, exposure, lens perspective, motion blur, and depth of field.

Keep <Subject 3> completely unchanged. Protected props and the girl's hands have priority if the matte touches them: preserve their original shape, texture, color, position, and contact shadows, and place the replacement naturally behind or beside them. Preserve captions, stickers, background, camera path, and framing through the final frame.

Keep the replacement identity stable in close-up, speech, turns, partial occlusion, and motion. Prohibit the source character's face, hair, ethnicity, clothing, facial structure, face blending, identity drift, gray matte, flat silhouette, mask halo, rectangular patch, matte spill, altered girl, altered props, caption changes, background repainting outside the matte, extra fingers, extra limbs, new people, crop, zoom, reframing, frame interpolation, and audio replacement.

overall_soundscape:
Preserve the source ambience and physical sounds from <Audio 1> with the original timing. Keep replacement lip movement synchronized to the existing speech without changing the audio.

non_diegetic_music:
N/A
```
