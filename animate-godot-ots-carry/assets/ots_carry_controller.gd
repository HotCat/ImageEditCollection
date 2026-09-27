@tool
extends Node3D

## Procedural over-the-shoulder carry controller for a render-reference rig.
## Evaluation order: carrier gait -> root trajectory -> pelvis follow ->
## carried-body secondary motion -> contact targets -> carrier hand IK.

@export_category("Required Nodes")
@export var carrier_root_path: NodePath
@export var carrier_skeleton_path: NodePath
@export var carried_root_path: NodePath
@export var carried_skeleton_path: NodePath
@export var animation_player_path: NodePath
@export var trajectory_path: NodePath

@export_category("Editor Preview")
@export var preview_in_editor := true
@export var restore_carried_pose_when_preview_stops := true

@export_category("Carrier Root Motion")
@export var root_motion_enabled := true
@export var snap_to_trajectory_start := true
@export var trajectory_heading_enabled := true
@export var loop_trajectory := false
@export_range(0.0, 3.0, 0.01) var pace_scale := 1.0
@export_range(0.0, 1.0, 0.01) var planted_foot_correction := 0.85
@export var carrier_local_forward := Vector3(0.0, 0.0, -1.0)
@export var carrier_left_foot_bone: StringName = &"LeftFoot"
@export var carrier_right_foot_bone: StringName = &"RightFoot"
@export_range(0.001, 0.2, 0.001, "suffix:m") var fallback_contact_height := 0.035
@export_range(0.01, 2.0, 0.01, "suffix:m/s") var fallback_contact_speed := 0.18

@export_category("Carried Pelvis Follow")
@export var pelvis_follow_enabled := true
@export_enum("LeftShoulder", "RightShoulder") var carrier_shoulder_bone: String = "RightShoulder"
@export var carried_pelvis_bone: StringName = &"Hips"
@export var follow_shoulder_orientation := true
@export_range(0.0, 2.0, 0.01, "suffix:s") var pelvis_position_lag_seconds := 0.06
@export_range(0.0, 2.0, 0.01, "suffix:s") var pelvis_orientation_lag_seconds := 0.10
@export_range(0.0, 1.0, 0.01) var pelvis_position_weight := 1.0
@export_range(0.0, 1.0, 0.01) var pelvis_orientation_weight := 0.65
@export var auto_calibrate_pelvis_offset := true
@export_storage var carried_pelvis_in_shoulder := Transform3D.IDENTITY
@export_tool_button("Calibrate pelvis at current pose")
var calibrate_pelvis_action: Callable = calibrate_pelvis_offset

@export_category("Foot-Rhythm Secondary Motion")
@export var secondary_motion_enabled := true
@export_range(0.0, 1.0, 0.01) var secondary_motion_weight := 1.0
@export_range(0.0, 1.0, 0.01, "suffix:s") var secondary_lag_seconds := 0.08
@export_range(0.0, 45.0, 0.1, "degrees") var leg_swing_degrees := 7.0
@export_range(0.0, 45.0, 0.1, "degrees") var knee_dangle_degrees := 5.0
@export_range(0.0, 45.0, 0.1, "degrees") var foot_dangle_degrees := 4.0
@export_range(0.0, 45.0, 0.1, "degrees") var arm_swing_degrees := 8.0
@export_range(0.0, 45.0, 0.1, "degrees") var forearm_dangle_degrees := 6.0
@export_range(0.0, 30.0, 0.1, "degrees") var head_sway_degrees := 5.0
@export_range(0.0, 30.0, 0.1, "degrees") var head_nod_degrees := 3.0
@export_range(0.0, 30.0, 0.1, "degrees") var torso_bob_degrees := 2.0
@export var leg_swing_axis := Vector3.RIGHT
@export var knee_dangle_axis := Vector3.RIGHT
@export var foot_dangle_axis := Vector3.RIGHT
@export var arm_swing_axis := Vector3.RIGHT
@export var forearm_dangle_axis := Vector3.FORWARD
@export var head_sway_axis := Vector3.UP
@export var head_nod_axis := Vector3.RIGHT
@export_tool_button("Capture carried FK baseline")
var capture_baseline_action: Callable = capture_carried_baseline

