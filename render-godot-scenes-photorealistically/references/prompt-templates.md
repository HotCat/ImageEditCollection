# Prompt Templates

Replace every bracketed value. Keep the input order and repeat all invariants on every edit.

## Pass A — photorealistic reconstruction

```text
Purpose: final high-end photorealistic visualization of an established Godot 4 scene.

Input roles, in upload order:
1. Image 1 is the PRIMARY GODOT BEAUTY RENDER. Preserve its exact camera position, focal length, framing, room geometry, horizon, perspective, character position, pose, object placement, and shadow direction.
2. Image 2 is a DEPTH REFERENCE ONLY. Use it to preserve depth, silhouettes, spacing, occlusion, and floor contact. Do not display grayscale depth appearance.
3. Image 3 is a LINE-ART REFERENCE ONLY. Use it to preserve contours and joint positions. Do not display outlines or technical lines.
4. Image 4 is a BODY APPEARANCE REFERENCE ONLY. Match [CLOTHING AND BODY-IDENTITY FEATURES]. Do not copy its body proportions; the Godot character in image 1 is authoritative.
5. Image 5 is a HEAD IDENTITY REFERENCE ONLY. Match [FACE, SKIN, HAIR]. Do not change head size or body geometry.
6. Image 6 is a FURNITURE APPEARANCE REFERENCE ONLY. Match [MATERIAL/STYLE] while retaining the Godot object's exact size and silhouette.

Render image 1 as a convincing professional [INTERIOR/EXTERIOR] photograph: [MATERIAL DETAIL], realistic skin and hair, physically plausible light, [LENS AND SHOT], natural tonal range.

Metric and morphology lock:
The character is exactly [HEIGHT_M] m tall from floor contact to crown. [LANDMARK] is [LANDMARK_M] m high, or [RATIO_PERCENT]% of character stature, reaching [ANATOMICAL LANDMARK]. Preserve the exact projected silhouette, shoulder width, ribcage, waist, pelvis, limb lengths, joint positions, head-to-body ratio, pose, and floor contact of image 1. The character must read as [TALL/SHORT/AVERAGE] and [FIGURE DESCRIPTION], without horizontal warping.

Absolute invariants:
[CAMERA, POSE, CHARACTER COUNT, OBJECT COUNT, ROOM, LIGHTING, CONTACTS, CLOTHING].

Forbidden:
changed camera, changed pose, changed metric scale, widened or compressed body, enlarged head, extra people, duplicate limbs, malformed hands or feet, added doors/windows/furniture, visible depth map, visible line art, text, logo, watermark, borders, CGI/plastic skin.
```

Omit an input-role line when that file is not supplied, then renumber the remaining images. Do not mention absent inputs.

## Pass B — proportion correction

```text
This is a precision correction pass on a finished photorealistic Godot scene. Change ONLY the character body geometry in image 1. Preserve everything else in image 1 exactly.

Input roles, in upload order:
1. Image 1 is the EDIT TARGET: the accepted photorealistic room, objects, lighting, shadows, camera, identity, hair, and clothing.
2. Image 2 is the AUTHORITATIVE 3D GEOMETRY GUIDE: the original Godot beauty render. Match its character silhouette, projected joints, pose, floor contact, and metric proportions exactly. The modeled height is [HEIGHT_M] m.
3. Image 3 is CLOTHING REFERENCE ONLY: match [CLOTHING]. Do not copy the photographed subject's height, width, torso length, leg length, head size, or physique.
4. Image 4 is FACE/HAIR IDENTITY REFERENCE ONLY: preserve [IDENTITY]. Do not use it to change head size or body geometry.

Only required change:
Restore the exact [TALL/SLENDER/etc.] morphology of the [HEIGHT_M] m skinned 3D proxy in image 2. Remove horizontal body warping. Match its shoulders, ribcage, waist, pelvis, thighs, calves, torso length, leg length, joint locations, limb lengths, head position, hand position, foot position, and pose. Keep natural anatomy.

Metric scale lock:
The character is [HEIGHT_M] m tall. [LANDMARK] is [LANDMARK_M] m high, [RATIO_PERCENT]% of stature, reaching [ANATOMICAL LANDMARK]. Preserve this relationship. The character must visibly read as [TARGET STATURE], not [INCORRECT STATURE].

Absolute invariants — do not change:
exact framing, camera, lens, perspective, environment, objects, object dimensions, lighting, shadows, colors, facial identity, hairstyle, expression, clothing, footwear, pose, world position, and floor contact from image 1.

Forbidden:
horizontal stretching, short legs, compressed torso, widened hips or thighs, enlarged head, copied turnaround-body proportions, pose change, camera change, object change, added objects, text, watermark, CGI/plastic skin.
```

## Role-scoping rules

- Say `clothing reference only` when the turnaround person's physique differs from the GLB.
- Say `face and hair only` for head contact sheets.
- Say `material and style only` for furniture photographs.
- Never use `preserve everything` without enumerating the actual invariants.
- Do not call depth or line art a hard control channel when using HeyRoute image edit.
