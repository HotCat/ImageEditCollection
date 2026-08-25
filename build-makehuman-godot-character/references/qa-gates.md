# Quality gates

## Generated reference views

Accept each view only when all are true:

- same facial identity, age, ethnicity, hairline, hairstyle, body proportions, and skin tone;
- same A-pose, hand orientation, foot stance, clothing, expression, crop, lens character, camera height, and lighting;
- no duplicated body parts, asymmetric limb length, invented garment features, beauty-filter drift, or perspective exaggeration;
- person mask contains the entire intended silhouette without background islands or lost limbs.

Use side and three-quarter views only as geometry guides unless the cameras are calibrated. Reject a view for texture projection when its features cannot be aligned to actual model landmarks.

## Geometry and rig

Inspect the clay turntable at full resolution. Reject and iterate on:

- wrong known height, shoulder/hip depth, head size, limb segment length, or foot placement;
- joints outside the body volume or clearly misplaced relative to shoulder, elbow, wrist, hip, knee, ankle, neck, or head;
- asymmetric A-pose, helper geometry visible as anatomy, or garment silhouette baked into the body;
- deformations that collapse shoulders, hips, knees, or thighs during an idle/walk retarget.

## Texture bake

The exact check names accepted by `record_texture_qa.py` are:

- `identity_match`
- `no_duplicate_features`
- `no_neck_projection`
- `no_uv_seams`
- `no_background_contamination`
- `front_clean`
- `profiles_clean`
- `back_clean`
- `closeup_clean`

Inspect front, both profiles, back, three-quarter views, and the face close-up. A passing front view alone is insufficient. Reject duplicated eyes/lips/nose, face pixels on neck or ears, gray studio background in skin, UV island streaks, abrupt seams, smeared profiles, mirrored text/details, or identity drift.

Bake from a temporary skin-only mesh. Exclude MPFB helper geometry, joint cubes, teeth, tongue, eyes, eyelashes, hair, garments, and proxies because their overlapping UVs can contaminate visible skin.

When any check fails, keep the bake and report as experimental, then deliver the clean neutral realtime proxy. Never relabel a distorted bake as production-ready.

## GLB

Require:

- valid GLB 2 header and raw JSON;
- at least one raw mesh and one raw skin;
- armature and weighted mesh after fresh import;
- expected humanoid bone count and height within tolerance;
- no raw `Icosphere` or other editor-only rig display shapes;
- resolved materials and embedded or adjacent texture resources as intended.

Raw GLB evidence takes precedence over Blender importer object names. An importer may create display geometry locally that is absent from the file.