@export_category("Carrier Hand Contact IK")
@export var hand_ik_enabled := false
@export var right_hand_ik_path: NodePath
@export var left_hand_ik_path: NodePath
@export var right_hand_target_path: NodePath
@export var left_hand_target_path: NodePath
@export_enum("Hips", "LeftUpperLeg", "RightUpperLeg") var right_hand_contact_bone: String = "Hips"
@export_enum("Hips", "LeftUpperLeg", "RightUpperLeg") var left_hand_contact_bone: String = "LeftUpperLeg"
@export var right_hand_contact_offset := Transform3D.IDENTITY
@export var left_hand_contact_offset := Transform3D.IDENTITY
@export_range(0.0, 1.0, 0.01) var right_hand_ik_influence := 1.0
@export_range(0.0, 1.0, 0.01) var left_hand_ik_influence := 1.0

var _carrier_initial_basis := Basis.IDENTITY
var _trajectory_progress := 0.0
var _root_initialized := false
var _pelvis_target := Transform3D.IDENTITY
var _pelvis_target_initialized := false
var _carried_initial_transform := Transform3D.IDENTITY
var _carried_baseline: Array[Transform3D] = []
var _rhythm := Vector3.ZERO
var _previous_foot_positions := {"left": Vector3.ZERO, "right": Vector3.ZERO}
var _foot_ground_y := {"left": INF, "right": INF}
var _foot_was_contact := {"left": false, "right": false}
var _foot_anchors := {"left": Vector3.ZERO, "right": Vector3.ZERO}

func _ready() -> void:
	process_priority = 100
	var carrier := _carrier_root()
	var carried := _carried_root()
	if carrier != null:
		_carrier_initial_basis = carrier.global_basis
	if carried != null:
		_carried_initial_transform = carried.global_transform
	capture_carried_baseline()
	if auto_calibrate_pelvis_offset:
		calibrate_pelvis_offset()
	_configure_hand_ik()

func _process(delta: float) -> void:
	if Engine.is_editor_hint() and not preview_in_editor:
		return
	var player := _animation_player()
	var active := player != null and player.is_playing()
	if not active:
		if Engine.is_editor_hint() and restore_carried_pose_when_preview_stops:
			_restore_carried_baseline()
		_configure_hand_ik()
		return
	var contacts := _contact_state(player, delta)
	_apply_trajectory_root(delta, contacts)
	_apply_pelvis_follow(delta)
	_apply_secondary_motion(delta, contacts)
	_update_hand_targets()
	_configure_hand_ik()

func calibrate_pelvis_offset() -> void:
	var carrier_skeleton := _carrier_skeleton()
	var carried_skeleton := _carried_skeleton()
	if carrier_skeleton == null or carried_skeleton == null:
		return
	var shoulder_index := carrier_skeleton.find_bone(StringName(carrier_shoulder_bone))
	var pelvis_index := carried_skeleton.find_bone(carried_pelvis_bone)
	if shoulder_index < 0 or pelvis_index < 0:
		return
	var shoulder := carrier_skeleton.global_transform * carrier_skeleton.get_bone_global_pose(shoulder_index)
	var pelvis := carried_skeleton.global_transform * carried_skeleton.get_bone_global_pose(pelvis_index)
	carried_pelvis_in_shoulder = shoulder.affine_inverse() * pelvis
	_pelvis_target_initialized = false
	_mark_scene_unsaved()

func capture_carried_baseline() -> void:
	var skeleton := _carried_skeleton()
	if skeleton == null:
		return
	_carried_baseline.resize(skeleton.get_bone_count())
	for bone_index in skeleton.get_bone_count():
		_carried_baseline[bone_index] = skeleton.get_bone_pose(bone_index)
	var carried := _carried_root()
	if carried != null:
		_carried_initial_transform = carried.global_transform
	_mark_scene_unsaved()

