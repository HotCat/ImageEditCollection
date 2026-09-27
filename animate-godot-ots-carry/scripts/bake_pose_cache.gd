extends SceneTree

## Bake an absolute-local SAM3D/NLF pose cache into an AnimationLibrary.
## Configuration is JSON so this script remains reusable across projects.

const ROTATION_SPACE := "godot4_absolute_local_bone_pose"

func _initialize() -> void:
	var arguments := OS.get_cmdline_user_args()
	if arguments.size() != 3:
		_fail("Usage: Godot --headless --path PROJECT --script bake_pose_cache.gd -- CACHE.json CONFIG.json OUTPUT.tres")
		return
	var cache := _load_json(arguments[0])
	var config := _load_json(arguments[1])
	if cache.is_empty() or config.is_empty():
		return
	if str(cache.get("rotation_space", "")) != ROTATION_SPACE:
		_fail("Motion cache must declare rotation_space=%s" % ROTATION_SPACE)
		return
	var frames := cache.get("frames", []) as Array
	var fps := float(cache.get("fps", 0.0))
	if frames.size() < 2 or fps <= 0.0:
		_fail("Motion cache needs at least two frames and a positive fps")
		return
	var base_scene_path := str(config.get("base_scene", ""))
	var skeleton_node_path := str(config.get("skeleton_node_path", ""))
	var track_skeleton_path := str(config.get("track_skeleton_path", skeleton_node_path))
	var packed := load(base_scene_path) as PackedScene
	if packed == null:
		_fail("Cannot load base_scene: %s" % base_scene_path)
		return
	var root := packed.instantiate()
	var skeleton := root.get_node_or_null(NodePath(skeleton_node_path)) as Skeleton3D
	if skeleton == null:
		root.free()
		_fail("Cannot find Skeleton3D: %s" % skeleton_node_path)
		return
	var animation_name := StringName(str(config.get("animation_name", "ots_carrier_gait")))
	var loop := bool(config.get("loop", true))
	var rebase_to_authored_pose := bool(config.get("rebase_to_authored_pose", true))
	var allowed := _allowed_bones(config.get("bones", []))
	var animation := Animation.new()
	animation.resource_name = str(animation_name)
	animation.step = 1.0 / fps
	animation.loop_mode = Animation.LOOP_LINEAR if loop else Animation.LOOP_NONE
	animation.length = frames.size() / fps if loop else (frames.size() - 1) / fps
	var first_frame := frames[0] as Dictionary
	for bone_name_value in first_frame:
		var bone_name := str(bone_name_value)
		if not allowed.is_empty() and not allowed.has(bone_name):
			continue
		var bone_index := skeleton.find_bone(StringName(bone_name))
		if bone_index < 0:
			continue
		var captured_start_value: Variant = _quaternion(first_frame.get(bone_name, []))
		if captured_start_value == null:
			continue
		var captured_start := captured_start_value as Quaternion
		var authored_start := skeleton.get_bone_pose_rotation(bone_index).normalized()
		var track := animation.add_track(Animation.TYPE_ROTATION_3D)
		animation.track_set_path(track, NodePath("%s:%s" % [track_skeleton_path, bone_name]))
		animation.track_set_interpolation_type(track, Animation.INTERPOLATION_LINEAR)
		for frame_index in frames.size():
			var frame: Variant = frames[frame_index]
			if not frame is Dictionary:
				continue
			var captured_value: Variant = _quaternion((frame as Dictionary).get(bone_name, []))
			if captured_value == null:
				continue
			var output := captured_value as Quaternion
			if rebase_to_authored_pose:
				output = (authored_start * (captured_start.inverse() * output)).normalized()
			animation.rotation_track_insert_key(track, frame_index / fps, output)
		if loop:
			var seam := authored_start if rebase_to_authored_pose else captured_start
			animation.rotation_track_insert_key(track, animation.length, seam)
	_copy_motion_metadata(animation, cache, fps)
	root.free()
	var library := AnimationLibrary.new()
	library.add_animation(animation_name, animation)
	var error := ResourceSaver.save(library, arguments[2])
	if error != OK:
		_fail("ResourceSaver failed with error %d: %s" % [error, arguments[2]])
		return
	print("Baked %s: tracks=%d frames=%d fps=%.3f length=%.3f loop=%s" % [
		animation_name, animation.get_track_count(), frames.size(), fps, animation.length, loop,
	])
	quit(0)

func _copy_motion_metadata(animation: Animation, cache: Dictionary, fps: float) -> void:
	animation.set_meta("ots_source_fps", fps)
	var clip := cache.get("clip", {}) as Dictionary
	var root_motion := cache.get("root_motion", {}) as Dictionary
	var speed := float(clip.get("recommended_speed_mps", 0.0))
	if speed <= 0.0:
		speed = _root_motion_speed(root_motion.get("positions", []), fps)
	animation.set_meta("ots_recommended_speed_mps", speed)
	var contacts := root_motion.get("contacts", {}) as Dictionary
	animation.set_meta("ots_contacts_left", contacts.get("left", []))
	animation.set_meta("ots_contacts_right", contacts.get("right", []))
	animation.set_meta("ots_local_forward", root_motion.get("local_forward", [0.0, 0.0, -1.0]))
	animation.set_meta("ots_bake_mode", str(root_motion.get("bake_mode", "captured_clip")))

func _root_motion_speed(value: Variant, fps: float) -> float:
	if not value is Array or value.size() < 2 or fps <= 0.0:
		return 0.0
	var distance := 0.0
	var previous := _vector3(value[0])
	for index in range(1, value.size()):
		var current := _vector3(value[index])
		distance += Vector2(current.x - previous.x, current.z - previous.z).length()
		previous = current
	return distance / ((value.size() - 1) / fps)

func _vector3(value: Variant) -> Vector3:
	if value is Array and value.size() >= 3:
		return Vector3(float(value[0]), float(value[1]), float(value[2]))
	return Vector3.ZERO

func _allowed_bones(value: Variant) -> Dictionary:
	var result := {}
	if value is Array:
		for bone_name in value:
			result[str(bone_name)] = true
	return result

func _quaternion(value: Variant) -> Variant:
	if value is Array and value.size() >= 4:
		return Quaternion(float(value[0]), float(value[1]), float(value[2]), float(value[3])).normalized()
	return null

func _load_json(path_string: String) -> Dictionary:
	var path := ProjectSettings.globalize_path(path_string) if path_string.begins_with("res://") else path_string
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		_fail("Cannot open JSON: %s" % path)
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary:
		_fail("Expected a JSON object: %s" % path)
		return {}
	return parsed as Dictionary

func _fail(message: String) -> void:
	push_error(message)
	quit(1)
