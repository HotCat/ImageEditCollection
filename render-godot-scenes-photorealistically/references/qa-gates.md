# Quality Gates

Reject or iterate when any required gate fails. Inspect the native output at full resolution.

## Geometry and camera

- Match the Godot camera position, yaw, pitch, roll, focal character, crop, horizon, and vanishing lines.
- Keep room corners, floor plane, object positions, occlusion order, and contact shadows aligned.
- Preserve the character crown and foot-contact locations relative to the frame.
- Preserve projected shoulders, elbows, wrists, hips, knees, ankles, and feet.
- Preserve each measured object-to-character ratio. Compute `landmark_height / character_height` before generation.

## Figure proportions

- Compare shoulder, ribcage, waist, pelvis, thigh, calf, and head widths against the Godot silhouette.
- Compare torso, upper-leg, lower-leg, arm, neck, and head lengths.
- Reject a subject that looks shorter because of enlarged head, compressed torso, shortened legs, widened hips/thighs, or horizontal body warping.
- Treat the GLB morphology as authoritative even when a photographic turnaround differs.

## Identity and appearance

- Match face shape, eyes, nose, lips, skin tone, hairline, hairstyle, and distinctive asymmetry across supplied head views.
- Preserve requested clothing layers, neckline, sleeve length, skirt or trouser construction, and footwear.
- Require realistic skin, hair, fabric, furniture material, and floor response without plastic CGI surfaces.

## Anatomy and contacts

- Require one intended person, correct limb count, plausible joints, five readable fingers when visible, and complete footwear.
- Keep feet on the specified floor plane and the body on any authored furniture/contact anchors.
- Reject floating feet, interpenetration, melted hands, duplicated digits, collapsed knees, or changed pose.

## Scene invariants

- Preserve the number and type of furniture pieces.
- Reject invented doors, windows, lights, decorations, tables, or props.
- Preserve lighting direction and the shape of major cast shadows unless the user requests a lighting change.
- Reject visible grayscale depth, line-art strokes, labels, watermarks, borders, or contact-sheet layouts.

## Delivery

- Verify that the output file is nonempty and decodes as an image.
- Record native width, height, aspect ratio, and byte count.
- Compare actual dimensions with the requested size. A smaller native return is a delivery limitation, not proof of failed visual quality.
- Preserve the native PNG. Label any locally resized image as a resampled delivery copy.
- Report remaining identity, morphology, geometry, anatomy, or texture drift honestly. Never call a diffusion edit metrically exact.
