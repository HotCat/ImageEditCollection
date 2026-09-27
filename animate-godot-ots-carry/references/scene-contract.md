# Godot scene contract

The controller does not require exact node names, but all exported paths must
resolve. A practical hierarchy is:

```text
OTSCaryShot (Node3D, ots_carry_controller.gd)
├── CarryRigRoot (Node3D or plain grouping node)
│   ├── MaleCarrier (Node3D)
│   │   └── Skeleton3D
│   │       ├── CarryRightArmIK (TwoBoneIK3D)
│   │       └── CarryLeftArmIK (TwoBoneIK3D)
│   └── FemaleCarried (Node3D)
│       └── Skeleton3D
├── AnimationPlayer
├── PlannedTrajectory (Path3D with Curve3D)
└── CarryContacts (Node3D)
    ├── FemaleHipTarget (Marker3D)
    ├── FemaleThighTarget (Marker3D)
    ├── MaleRightElbowPole (Marker3D)
    └── MaleLeftElbowPole (Marker3D)
```

The male and female need not share a parent. Root motion advances the exported
`carrier_root_path`; the female follows the evaluated shoulder in world space.
Do not move the environment with the carrier.

## Pelvis attachment

Pose both characters at animation frame zero, select the intended
`LeftShoulder` or `RightShoulder`, then run **Calibrate pelvis at current pose**.
Calibration stores:

```text
carried_pelvis_in_shoulder = inverse(shoulder_world) * pelvis_world
```

At playback the shoulder pose is evaluated first. Position and orientation are
filtered independently. Orientation correction is applied around the current
pelvis pivot; rotating around world origin is a bug because it translates the
whole female in an arc.

Useful starting ranges:

- position lag: `0.03–0.10 s`
- orientation lag: `0.07–0.18 s`
- position weight: `1.0`
- orientation weight: `0.45–0.75`

Use more orientation lag than position lag. Large position lag visibly detaches
the pelvis; modest orientation lag reads as body inertia.

## Secondary motion

The controller uses baked left/right contact arrays. Non-contact legs and arms
receive additive rotations relative to the captured female FK baseline; contact
onset supplies a decaying body/head impact signal through the lag filter.

Start with small amplitudes. A video generator needs readable rhythm, not a
ragdoll. Tune axes per rig because local bone axes differ. If a limb twists,
fix its exported axis or sign before increasing amplitude.

## Carrier hand IK

Create two `TwoBoneIK3D` modifiers under the male skeleton:

- right upper arm → right forearm → right hand, targeting the female hip;
- left upper arm → left forearm → left hand, targeting the supported thigh.

Reverse the assignment when the authored carry pose requires it. Give each
modifier an elbow pole marker. Wire modifier and target paths into the
controller, then set contact offsets in the female bone's local space.

Keep hand IK disabled while retargeting the gait. Enable one arm at a time,
starting at influence `0.3–0.5`; move the target and pole before raising the
influence. The gait library should normally omit arm tracks so animation and IK
do not fight over the same bones.

## Root motion and foot contacts

The Animation metadata supplies contact state and recommended speed. Each
contact onset records the corresponding male foot's world position. After the
nominal trajectory step, the controller projects planted-foot error onto the
path tangent and corrects trajectory progress. When both feet are planted, it
averages both errors.

This locks progress along the planned path without pulling the character
sideways off it. It is intentionally one-dimensional along the curve tangent;
full-body dynamics and arbitrary terrain adaptation are outside this reference
animation layer.

Use a `Path3D` whose first point is the desired shot start. The controller can
align the carrier's configured local-forward vector, normally Godot `-Z`, to
the curve tangent while preserving the authored initial tilt.