func _apply_trajectory_root(delta: float, contacts: Dictionary) -> void:
	if not root_motion_enabled:
		return
	var carrier := _carrier_root()
	var path := get_node_or_null(trajectory_path) as Path3D
	if carrier == null or path == null or path.curve == null:
		return
	var length := path.curve.get_baked_length()
	if length <= 0.0001:
		return
	if not _root_initialized:
		_root_initialized = true
		_trajectory_progress = 0.0
		_carrier_initial_basis = carrier.global_basis
		if snap_to_trajectory_start:
			_place_carrier_on_path(carrier, path, _trajectory_progress)
	var speed := _recommended_speed() * pace_scale
	_trajectory_progress += speed * maxf(delta, 0.0)
	_trajectory_progress = fposmod(_trajectory_progress, length) if loop_trajectory else clampf(_trajectory_progress, 0.0, length)
	_place_carrier_on_path(carrier, path, _trajectory_progress)
	_update_contact_anchors(contacts)
	var tangent := _path_tangent_world(path, _trajectory_progress)
	var correction_sum := 0.0
	var correction_count := 0
	for side in ["left", "right"]:
		if bool(contacts.get(side, false)) and bool(_foot_was_contact.get(side, false)):
			var current := _carrier_foot_world(side)
			correction_sum += ((_foot_anchors[side] as Vector3) - current).dot(tangent)
			correction_count += 1
	if correction_count > 0:
		_trajectory_progress += correction_sum / float(correction_count) * planted_foot_correction
		_trajectory_progress = fposmod(_trajectory_progress, length) if loop_trajectory else clampf(_trajectory_progress, 0.0, length)
		_place_carrier_on_path(carrier, path, _trajectory_progress)
	for side in ["left", "right"]:
		_foot_was_contact[side] = bool(contacts.get(side, false))

func _place_carrier_on_path(carrier: Node3D, path: Path3D, progress: float) -> void:
	carrier.global_position = path.to_global(path.curve.sample_baked(progress, true))
	if not trajectory_heading_enabled:
		return
	var tangent := _path_tangent_world(path, progress)
	var initial_forward := (_carrier_initial_basis * carrier_local_forward.normalized()).normalized()
	var from_flat := Vector3(initial_forward.x, 0.0, initial_forward.z).normalized()
	var to_flat := Vector3(tangent.x, 0.0, tangent.z).normalized()
	if from_flat.length_squared() > 0.0001 and to_flat.length_squared() > 0.0001:
		carrier.global_basis = Basis(Quaternion(from_flat, to_flat)) * _carrier_initial_basis

func _path_tangent_world(path: Path3D, progress: float) -> Vector3:
	var length := path.curve.get_baked_length()
	var epsilon := minf(0.025, maxf(length * 0.002, 0.001))
	var before := clampf(progress - epsilon, 0.0, length)
	var after := clampf(progress + epsilon, 0.0, length)
	var a := path.to_global(path.curve.sample_baked(before, true))
	var b := path.to_global(path.curve.sample_baked(after, true))
	return (b - a).normalized() if not a.is_equal_approx(b) else Vector3.FORWARD

func _apply_pelvis_follow(delta: float) -> void:
	if not pelvis_follow_enabled:
		return
	var carrier_skeleton := _carrier_skeleton()
	var carried_skeleton := _carried_skeleton()
	var carried := _carried_root()
	if carrier_skeleton == null or carried_skeleton == null or carried == null:
		return
	var shoulder_index := carrier_skeleton.find_bone(StringName(carrier_shoulder_bone))
	var pelvis_index := carried_skeleton.find_bone(carried_pelvis_bone)
	if shoulder_index < 0 or pelvis_index < 0:
		return
	var shoulder := carrier_skeleton.global_transform * carrier_skeleton.get_bone_global_pose(shoulder_index)
	var pelvis := carried_skeleton.global_transform * carried_skeleton.get_bone_global_pose(pelvis_index)
	var target := shoulder * carried_pelvis_in_shoulder
	if not _pelvis_target_initialized:
		_pelvis_target = target
		_pelvis_target_initialized = true
	_pelvis_target.origin = _pelvis_target.origin.lerp(target.origin, _lag_alpha(pelvis_position_lag_seconds, delta))
	_pelvis_target.basis = Basis(_pelvis_target.basis.get_rotation_quaternion().slerp(
		target.basis.get_rotation_quaternion(), _lag_alpha(pelvis_orientation_lag_seconds, delta)
	))
	var correction := Transform3D.IDENTITY
	var position_delta := (_pelvis_target.origin - pelvis.origin) * pelvis_position_weight
	if follow_shoulder_orientation:
		var rotation_delta := _pelvis_target.basis.get_rotation_quaternion() * pelvis.basis.get_rotation_quaternion().inverse()
		correction.basis = Basis(Quaternion.IDENTITY.slerp(rotation_delta, pelvis_orientation_weight))
	correction.origin = pelvis.origin - correction.basis * pelvis.origin + position_delta
	carried.global_transform = correction * carried.global_transform

