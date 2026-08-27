# Godot 4 handoff

1. Copy the validated Humanizer-native GLB and any external textures into a dedicated project asset directory. Delete or invalidate an older import with the same filename so Godot cannot display a cached defective proxy.
2. Let Godot import the GLB, open Advanced Import Settings, and inspect the `Skeleton3D`, skinned meshes, materials, scale, and axis orientation.
3. Create or assign a `BoneMap` using `SkeletonProfileHumanoid`. Map pelvis/hips, spine, chest, neck, head, clavicles, upper/lower arms, hands, upper/lower legs, feet, and toes. MPFB's `game_engine` names are not a guarantee that every animation library will auto-map them.
4. Retarget a short neutral idle and walk. Test the rest pose before complex motion.
5. Inspect shoulder roll, elbow bend, hip rotation, thigh twist, knee direction, ankle/foot contact, and hand orientation from front, profile, and back views.
6. Confirm the visible height in a metre-scaled Godot scene and check that the root remains at ground level.
7. Rotate the Head bone and play Run. Confirm that eyes, eyebrows, eyelashes, scalp
   hair, and any ponytail/hair bones remain attached. Confirm the imported character
   exposes one combined Avatar mesh rather than rigid head-part nodes.

Call the result Godot-friendly only when import and retarget succeed. If the GLB imports but the thighs twist or the character lies down, diagnose bone mapping, rest-pose orientation, axis conversion, and root transform before changing mesh topology.

The final GLB is a baked runtime snapshot of a Humanizer configuration, not the complete
editable Humanizer recipe. Preserve the MPFB preset and Humanizer project/configuration
inputs if runtime morphs, garment fitting, equipment sockets, or later regeneration are required.
