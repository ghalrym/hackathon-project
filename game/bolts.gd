class_name Bolts
extends MultiMeshInstance3D
## The ship's cannon fire: bolts that fly on ahead down the lane and break up
## the first rock in their way, or hit the first raider.

const SPEED := 450.0  ## How fast a bolt pulls away from the ship.
const REACH := 200.0  ## How far ahead a bolt gets before it burns out.
const INTERVAL := 0.12  ## Seconds between shots while the trigger is held.
const HOMING_INTERVAL := INTERVAL * 10.0  ## Homing bolts take this much longer to load.
const TURN := 600.0  ## How fast a homing bolt can cross the lane.
const HOMING_TINT := Color(0.7, 1.5, 2.6)  ## Homing bolts burn blue,
const HOMING_PITCH := 0.72  ## and sound deeper.
## Where the two cannons sit on the ship.
const MUZZLES: Array[Vector3] = [Vector3(-0.3, -0.05, -1.2), Vector3(0.3, -0.05, -1.2)]


class Bolt:
	var at := Vector3.ZERO
	var across := Vector2.ZERO  ## Its speed across the lane: zero unless it is homing.


## Bolts steer for the nearest raider ahead or, with none about, the first
## rock, and fire far less often.
var homing := false:
	set(value):
		homing = value
		if is_node_ready():
			_paint.albedo_color = HOMING_TINT if homing else _tint

var _flying: Array[Bolt] = []
var _cooldown := 0.0

@onready var _shot: AudioStreamPlayer = $Shot
@onready var _shot_pitch := _shot.pitch_scale
@onready var _paint: StandardMaterial3D = (multimesh.mesh as PrimitiveMesh).material
@onready var _tint := _paint.albedo_color


## Fly the bolts on, and fire more from [param ship] while [param firing].
## Whatever of [param rocks] a bolt meets is shot apart, and any of
## [param raiders] it meets is hit. [param speed] is the world's.
func advance(delta: float, firing: bool, ship: Vector3, speed: float, rocks: Asteroids, raiders: Raiders) -> void:
	_cooldown = maxf(_cooldown - delta, 0.0)
	if firing and _cooldown == 0.0:
		_cooldown = HOMING_INTERVAL if homing else INTERVAL
		for muzzle in MUZZLES:
			if _flying.size() < multimesh.instance_count:
				var bolt := Bolt.new()
				bolt.at = ship + muzzle
				_flying.append(bolt)
		_shot.pitch_scale = _shot_pitch * (HOMING_PITCH if homing else 1.0) * randf_range(0.94, 1.06)
		_shot.play()

	var step := SPEED * delta
	for i in range(_flying.size() - 1, -1, -1):
		var bolt := _flying[i]
		if homing:
			bolt.across = _steer(delta, bolt.at, speed, rocks, raiders)
			bolt.at += Vector3(bolt.across.x, bolt.across.y, 0) * delta
		var to_z := bolt.at.z - step
		if rocks.shoot(bolt.at, to_z) or raiders.shoot(bolt.at, to_z) or to_z < -REACH:
			_flying[i] = _flying[-1]
			_flying.pop_back()
		else:
			bolt.at.z = to_z
	for i in _flying.size():
		var bolt := _flying[i]
		var way := Vector3(bolt.across.x, bolt.across.y, -SPEED)
		multimesh.set_instance_transform(i, Transform3D(_along(way), bolt.at))
	multimesh.visible_instance_count = _flying.size()


func clear() -> void:
	_flying.clear()
	multimesh.visible_instance_count = 0


## The speed across the lane that brings a homing bolt at [param from] onto
## its target by the time it has closed the distance down the lane.
func _steer(delta: float, from: Vector3, speed: float, rocks: Asteroids, raiders: Raiders) -> Vector2:
	var left := REACH + from.z  # before it burns out
	# A raider keeps pace with the ship; the rocks come on at the world's speed.
	var closing := SPEED
	var target := raiders.target(from, left)
	if not target.is_finite():
		closing += speed
		target = rocks.target(from, left * closing / SPEED, TURN / closing)
	if not target.is_finite():
		return Vector2.ZERO
	var time := maxf((from.z - target.z) / closing, delta)
	return (Vector2(target.x - from.x, target.y - from.y) / time).limit_length(TURN)


## The pose of a bolt flying along [param way]: the mesh's length lies along it.
static func _along(way: Vector3) -> Basis:
	var length := way.normalized()
	var up := Vector3.RIGHT.cross(length).normalized()
	return Basis(length.cross(up), length, up)
