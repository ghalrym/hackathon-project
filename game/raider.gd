class_name Raider
extends Node3D
## A ship in the other side's colours. It comes past the player, settles in
## ahead at the player's speed and weaves about there, keeping out of the
## line of fire and out of the rocks, until it pulls away again.

enum Mode { ARRIVING, HOLDING, LEAVING, GONE }

const OVERTAKE := 95.0  ## How much faster than the player it comes past.
const ACCEL := 140.0  ## How quickly its engines change its speed down the lane.
const DART := 16.0  ## Its top speed across the lane,
const LIFT := 45.0  ## and how quickly it gets up to that.
const AHEAD := Vector2(10.0, 16.0)  ## How far ahead of the player it settles.
const STAY := Vector2(14.0, 20.0)  ## Seconds it flies there before pulling away.
const ROOM := Vector2(11.0, 6.0)  ## How far from the centre line it chooses to be,
const BOUNDS := Vector2(12.5, 7.0)  ## and how far it can be pushed.
const REACTION := 0.5  ## Seconds it takes to notice where the player is aiming.
const DANGER := 3.0  ## Lined up closer than this, it gets out of the way.
const HORIZON := 0.8  ## Seconds ahead it watches for rocks.
const BERTH := 0.5  ## Room it likes to leave between itself and a rock.
const SWERVES := 24  ## Directions it weighs up for a way past rocks in its path.
const BURST := 1.6  ## How much harder it can swerve than it cruises.
const GONE_Z := -360.0  ## Out of sight in the fog.
const HALF := Vector2(1.3, 0.45)  ## A bolt inside this, seen from behind, hits.
const LENGTH := 1.1  ## Half its length.
const HULL := Vector3(0.9, 0.25, 0.9)  ## What a rock has to touch to wreck it.
const ARMOUR := 4  ## Bolts it takes to bring down.

@export var hull: ShaderMaterial

var mode := Mode.GONE
var prev_z := 0.0  ## Where it was down the lane last frame.
## Out of armour: the last bolt brought it down.
var wrecked: bool:
	get:
		return _armour <= 0
## How it is moving through the field, which lies still while the player
## flies through it at the world's speed.
var velocity: Vector3:
	get:
		return Vector3(_vel.x, _vel.y, -_speed)

var _speed := 0.0  ## Its own speed down the lane; the player's is the world's.
var _post := 0.0  ## The spot ahead of the player it keeps to.
var _stay := 0.0
var _vel := Vector2.ZERO  ## Across the lane.
var _goal := Vector2.ZERO  ## Where across the lane it is making for.
var _rethink := 0.0  ## Seconds until it picks somewhere new to be.
var _dodging := 0.0  ## Seconds left of getting out of the line of fire.
var _seen := Vector2.ZERO  ## Where it thinks the player is aiming, a moment late.
var _armour := ARMOUR
var _flash := 0.0
var _heard := false

@onready var model: Node3D = $Model
@onready var _meshes := model.find_children("*", "MeshInstance3D", true, false)
@onready var _flames: Array[Node3D] = [$FlameLeft, $FlameRight]
@onready var _whoosh: AudioStreamPlayer3D = $Whoosh


func _ready() -> void:
	for mesh: MeshInstance3D in _meshes:
		mesh.material_override = hull


## Come up from [param at], behind the [param ship], and past it.
func launch(at: Vector3, speed: float, ship: Vector3) -> void:
	position = at
	rotation = Vector3.ZERO
	prev_z = at.z
	mode = Mode.ARRIVING
	_speed = speed + OVERTAKE
	_post = -randf_range(AHEAD.x, AHEAD.y)
	_stay = randf_range(STAY.x, STAY.y)
	_vel = Vector2.ZERO
	_goal = Vector2(at.x, at.y)
	_dodging = 0.0
	_seen = Vector2(ship.x, ship.y)
	_armour = ARMOUR
	_flash = 0.0
	_heard = false
	show()


## Pull away ahead and out of sight.
func leave() -> void:
	if mode != Mode.GONE:
		mode = Mode.LEAVING


func retire() -> void:
	mode = Mode.GONE
	_whoosh.stop()
	hide()


