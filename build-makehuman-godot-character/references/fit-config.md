# MPFB fit configuration

Create a JSON object with `macro`, `detail_targets`, and an optional neutral proxy skin color:

```json
{
  "macro": {
    "gender": 1.0,
    "age": 0.45,
    "muscle": 0.35,
    "weight": 0.40,
    "proportions": 0.60,
    "cupsize": 0.30,
    "firmness": 0.65,
    "race": {"asian": 1.0, "caucasian": 0.0, "african": 0.0}
  },
  "detail_targets": [
    {"target": "torso/measure-shoulder-dist-decr", "weight": 0.10},
    {"target": "legs/upperlegs-height-incr", "weight": 0.05}
  ],
  "neutral_skin_rgba": [0.46, 0.27, 0.19, 1.0]
}
```

The values above illustrate syntax only. Do not reuse them as an identity preset.

## Female and male gender values

For presets created by the bundled MPFB builder, use:

- `"gender": 1.0` for a female body;
- `"gender": 0.0` for a male body.

Humanizer uses the opposite numeric convention. The final exporter must therefore
run with `--gender-map invert`. Never copy the numeric gender value directly into
Humanizer and never infer it from hairstyle or clothing.

A minimal male syntax example is:

```json
{
  "macro": {
    "gender": 0.0,
    "age": 0.42,
    "muscle": 0.48,
    "weight": 0.38,
    "proportions": 0.62,
    "cupsize": 0.0,
    "firmness": 0.5,
    "race": {"asian": 1.0, "caucasian": 0.0, "african": 0.0}
  },
  "detail_targets": [],
  "neutral_skin_rgba": [0.46, 0.27, 0.19, 1.0]
}
```

These male values still illustrate syntax only. Fit shoulder width, torso depth,
waist/hip ratio, limb circumference, neck, head, jaw, and face from accepted image
evidence; do not reuse a stereotyped male template.

There is no deterministic mapping from silhouette scanlines to MPFB target weights in this skill. An agent must make a documented, conservative parameter fit, render it, compare it with accepted views, and iterate. Do not describe this manual/visual fit as an automatic inverse-model optimizer.

## Fitting order

1. Set macro age, explicit gender/body sex parameter, muscle, weight, proportions, race mixture, and other visible global features. Confirm the resulting clay body visually before fitting details.
2. Fit the known body height. The script evaluates target geometry and uses the native `body` vertex group; never measure static undeformed `body.data` coordinates.
3. Fit head height/width/depth, shoulder width, torso width/depth, waist, hips, leg segment lengths, arm segment lengths, and circumferences in that order.
4. Refit height after detail targets because segment changes can alter total height.
5. Add face details conservatively from high-resolution head references. Prioritize cranium depth, jaw/chin silhouette, nose projection, eye spacing, and ear position.
6. Render a clay turntable and iterate. Save each accepted config; do not make undocumented Blender sculpt changes that the MPFB preset cannot reproduce.
7. After serializing the preset, inspect its `phenotype.gender`, `phenotype.race`, and target list. The Humanizer stage consumes this JSON and reports every recognized or rejected target.

## Evidence rules

- Front/back views support width and vertical landmarks.
- Exact profiles support body/head depth and nose/chin silhouette.
- Three-quarter views expose identity drift and implausible interpolation.
- Skirts and coats do not reveal hip or waist anatomy.
- Heels do not reveal foot length or barefoot height.
- Hair silhouette does not reveal cranium shape without a separate head reference.

Use MPFB's bundled target browser or target listing sample to confirm target names. The build script fails on unknown targets instead of silently ignoring them.
