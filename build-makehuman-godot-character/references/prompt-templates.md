# Turnaround prompting

`scripts/generate_turnaround.py` contains the canonical prompts. Keep these constraints when extending them.

## Invariants for every view

- Edit the original character reference; do not generate from text alone.
- Preserve facial identity, age, ethnicity, skin tone, height impression, shoulder/waist/hip proportions, hairstyle, hair length/color, and the same fitted modest outfit.
- Use the identical A-pose, expression, studio lighting, neutral background, lens family, crop policy, and camera height.
- Use one generation call per view. Do not ask a model to draw a multi-panel sheet; panel identities and proportions drift.
- For the body, request an orthographic-like 100 mm studio lens and complete hair-to-feet framing.
- For the head, request a separate square 135 mm view containing the full cranium, ears, hair, and upper neck.

## Required views

Generate front, front-left 45 degrees, exact left profile, exact back, exact right profile, and front-right 315 degrees. Use exact profiles to estimate depth and three-quarter views to detect inconsistent feature placement.

## Regeneration cues

Regenerate only the failed view and repeat all invariants. Useful corrective clauses include:

- "The person must remain exactly the same; restore the original eye spacing, jaw, nose, and hairline."
- "Keep both arms at the same A-pose angle and both feet flat; do not mirror or change the outfit."
- "Use a level camera with no top-down view, low-angle view, foreshortening, or wide-angle distortion."
- "Show the actual back of the same hairstyle and clothing; do not add logos, seams, accessories, or exposed skin."

Do not use a generated view merely because its angle is correct. Identity and proportional consistency are separate acceptance conditions.