## [param speed] is the player's, [param ship] where it is and [param firing]
## whether it is shooting. [param rocks] to steer around, or null while the
## field swings past in a hard turn; [param crowd] the way to ease to keep
## clear of the others.
func fly(delta: float, speed: float, ship: Vector3, firing: bool, rocks: Asteroids, crowd: Vector2) -> void:
	prev_z = position.z
	# Down the lane: make for its post ahead of the player and keep pace there.
	# Its engines take a moment to answer, so a boost closes the gap for a while.
	var want := speed + OVERTAKE * 2.0
	if mode != Mode.LEAVING:
		var short := position.z - _post
		want = speed + signf(short) * minf(sqrt(2.0 * ACCEL * absf(short)), OVERTAKE)
	_speed = move_toward(_speed, want, ACCEL * delta)
	position.z += (speed - _speed) * delta
	match mode:
		Mode.ARRIVING:
			if absf(position.z - _post) < 3.0 and absf(_speed - speed) < 15.0:
				mode = Mode.HOLDING
		Mode.HOLDING:
			_stay -= delta
			if _stay <= 0.0:
				mode = Mode.LEAVING
		Mode.LEAVING:
			if position.z < GONE_Z:
				retire()
				return
	if not _heard and position.z < (_speed - speed) * 0.2:
		_heard = true
		_whoosh.play()

	# Across the lane: somewhere to be, unless it is lined up with the player's
	# guns, in which case anywhere else.
	var at := Vector2(position.x, position.y)
	var aim := Vector2(ship.x, ship.y)
	_seen = _seen.lerp(aim, 1.0 - exp(-delta / REACTION))
	_rethink -= delta
	_dodging -= delta
	if mode == Mode.HOLDING and _dodging <= 0.0:
		if at.distance_to(_seen) < DANGER * (1.4 if firing else 1.0):
			_dodge(at)
		elif _rethink <= 0.0:
			_wander()
	var want_vel := ((_goal - at) * 3.0).limit_length(DART)
	if absf(position.z) < 12.0:
		# Going past the player, give it room.
		var off := at - aim
		var gap := off.length()
		if gap < 4.0:
			want_vel += off / maxf(gap, 0.01) * DART * 2.0 * (1.0 - gap / 4.0)
	want_vel += crowd * DART
	var steer := want_vel
	if rocks:
		steer = _steer_clear(want_vel, at, rocks.ahead_of(position, _speed * HORIZON, DART * BURST * HORIZON))
	var urgent := _dodging > 0.0 or steer != want_vel
	_vel = _vel.move_toward(steer, LIFT * (BURST if urgent else 1.0) * delta)
	at += _vel * delta
	for axis in 2:
		if absf(at[axis]) > BOUNDS[axis]:
			at[axis] = signf(at[axis]) * BOUNDS[axis]
			_vel[axis] = 0.0
	position.x = at.x
	position.y = at.y

	# Bank into turns and pitch with climbs, like the player's ship.
	var tilt := 1.0 - exp(-8.0 * delta)
	rotation.z = lerpf(rotation.z, clampf(-_vel.x * 0.06, -0.9, 0.9), tilt)
	rotation.y = lerpf(rotation.y, clampf(-_vel.x * 0.015, -0.25, 0.25), tilt)
	rotation.x = lerpf(rotation.x, clampf(_vel.y * 0.035, -0.4, 0.4), tilt)
	for flame in _flames:
		flame.scale.y = 0.7 + _speed / 130.0
	_flash = maxf(_flash - 6.0 * delta, 0.0)
	for mesh: MeshInstance3D in _meshes:
		mesh.set_instance_shader_parameter(&"flash", _flash)


## A bolt flew straight ahead from [param from] to [param to_z] this frame.
## Returns whether it hit; each one that does chips at the armour and sends
## the raider jinking.
func struck(from: Vector3, to_z: float) -> bool:
	if mode == Mode.GONE:
		return false
	if minf(prev_z, position.z) - LENGTH > from.z or maxf(prev_z, position.z) + LENGTH < to_z:
		return false
	var off := Vector2(from.x - position.x, from.y - position.y).rotated(-rotation.z)
	if pow(off.x / HALF.x, 2.0) + pow(off.y / HALF.y, 2.0) > 1.0:
		return false
	_armour -= 1
	_flash = 1.0
	if _dodging <= 0.0:
		_dodge(Vector2(position.x, position.y))
	return true


## Of the velocities across the lane it could take up, the one nearest
## [param want] that keeps clear of [param rocks]; failing that, whichever
## gives them the widest berth.
func _steer_clear(want: Vector2, at: Vector2, rocks: Array[Asteroids.Rock]) -> Vector2:
	if rocks.is_empty() or _berth(want, at, rocks) >= 1.0:
		return want
	var choices: Array[Vector2] = [Vector2.ZERO, _vel]
	for i in SWERVES:
		for pace in [0.5, 1.0, BURST]:
			choices.append(Vector2.from_angle(TAU * i / SWERVES) * DART * pace)
	var best := want
	var best_score := -INF
	for choice in choices:
		var score := minf(_berth(choice, at, rocks), 1.0) * 1000.0 - choice.distance_to(want)
		if score > best_score:
			best_score = score
			best = choice
	return best


## How wide of [param rocks] it would pass, from [param at], by taking up
## [param across] as its velocity across the lane: under 1 it hits one.
func _berth(across: Vector2, at: Vector2, rocks: Array[Asteroids.Rock]) -> float:
	var change := across - _vel
	var settle := change.length() / (LIFT * BURST)  # seconds to take it up
	var narrowest := INF
	for rock in rocks:
		var p := rock.node.position
		var t := maxf(position.z - p.z, 0.0) / maxf(_speed + rock.drift.z, 1.0)
		var k := minf(t, settle)
		var mine := at + _vel * k + change * (0.5 * k * k / maxf(settle, 0.001)) + across * (t - k)
		var theirs := Vector2(p.x + rock.drift.x * t, p.y + rock.drift.y * t)
		var reach := Vector2(HULL.x, HULL.y) + Vector2.ONE * (rock.radius + BERTH)
		narrowest = minf(narrowest, ((mine.clamp(-BOUNDS, BOUNDS) - theirs) / reach).length())
	return narrowest


## Out of the line of fire: away from where the player seems to be aiming,
## turning back along any wall that would stop it.
func _dodge(at: Vector2) -> void:
	var away := at - _seen
	if away.length() < 0.5:
		away = Vector2.from_angle(randf() * TAU)
	var spot := at + away.normalized().rotated(randf_range(-0.7, 0.7)) * randf_range(5.0, 8.0)
	for axis in 2:
		if absf(spot[axis]) > ROOM[axis]:
			spot[axis] = 2.0 * at[axis] - spot[axis]
	_goal = spot.clamp(-ROOM, ROOM)
	_dodging = randf_range(0.5, 0.8)
	_rethink = _dodging + randf_range(0.6, 1.4)


## Somewhere new to be, not too near the player's guns.
func _wander() -> void:
	for attempt in 4:
		_goal = Vector2(randf_range(-ROOM.x, ROOM.x), randf_range(-ROOM.y, ROOM.y)) * 0.85
		if _goal.distance_to(_seen) > DANGER * 1.5:
			break
	_rethink = randf_range(1.2, 2.6)
