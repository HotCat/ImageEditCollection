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

For both male and female builds, verify that the clay body—not clothing or hair—matches
the intended sex, stature, shoulder/torso/hip proportions, muscle, weight, and limb
segment lengths. Reject a numerically correct height attached to the wrong body sex.

## Humanizer conversion

Require the conversion report to show:

- correct MPFB source gender, explicit mapping mode, Humanizer gender, and sex label;
- intended body material and hairstyle equipment;
- all important custom targets recognized, with rejected targets reviewed;
- fitted `Body-Default` sole-to-crown geometry calibration within 0.1 mm, without
  using helper head height, hair-inclusive bounds, or global root scale;
- freshly imported, armature-deformed body surface `0` within 1 mm of anatomical
  height, with the hair-inclusive visual height reported separately;
- one combined Avatar mesh, one skeleton, expected head/body equipment surfaces,
  and Idle/Run animations.

Inspect the fresh-import rest, Run, and head-turn renders. Reject floating or detached
eyes, eyebrows, eyelashes, scalp hair, ponytail/hair cards, or head accessories. Also
reject eye surfaces outside the sockets, hair intersecting the skull badly, or limbs
collapsing during Run.

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
- for the Humanizer final proxy, exactly one imported payload mesh and no raw mesh
  node without a skin index;
- enough primitive surfaces to account for body, eyes, eyebrows, eyelashes, and hair;
- required Idle and Run animation clips.

Raw GLB evidence takes precedence over Blender importer object names. An importer may create display geometry locally that is absent from the file.

A generic “at least one weighted mesh” check is insufficient: it allows a weighted body
plus rigid hair/eye nodes. Use the strict validator flags from `SKILL.md` for the final proxy.
For the Humanizer combined proxy, also pass `--height-surface-index 0`; whole-Avatar
bounds include hair and are not anatomical stature.
