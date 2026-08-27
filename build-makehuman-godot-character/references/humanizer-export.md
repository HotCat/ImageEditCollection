# Humanizer-native export

Use this stage after the MPFB fit is accepted. The MPFB preset remains the editable source; Humanizer generates the final runtime representation.

## Why the second stage is mandatory

The successful portable proxy uses:

- one Humanizer-generated `Avatar` mesh with one surface per body/head equipment item;
- one Humanizer retargeted skeleton and skin;
- Humanizer-native fitting for body, eyes, eyebrows, eyelashes, and hair;
- morphological height calibration before export;
- bundled Idle and Run animations for deformation QA.

A Blender scene with separately bone-parented hair, sclera, irises, pupils, or lashes can look correct in Blender and even after one re-import, yet detach in Godot or another glTF consumer because rigid node transforms and skin bind space are interpreted differently. Do not repair this by adding more parent transforms. Re-export through Humanizer as one combined skinned Avatar.

## Gender semantics

Presets written by `regenerate_mpfb_actor.py` use the MPFB/MakeHuman convention observed in this pipeline:

| Body | MPFB preset | Humanizer macro |
|---|---:|---:|
| Female | 1 | 0 |
| Male | 0 | 1 |

Use `--gender-map invert` for these presets. Use `identity` only when the input JSON is known to already use Humanizer semantics. Always inspect the output report rather than trusting the numeric value alone.

For a male actor, the minimum report evidence is:

```json
{
  "source_gender_value": 0.0,
  "gender_mapping": "invert",
  "humanizer_gender_value": 1.0,
  "sex_label": "male"
}
```

If the source is ambiguous, ask the user or run two labeled clay comparisons. Do not infer sex from clothing alone.

## Equipment selection

The exporter derives `young_<dominant-race>_<sex>` for the body material and selects a conservative default hair asset. Override `--body-material`, `--hair`, and `--hair-material` from visible evidence.

Examples:

```text
--hair Hair-Short01
--hair Hair-Short03
--hair Hair-Ponytail01_Rigged --hair-material brown
--hair none
```

Confirm each asset exists in the target Humanizer project's generated equipment registry. A hairstyle is a proxy silhouette, not an identity-perfect hair reconstruction.

Garments are not part of the neutral exporter. Add clothing only as Humanizer/MHCLO equipment fitted after the body profile is calibrated. Do not merge garment geometry into the body and do not use the garment silhouette to alter hidden anatomy.

## Target transfer and height

The exporter copies macro values plus every custom target recognized by the installed Humanizer target registry. Review `rejected_custom_targets`; a large or anatomically important rejected set means the Humanizer data version does not match the MPFB target set.

After transferring all targets, the exporter binary-searches only Humanizer's height
macro until the fitted `Body-Default` vertex range from sole to visible crown matches
the supplied anatomical height within 0.1 mm. It reports `get_head_height()` only as a
helper landmark. Do not calibrate from that helper or from combined Avatar bounds:
the former can differ from visible geometry and the latter can include hair. The
exporter does not globally scale the node, mesh, or skeleton, so equipment refits and
bind/rest spaces remain consistent.

The neutral proxy deliberately keeps the complete body/scalp under fitted hair because
it has no garments requiring deletion masks. Applying Humanizer's hair deletion mask can
remove the crown and shorten the exported visible character. A later dressed build may
hide body faces under garments, but it must preserve the calibrated neutral body profile.

The calibrated Humanizer height macro normally differs from the MPFB preset height value because custom leg, neck, head, and torso targets also affect stature. This difference is expected.

glTF skin/rest transforms can still shift fresh-imported visible bounds by several
millimetres even when source body arrays are exact. Use `build_humanizer_proxy.py`,
which measures every generated GLB in a factory Blender process and feeds the error
back into Humanizer morphology. The wrapper measures deformed material/surface `0`,
the body-first invariant of this combined exporter, rather than the whole Avatar.
This prevents short hair, a ponytail, or other head equipment from changing anatomical
stature. The report preserves both `final_fresh_import_body_height_m` and the separate
hair-inclusive `final_fresh_import_visual_height_m`. It must report
`global_scale_used: false`, a passed strict validation, and a final imported body
height inside tolerance. It also records `body_surface_index` and
`surface_equipment_order`; the wrapper stops if body is no longer surface `0` rather
than silently measuring the wrong equipment after a Humanizer upgrade.

## Required final invariants

- `combined_avatar_mesh_count` equals 1;
- every raw glTF mesh node has a `skin` index;
- fresh import exposes one payload mesh and one armature;
- surface count covers requested equipment: normally 8 for body, two eyes, hair,
  two eyebrows, and two eyelashes; 7 when `--hair none`; 1 for `--no-face-parts`;
- bone count is normally 56 with rigged ponytail, or at least the configured humanoid minimum;
- Idle and Run exist;
- fitted body geometry and fresh-import body height match within 1 mm (hair is excluded from the target measurement);
- rest, Run, and 40-degree head-turn renders pass visual review;
- Godot import and retarget pass before the result is called Godot-ready.

If any attachment gate fails, do not fall back to custom bone parenting. Diagnose Humanizer equipment registration, combined mesh generation, skin weights, or the selected rig.