func _apply_secondary_motion(delta: float, contacts: Dictionary) -> void:
	if not secondary_motion_enabled or _carried_baseline.is_empty():
		return
	var skeleton := _carried_skeleton()
	if skeleton == null:
		return
	var left_swing := 0.0 if bool(contacts.get("left", false)) else 1.0
	var right_swing := 0.0 if bool(contacts.get("right", false)) else 1.0
	var alternating := left_swing - right_swing
	var impact := float(contacts.get("impact", 0.0))
	var desired := Vector3(alternating, impact, left_swing - right_swing)
	_rhythm = _rhythm.lerp(desired, _lag_alpha(secondary_lag_seconds, delta))
	var weight := secondary_motion_weight
	_apply_bone_offset(skeleton, &"LeftUpperLeg", leg_swing_axis, _rhythm.x * leg_swing_degrees * weight)
	_apply_bone_offset(skeleton, &"RightUpperLeg", leg_swing_axis, -_rhythm.x * leg_swing_degrees * weight)
	_apply_bone_offset(skeleton, &"LeftLowerLeg", knee_dangle_axis, left_swing * knee_dangle_degrees * weight)
	_apply_bone_offset(skeleton, &"RightLowerLeg", knee_dangle_axis, right_swing * knee_dangle_degrees * weight)
	_apply_bone_offset(skeleton, &"LeftFoot", foot_dangle_axis, left_swing * foot_dangle_degrees * weight)
	_apply_bone_offset(skeleton, &"RightFoot", foot_dangle_axis, right_swing * foot_dangle_degrees * weight)
	_apply_bone_offset(skeleton, &"LeftUpperArm", arm_swing_axis, left_swing * arm_swing_degrees * weight)
	_apply_bone_offset(skeleton, &"RightUpperArm", arm_swing_axis, right_swing * arm_swing_degrees * weight)
	_apply_bone_offset(skeleton, &"LeftLowerArm", forearm_dangle_axis, -left_swing * forearm_dangle_degrees * weight)
	_apply_bone_offset(skeleton, &"RightLowerArm", forearm_dangle_axis, -right_swing * forearm_dangle_degrees * weight)
	_apply_bone_offset(skeleton, &"Neck", head_sway_axis, _rhythm.x * head_sway_degrees * weight)
	_apply_bone_offset(skeleton, &"Head", head_nod_axis, _rhythm.y * head_nod_degrees * weight)
	_apply_bone_offset(skeleton, &"Spine", head_nod_axis, _rhythm.y * torso_bob_degrees * weight)
	skeleton.force_update_all_bone_transforms()

func _apply_bone_offset(skeleton: Skeleton3D, bone_name: StringName, axis: Vector3, degrees: float) -> void:
	var index := skeleton.find_bone(bone_name)
	if index < 0 or index >= _carried_baseline.size():
		return
	var baseline := _carried_baseline[index]
	var posed := baseline
	if axis.length_squared() > 0.0001 and not is_zero_approx(degrees):
		posed.basis = Basis(baseline.basis.get_rotation_quaternion() * Quaternion(axis.normalized(), deg_to_rad(degrees)))
	skeleton.set_bone_pose(index, posed)

func _contact_state(player: AnimationPlayer, delta: float) -> Dictionary:
	var animation := player.get_animation(player.current_animation)
	if animation != null and animation.has_meta("ots_contacts_left") and animation.has_meta("ots_contacts_right"):
		var fps := float(animation.get_meta("ots_source_fps", 24.0))
		var left: Array = animation.get_meta("ots_contacts_left", [])
		var right: Array = animation.get_meta("ots_contacts_right", [])
		if not left.is_empty() and not right.is_empty():
			var frame := mini(int(floor(player.current_animation_position * fps)), mini(left.size(), right.size()) - 1)
			var left_contact := bool(left[frame])
			var right_contact := bool(right[frame])
			var impact := float((left_contact and not bool(_foot_was_contact.left)) or (right_contact and not bool(_foot_was_contact.right)))
			return {"left": left_contact, "right": right_contact, "impact": impact}
	return _fallback_contacts(delta)

