extends Node

## Export one MakeHuman/MPFB preset as a Humanizer-native Godot 4 proxy.
##
## Install this script and export_humanizer_proxy.tscn inside the target Humanizer
## project's `tools/build_makehuman_godot_character/` directory. Run the scene with
## user arguments after `--`; see SKILL.md for the complete command. Keeping the
## exporter inside the project is important because Humanizer registers its service
## classes and generated equipment resources through the project autoload/plugin.
##
## The final GLB intentionally contains one combined, skinned Avatar mesh. Do not
## export eyes or hair as Blender bone-parented objects: that representation looked
## correct after one Blender re-import but detached in another real GLB consumer.


const DEFAULT_TARGET_HEIGHT_M := 1.75
const HEIGHT_ITERATIONS := 24
const HEIGHT_EPSILON_M := 0.0001


func _parse_user_args() -> Dictionary:
	var result := {
		"preset": "",
		"output": "",
		"report": "",
		"height": DEFAULT_TARGET_HEIGHT_M,
		"rig": "",
		"gender_map": "invert",
		"body_material": "",
		"hair": "auto",
		"hair_material": "",
		"include_face_parts": true,
	}
	var args := OS.get_cmdline_user_args()
	var index := 0
	while index < args.size():
		var flag := args[index]
		if flag == "--no-face-parts":
			result.include_face_parts = false
			index += 1
			continue
		if index + 1 >= args.size():
			_fatal("Missing value after " + flag)
		var value := args[index + 1]
		match flag:
			"--preset": result.preset = value
			"--output": result.output = value
			"--report": result.report = value
			"--height": result.height = float(value)
			"--rig": result.rig = value
			"--gender-map": result.gender_map = value
			"--body-material": result.body_material = value
			"--hair": result.hair = value
			"--hair-material": result.hair_material = value
			_: _fatal("Unknown argument: " + flag)
		index += 2
	if result.preset.is_empty() or result.output.is_empty() or result.report.is_empty():
		_fatal("Required arguments: --preset, --output, --report, and --height")
	if result.height <= 0.5 or result.height >= 2.6:
		_fatal("--height must be a plausible anatomical height in metres")
	if result.gender_map not in ["invert", "identity"]:
		_fatal("--gender-map must be 'invert' or 'identity'")
	return result


func _fatal(message: String) -> void:
	push_error(message)
	get_tree().quit(2)
	# Stop the current call immediately as get_tree().quit() is deferred.
	assert(false, message)


func _read_preset(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		_fatal("MPFB preset does not exist: " + path)
	var file := FileAccess.open(path, FileAccess.READ)
	var parsed = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary:
		_fatal("MPFB preset is not a JSON object: " + path)
	if not parsed.has("phenotype") or not parsed.phenotype is Dictionary:
		_fatal("MPFB preset has no phenotype dictionary: " + path)
	return parsed


func _humanizer_gender(source_gender: float, mapping: String) -> float:
	# MPFB/MakeHuman presets produced by the bundled builder encode female at 1
	# and male at 0. Humanizer's macro service encodes female at 0 and male at 1.
	# The explicit switch prevents a silent male/female body inversion if a future
	# preset source uses Humanizer's convention directly.
	return 1.0 - source_gender if mapping == "invert" else source_gender


func _actor_targets(preset: Dictionary, gender_mapping: String) -> Dictionary:
	var phenotype: Dictionary = preset.phenotype
	var targets := {}
	for name in ["age", "cupsize", "firmness", "height", "muscle", "proportions", "weight"]:
		if phenotype.has(name):
			targets[name] = float(phenotype[name])
	targets.gender = _humanizer_gender(float(phenotype.get("gender", 0.5)), gender_mapping)
	var race: Dictionary = phenotype.get("race", {})
	for race_name in HumanizerMacroService.race_options:
		targets[race_name] = float(race.get(race_name, 0.0))

	# Humanizer silently ignores unknown target data when applying it to vertices.
	# Filter explicitly so the report can prove which identity/body targets survived.
	for entry in preset.get("targets", []):
		if entry is Dictionary and entry.has("target") and entry.has("value"):
			var target_name := str(entry.target)
			if target_name in HumanizerTargetService.data:
				targets[target_name] = float(entry.value)
	return targets


func _race_label(phenotype: Dictionary) -> String:
	var race: Dictionary = phenotype.get("race", {})
	var best_name := "caucasian"
	var best_value := -1.0
	for name in ["african", "asian", "caucasian"]:
		var value := float(race.get(name, 0.0))
		if value > best_value:
			best_name = name
			best_value = value
	return best_name


func _sex_label(humanizer_gender: float) -> String:
	return "male" if humanizer_gender >= 0.5 else "female"


func _default_body_material(phenotype: Dictionary, humanizer_gender: float) -> String:
	# Humanizer's bundled body library contains young_<race>_<sex> materials.
	# This is an appearance default only; morphology comes from macro/detail targets.
	return "young_%s_%s" % [_race_label(phenotype), _sex_label(humanizer_gender)]


func _default_hair(humanizer_gender: float) -> String:
	# A caller should override this from visible reference evidence. These defaults
	# merely keep the generated head complete for unattended female and male tests.
	return "Hair-Short01" if humanizer_gender >= 0.5 else "Hair-Ponytail01_Rigged"


func _equipment(type_name: String, material_name: String = "") -> HumanizerEquipment:
	return (
		HumanizerEquipment.new(type_name, material_name)
		if not material_name.is_empty()
		else HumanizerEquipment.new(type_name)
	)


func _add_head_equipment(humanizer: Humanizer, hair_type: String, hair_material: String) -> void:
	# Add head equipment only after anatomical body-height calibration. Hair assets
	# can hide scalp triangles or extend above the cranium and must not influence it.
	humanizer.add_equipment(HumanizerEquipment.new("RightEye-LowPolyEyeball"))
	humanizer.add_equipment(HumanizerEquipment.new("LeftEye-LowPolyEyeball"))
	humanizer.add_equipment(HumanizerEquipment.new("RightEyebrow-002"))
	humanizer.add_equipment(HumanizerEquipment.new("LeftEyebrow-002"))
	humanizer.add_equipment(HumanizerEquipment.new("RightEyelash"))
	humanizer.add_equipment(HumanizerEquipment.new("LeftEyelash"))
	if hair_type != "none":
		humanizer.add_equipment(_equipment(hair_type, hair_material))


func _body_geometry_height(humanizer: Humanizer) -> float:
	# Measure the fitted body equipment itself. `get_head_height()` is a MakeHuman
	# helper landmark and can differ from the visible crown/sole mesh by centimetres;
	# combined Avatar bounds can instead include hair above the cranium. Neither is
	# acceptable for calibrating a known anatomical height.
	var body_equipment := humanizer.human_config.get_equipment_in_slot("body")
	if body_equipment == null or not humanizer.mesh_arrays.has(body_equipment.type):
		_fatal("Humanizer body equipment arrays are missing")
	var vertices: PackedVector3Array = humanizer.mesh_arrays[body_equipment.type][Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = humanizer.mesh_arrays[body_equipment.type][Mesh.ARRAY_INDEX]
	if vertices.is_empty():
		_fatal("Humanizer body equipment contains no vertices")
	if indices.is_empty():
		_fatal("Humanizer body equipment contains no triangle indices")
	var minimum_y := INF
	var maximum_y := -INF
	# MHCLO arrays can retain unreferenced helper/deleted vertices. Measuring only
	# indexed triangles matches the geometry that glTF actually exports and renders.
	for vertex_index in indices:
		var vertex := vertices[vertex_index]
		minimum_y = minf(minimum_y, vertex.y)
		maximum_y = maxf(maximum_y, vertex.y)
	return maximum_y - minimum_y


func _calibrate_height(humanizer: Humanizer, target_height: float) -> Dictionary:
	# Refit only the height macro. Humanizer then recomputes the body, equipment,
	# skeleton, and skin weights in a shared space. Never globally scale the GLB root.
	var low := 0.0
	var high := 1.0
	var best_macro := float(humanizer.human_config.targets.macro.get("height", 0.5))
	var best_height := _body_geometry_height(humanizer)
	for _iteration in HEIGHT_ITERATIONS:
		var candidate := (low + high) * 0.5
		humanizer.set_targets({"height": candidate})
		var measured := _body_geometry_height(humanizer)
		if absf(measured - target_height) < absf(best_height - target_height):
			best_macro = candidate
			best_height = measured
		if measured < target_height:
			low = candidate
		else:
			high = candidate
	humanizer.set_targets({"height": best_macro})
	return {
		"macro": best_macro,
		"measured_height_m": _body_geometry_height(humanizer),
		"helper_head_height_m": humanizer.get_head_height(),
		"target_height_m": target_height,
		"absolute_error_m": absf(_body_geometry_height(humanizer) - target_height),
	}


func _write_glb(node: Node, path: String) -> Dictionary:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var gltf := GLTFDocument.new()
	var state := GLTFState.new()
	var append_error := gltf.append_from_scene(node, state)
	var write_error := ERR_CANT_CREATE
	if append_error == OK:
		write_error = gltf.write_to_filesystem(state, path)
	return {"append": append_error, "write": write_error}


func _ready() -> void:
	call_deferred("_run")


func _run() -> void:
	var args := _parse_user_args()
	var preset := _read_preset(args.preset)
	var phenotype: Dictionary = preset.phenotype
	var source_gender := float(phenotype.get("gender", 0.5))
	var mapped_gender := _humanizer_gender(source_gender, args.gender_map)
	var body_material: String = args.body_material
	if body_material.is_empty():
		body_material = _default_body_material(phenotype, mapped_gender)
	var hair_type: String = args.hair
	if hair_type == "auto":
		hair_type = _default_hair(mapped_gender)

	var humanizer := Humanizer.new()
	var config := HumanConfig.new()
	config.set_targets(_actor_targets(preset, args.gender_map))
	config.rig = args.rig if not args.rig.is_empty() else str(
		ProjectSettings.get_setting("addons/humanizer/default_skeleton")
	)
	config.add_equipment(_equipment("Body-Default", body_material))

	# In headless mode geometry fitting finishes before the optional overlay-texture
	# await. Avoid awaiting a viewport texture render that has no headless viewport.
	humanizer.load_config_async(config)
	var height_calibration := _calibrate_height(humanizer, args.height)
	if height_calibration.absolute_error_m > HEIGHT_EPSILON_M:
		_fatal(
			"Height calibration error %.6f m exceeds %.6f m"
			% [height_calibration.absolute_error_m, HEIGHT_EPSILON_M]
		)
	if args.include_face_parts:
		_add_head_equipment(humanizer, hair_type, args.hair_material)
	# This neutral proxy has no garments that require body deletion masks. Keep the
	# full calibrated scalp/body underneath fitted hair; applying hair delete masks
	# can remove the visible crown and shorten the exported character by ~1 cm.
	var character: CharacterBody3D = humanizer.get_CharacterBody3D(false)
	character.name = "%s_Humanizer_RealtimeProxy" % args.output.get_file().get_basename()
	add_child(character)

	# Rebuild the one Avatar mesh after all target and equipment fitting. This single
	# combined mesh is the portability invariant that prevents detached head parts.
	var avatar := character.get_node("Avatar") as MeshInstance3D
	avatar.mesh = humanizer.get_combined_meshes()
	var skeletons := character.find_children("*", "Skeleton3D", true, false)
	var player := character.get_node_or_null("AnimationTree/AnimationPlayer") as AnimationPlayer
	var animations := PackedStringArray()
	if player != null:
		animations = player.get_animation_list()

	var export_result := _write_glb(character, args.output)
	var equipment_slots := {}
	var surface_equipment_order := []
	for equipment in config.equipment.values():
		# Humanizer's combined mesh appends one surface in this same equipment
		# insertion order. Body-Default is deliberately installed first so the
		# outer Blender calibration can measure anatomy without hair/face parts.
		surface_equipment_order.append(equipment.type)
		for slot in equipment.get_type().slots:
			equipment_slots[slot] = equipment.type

	var recognized_targets := []
	var rejected_targets := []
	for entry in preset.get("targets", []):
		var name := str(entry.get("target", ""))
		if name in HumanizerTargetService.data:
			recognized_targets.append(name)
		else:
			rejected_targets.append(name)
	var report := {
		"pipeline": "Humanizer native combined-skinned Avatar",
		"source_preset": args.preset,
		"source_gender_value": source_gender,
		"gender_mapping": args.gender_map,
		"humanizer_gender_value": mapped_gender,
		"sex_label": _sex_label(mapped_gender),
		"body_material": body_material,
		"hair_equipment": hair_type,
		"target_height_m": args.height,
		"calibrated_body_geometry_height_m": height_calibration.measured_height_m,
		"helper_head_height_m": humanizer.get_head_height(),
		"height_error_m": height_calibration.absolute_error_m,
		"calibrated_height_macro": height_calibration.macro,
		"recognized_custom_target_count": recognized_targets.size(),
		"recognized_custom_targets": recognized_targets,
		"rejected_custom_targets": rejected_targets,
		"surface_count": avatar.mesh.get_surface_count(),
		"body_surface_index": surface_equipment_order.find("Body-Default"),
		"surface_equipment_order": surface_equipment_order,
		"combined_avatar_mesh_count": 1,
		"skeleton_count": skeletons.size(),
		"skeleton_bone_count": (
			(skeletons[0] as Skeleton3D).get_bone_count() if not skeletons.is_empty() else 0
		),
		"equipment_slots": equipment_slots,
		"animations": animations,
		"gltf_append_error": export_result.append,
		"gltf_write_error": export_result.write,
		"output_glb": args.output,
	}
	DirAccess.make_dir_recursive_absolute(args.report.get_base_dir())
	var report_file := FileAccess.open(args.report, FileAccess.WRITE)
	report_file.store_string(JSON.stringify(report, "  "))
	print("HUMANIZER_PROXY_VALIDATION_BEGIN")
	print(JSON.stringify(report, "  "))
	print("HUMANIZER_PROXY_VALIDATION_END")
	get_tree().quit(0 if export_result.write == OK else 3)