func _fallback_contacts(delta: float) -> Dictionary:
	var result := {"left": false, "right": false, "impact": 0.0}
	for side in ["left", "right"]:
		var position := _carrier_foot_world(side)
		_foot_ground_y[side] = minf(float(_foot_ground_y[side]), position.y)
		var previous := _previous_foot_positions[side] as Vector3
		var speed := position.distance_to(previous) / maxf(delta, 0.0001) if not previous.is_zero_approx() else INF
		var contact := position.y <= float(_foot_ground_y[side]) + fallback_contact_height and speed <= fallback_contact_speed
		result[side] = contact
		if contact and not bool(_foot_was_contact[side]):
			result.impact = 1.0
		_previous_foot_positions[side] = position
	return result

func _update_contact_anchors(contacts: Dictionary) -> void:
	for side in ["left", "right"]:
		var contact := bool(contacts.get(side, false))
		if contact and not bool(_foot_was_contact[side]):
			_foot_anchors[side] = _carrier_foot_world(side)

func _carrier_foot_world(side: String) -> Vector3:
	var skeleton := _carrier_skeleton()
	if skeleton == null:
		return Vector3.ZERO
	var bone := carrier_left_foot_bone if side == "left" else carrier_right_foot_bone
	var index := skeleton.find_bone(bone)
	if index < 0:
		return Vector3.ZERO
	return (skeleton.global_transform * skeleton.get_bone_global_pose(index)).origin

func _update_hand_targets() -> void:
	var skeleton := _carried_skeleton()
	if skeleton == null:
		return
	_set_contact_target(skeleton, right_hand_target_path, StringName(right_hand_contact_bone), right_hand_contact_offset)
	_set_contact_target(skeleton, left_hand_target_path, StringName(left_hand_contact_bone), left_hand_contact_offset)

func _set_contact_target(skeleton: Skeleton3D, target_path: NodePath, bone_name: StringName, offset: Transform3D) -> void:
	var target := get_node_or_null(target_path) as Node3D
	var index := skeleton.find_bone(bone_name)
	if target != null and index >= 0:
		target.global_transform = skeleton.global_transform * skeleton.get_bone_global_pose(index) * offset

func _configure_hand_ik() -> void:
	_set_ik_state(right_hand_ik_path, hand_ik_enabled, right_hand_ik_influence)
	_set_ik_state(left_hand_ik_path, hand_ik_enabled, left_hand_ik_influence)

func _set_ik_state(path: NodePath, enabled: bool, influence_value: float) -> void:
	var modifier := get_node_or_null(path) as SkeletonModifier3D
	if modifier == null:
		return
	modifier.active = enabled and influence_value > 0.0
	modifier.influence = influence_value if enabled else 0.0

func _recommended_speed() -> float:
	var player := _animation_player()
	if player == null:
		return 0.0
	var animation := player.get_animation(player.current_animation)
	if animation != null:
		return float(animation.get_meta("ots_recommended_speed_mps", 0.0))
	return 0.0

func _restore_carried_baseline() -> void:
	var skeleton := _carried_skeleton()
	var carried := _carried_root()
	if skeleton != null and _carried_baseline.size() == skeleton.get_bone_count():
		for bone_index in skeleton.get_bone_count():
			skeleton.set_bone_pose(bone_index, _carried_baseline[bone_index])
	if carried != null and not _carried_initial_transform.is_equal_approx(Transform3D.IDENTITY):
		carried.global_transform = _carried_initial_transform
	_pelvis_target_initialized = false

func _lag_alpha(seconds: float, delta: float) -> float:
	return 1.0 if seconds <= 0.0001 else 1.0 - exp(-maxf(delta, 0.0) / seconds)

func _carrier_root() -> Node3D:
	return get_node_or_null(carrier_root_path) as Node3D

func _carrier_skeleton() -> Skeleton3D:
	return get_node_or_null(carrier_skeleton_path) as Skeleton3D

func _carried_root() -> Node3D:
	return get_node_or_null(carried_root_path) as Node3D

func _carried_skeleton() -> Skeleton3D:
	return get_node_or_null(carried_skeleton_path) as Skeleton3D

func _animation_player() -> AnimationPlayer:
	return get_node_or_null(animation_player_path) as AnimationPlayer

func _mark_scene_unsaved() -> void:
	if Engine.is_editor_hint():
		EditorInterface.mark_scene_as_unsaved()
