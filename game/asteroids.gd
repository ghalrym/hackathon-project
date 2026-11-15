class_name Asteroids
extends Node3D
## The asteroid field: a pool of rocks streaming toward the camera.

const SPAWN_Z := -430.0  ## Past the fog, so rocks fade in rather than pop.
const BEHIND_Z := 20.0
const LANE := Vector2(15, 9)  ## Half-extents of the corridor the ship flies in.
const AIMED := 0.3  ## Share of lane rocks thrown at where the ship is now.
const SCENERY_PER_UNIT := 0.03
const TURN_CLEAR := 200.0  ## Lane left empty this far ahead after a hard turn.
## Built by tools/build_asteroid_models.py; each has a mean radius of 1.
const MODELS: Array[PackedScene] = [
	preload("res://assets/models/asteroids/asteroid-01.glb"),
	preload("res://assets/models/asteroids/asteroid-02.glb"),
	preload("res://assets/models/asteroids/asteroid-03.glb"),
	preload("res://assets/models/asteroids/asteroid-04.glb"),
	preload("res://assets/models/asteroids/asteroid-05.glb"),
	preload("res://assets/models/asteroids/asteroid-06.glb"),
]
const WHOOSHES: Array[AudioStream] = [
	preload("res://assets/audio/flyby-01.ogg"),
	preload("res://assets/audio/flyby-02.ogg"),
]
const WHOOSH_LEAD := 0.18  ## Seconds before a rock passes that its whoosh starts.
const WHOOSH_RANGE := 5.0  ## Only rocks passing this close to the ship are heard.
const WHOOSH_SPEED := 80.0  ## Slower than this, rocks drift by silently.
const CRACK: AudioStream = preload("res://assets/audio/rock-fracture.ogg")
const VOICES := 8
const BOLT_WIDTH := 0.3  ## How far wide of a rock a bolt can pass and still hit it.
const PIECES := Vector2i(28, 56)  ## How many fragments a shot rock breaks into.
const PIECE_SIZE := Vector2(0.3, 1.4)  ## The smallest and largest a fragment gets.
## Fragments spread slowly enough to still be crowding the lane when they
## reach the ship: this fast across it at most,
const SCATTER := 9.0
const SURGE := 8.0  ## and this fast ahead of or behind where the rock was.
const RAM := 1.2  ## Ram plating breaks intact rocks up to this radius, and any fragment.
const GRAZE := 0.6  ## A rock passing this close to the ship's hull is a near miss.

## A rock of [param radius] was shot apart at [param at].
signal shattered(at: Vector3, radius: float)
## An intact lane rock went past the ship within GRAZE of it.
signal grazed


class Rock:
	var node: MeshInstance3D
	var radius := 1.0
	var axis := Vector3.UP
	var spin := 0.0
	var drift := Vector3.ZERO
	var prev_z := 0.0
	var lane := false
	var heard := false
	var fragment := false  ## A piece of a shot rock, too small to break again.
	var brake := 0.0  ## How quickly its drift slows (u/s²) until it lies still like the rest.


## No new rocks set off while this is on: a station is coming.
var quiet := false

var _meshes: Array[Mesh] = []
var _active: Array[Rock] = []
var _idle: Array[Rock] = []
var _voices: Array[AudioStreamPlayer3D] = []
var _next_voice := 0
var _lane_due := 0.0
var _scenery_due := 0.0


func _ready() -> void:
	for model in MODELS:
		var scene := model.instantiate()
		var source: MeshInstance3D = scene.find_children("*", "MeshInstance3D", true, false)[0]
		_meshes.append(source.mesh)
		scene.free()
	for i in VOICES:
		var voice := AudioStreamPlayer3D.new()
		voice.bus = &"SFX"
		# Loudness is set per whoosh; position only pans it.
		voice.attenuation_model = AudioStreamPlayer3D.ATTENUATION_DISABLED
		voice.panning_strength = 2.0
		add_child(voice)
		_voices.append(voice)


## Move the field toward the camera. [param lane_rate] is rocks per second
## thrown down the ship's corridor (0 keeps it empty); [param aim] is the ship.
func advance(delta: float, speed: float, lane_rate: float, aim: Vector3) -> void:
	if not quiet:
		_scenery_due += delta * speed * SCENERY_PER_UNIT
		while _scenery_due >= 1.0:
			_scenery_due -= 1.0
			_spawn(false, aim, _spawn_z())
		_lane_due += delta * lane_rate
		while _lane_due >= 1.0:
			_lane_due -= 1.0
			_spawn(true, aim, _spawn_z())

	for i in range(_active.size() - 1, -1, -1):
		var rock := _active[i]
		rock.prev_z = rock.node.position.z
		rock.drift = rock.drift.move_toward(Vector3.ZERO, rock.brake * delta)
		rock.node.position += (rock.drift + Vector3(0, 0, speed)) * delta
		rock.node.rotate(rock.axis, rock.spin * delta)
		if not rock.heard and rock.node.position.z > -speed * WHOOSH_LEAD:
			rock.heard = true
			if speed > WHOOSH_SPEED:
				_whoosh(rock, aim)
		if rock.lane and not rock.fragment and rock.prev_z < aim.z and rock.node.position.z >= aim.z:
			var off := Vector2(rock.node.position.x - aim.x, rock.node.position.y - aim.y)
			var reach := Vector2(Ship.HALF.x, Ship.HALF.y) + Vector2.ONE * (rock.radius + GRAZE)
			if (off / reach).length() < 1.0:
				grazed.emit()
		if rock.node.position.z > BEHIND_Z:
			_retire(i)


## Does any rock overlap an ellipsoid of the given half-extents this frame?
func hits(centre: Vector3, half: Vector3) -> bool:
	for rock in _active:
		if _overlaps(rock, centre, half):
			return true
	return false


## Ram plating: every fragment and small rock overlapping an ellipsoid of the
## given half-extents this frame goes to dust. Returns how many did.
func ram(centre: Vector3, half: Vector3) -> int:
	var broken := 0
	for i in range(_active.size() - 1, -1, -1):
		var rock := _active[i]
		if (rock.fragment or rock.radius <= RAM) and _overlaps(rock, centre, half):
			var at := rock.node.position
			_retire(i)
			_crack(at, rock.radius)
			shattered.emit(at, rock.radius)
			broken += 1
	return broken


## The rocks something at [param at] will meet in the next [param look] of
## travel down the lane, if it stays within [param near] of where it is.
func ahead_of(at: Vector3, look: float, near: float) -> Array[Rock]:
	var found: Array[Rock] = []
	for rock in _active:
		var p := rock.node.position
		var ahead := at.z - p.z
		if ahead < -rock.radius or ahead > look:
			continue
		if Vector2(p.x - at.x, p.y - at.y).length() < near + rock.radius:
			found.append(rock)
	return found


## A bolt flew straight ahead from [param from] to [param to_z] this frame.
## The first rock in its way stops it, and is shot apart unless it is a
## fragment, which is too small to break again. Returns whether there was one.
func shoot(from: Vector3, to_z: float) -> bool:
	var first := -1
	for i in _active.size():
		var rock := _active[i]
		var p := rock.node.position
		if p.z + rock.radius < to_z or rock.prev_z - rock.radius > from.z:
			continue
		var reach := rock.radius + BOLT_WIDTH
		if Vector2(p.x - from.x, p.y - from.y).length_squared() > reach * reach:
			continue
		if first < 0 or p.z > _active[first].node.position.z:
			first = i
	if first < 0:
		return false
	if not _active[first].fragment:
		_shatter(first)
	return true


## The crash: whatever rock the ship ran into breaks up with it, rather than
## sailing on whole between the wreck and the camera.
func smash(centre: Vector3, half: Vector3) -> void:
	for i in range(_active.size() - 1, -1, -1):
		if not _active[i].fragment and _overlaps(_active[i], centre, half):
			_shatter(i)


## Where the first intact lane rock ahead of a homing bolt at [param from] is,
## within [param look] down the lane and no further across it than the bolt
## can turn: [param slope] across for each unit it closes. INF when there is none.
func target(from: Vector3, look: float, slope: float) -> Vector3:
	var found := Vector3.INF
	for rock in _active:
		if not rock.lane or rock.fragment:
			continue
		var p := rock.node.position
		var ahead := from.z - p.z
		if ahead < 0.0 or ahead > look or (found.is_finite() and p.z < found.z):
			continue
		if Vector2(p.x - from.x, p.y - from.y).length() - rock.radius <= slope * ahead:
			found = p
	return found


## Break up an intact lane rock whose drift will carry it within [param reach]
## of the ship's course. Return the impact point for the beam, or INF when no
## rock qualifies.
func shatter_in_path(ship: Vector3, speed: float, reach := 6.0) -> Vector3:
	var best := -1
	var closest := INF
	for i in _active.size():
		var rock := _active[i]
		if not rock.lane or rock.fragment:
			continue
		var at := rock.node.position
		var arrival := (ship.z - at.z) / maxf(speed + rock.drift.z, 1.0)
		if arrival < 0.9 or arrival > 1.8:
			continue
		var crossing := at + rock.drift * arrival
		var gap := Vector2(crossing.x - ship.x, crossing.y - ship.y).length() - rock.radius
		if gap < reach and gap < closest:
			closest = gap
			best = i
	if best < 0:
		return Vector3.INF
	var impact := _active[best].node.position
	_shatter(best)
	return impact


func clear_lane() -> void:
	for i in range(_active.size() - 1, -1, -1):
		if _active[i].lane:
			_retire(i)
	_lane_due = 0.0


## Swap the whole field for a fresh one, as a hard turn does: backdrop rocks
## all the way down the tunnel, lane rocks ([param lane_density] per unit of
## distance) only beyond TURN_CLEAR.
func reroll(lane_density: float, aim: Vector3) -> void:
	for i in range(_active.size() - 1, -1, -1):
		_retire(i)
	if quiet:
		return
	for i in roundi(SCENERY_PER_UNIT * (BEHIND_Z - SPAWN_Z)):
		_spawn(false, aim, randf_range(SPAWN_Z, BEHIND_Z))
	for i in roundi(lane_density * (-TURN_CLEAR - SPAWN_Z)):
		_spawn(true, aim, randf_range(SPAWN_Z, -TURN_CLEAR))


## Where new rocks start: past the fog, staggered so they do not arrive in step.
static func _spawn_z() -> float:
	return SPAWN_Z - randf_range(0, 30)


func _spawn(lane: bool, aim: Vector3, z: float) -> void:
	var size: float
	var at: Vector2
	var drift := Vector3.ZERO
	if lane:
		size = 0.9 + 3.2 * pow(randf(), 2.0)
		if randf() < AIMED:
			at = Vector2(aim.x + randf_range(-3, 3), aim.y + randf_range(-3, 3))
		else:
			at = Vector2(randf_range(-LANE.x, LANE.x), randf_range(-LANE.y, LANE.y))
		drift = Vector3(randf_range(-1.5, 1.5), randf_range(-1.0, 1.0), 0)
	else:
		# Big backdrop rocks, kept well clear of the lane.
		size = randf_range(3, 11)
		at = Vector2.from_angle(randf() * TAU) * randf_range(size * 1.4 + LANE.x + 4, 95)

	var rock := _place(Vector3(at.x, at.y, z), size)
	rock.lane = lane
	rock.drift = drift


## Throw a piece of wreckage into the field: [param mesh] painted with
## [param material], posed at [param place] and [param radius] across for
## collisions. Like a rock's fragment it stops bolts without breaking. It
## sets off with [param drift] through the field, slowing at [param brake]
## until it lies still like the rocks.
func scatter(mesh: Mesh, material: Material, place: Transform3D, radius: float, drift: Vector3, brake: float) -> void:
	var piece := _place(place.origin, 1.0)
	piece.node.mesh = mesh
	piece.node.material_override = material
	piece.node.transform = place
	piece.node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	piece.radius = radius
	piece.spin = randf_range(1.5, 5.0)
	piece.lane = true
	piece.fragment = true
	piece.heard = true
	piece.drift = drift
	piece.brake = brake


## Break up the rock at [param i] into a burst of small ones: a patch of
## debris that widens across the lane as it comes on, thickest where the rock
## was headed.
func _shatter(i: int) -> void:
	var rock := _active[i]
	var at := rock.node.position
	var radius := rock.radius
	var drift := rock.drift
	_retire(i)
	for n in clampi(roundi(22 + 10 * radius), PIECES.x, PIECES.y):
		var size := clampf(radius * randf_range(0.2, 0.45), PIECE_SIZE.x, PIECE_SIZE.y)
		var piece := _place(at + _random_direction() * radius * randf_range(0.2, 0.9), size)
		# More of them hang together than fly wide.
		var across := Vector2.from_angle(randf() * TAU) * pow(randf(), 1.5) * SCATTER
		piece.lane = true
		piece.fragment = true
		piece.heard = true  # no fly-by of its own: the burst has been heard
		piece.drift = drift + Vector3(across.x, across.y, randf_range(-SURGE, SURGE))
		piece.node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_crack(at, radius)
	shattered.emit(at, radius)


## Take a rock from the pool and set it down at [param at], [param size]
## across, in a random pose.
func _place(at: Vector3, size: float) -> Rock:
	var rock: Rock = _create() if _idle.is_empty() else _idle.pop_back()
	rock.lane = false
	rock.fragment = false
	rock.heard = false
	rock.drift = Vector3.ZERO
	rock.brake = 0.0
	rock.radius = size * 0.82
	rock.spin = randf_range(0.2, 1.2) / sqrt(size)
	rock.axis = _random_direction()
	rock.prev_z = at.z
	rock.node.mesh = _meshes.pick_random()
	rock.node.material_override = null
	rock.node.position = at
	rock.node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	# A random pose, and a slightly different squash each time so the six
	# models do not read as six.
	var squash := Vector3(randf_range(0.88, 1.12), randf_range(0.88, 1.12), randf_range(0.88, 1.12))
	rock.node.basis = Basis.from_euler(Vector3(randf(), randf(), randf()) * TAU).scaled_local(squash * size)
	rock.node.show()
	_active.append(rock)
	return rock


## Play a fly-by for a rock about to pass close to the ship: louder the
## nearer the miss, deeper the bigger the rock.
func _whoosh(rock: Rock, aim: Vector3) -> void:
	var p := rock.node.position
	var gap := Vector2(p.x - aim.x, p.y - aim.y).length() - rock.radius
	if gap > WHOOSH_RANGE:
		return
	var loudness := lerpf(0.0, -15.0, clampf(gap / WHOOSH_RANGE, 0.0, 1.0))
	var pitch := lerpf(1.25, 0.8, clampf(rock.radius / 3.5, 0.0, 1.0))
	_sound(WHOOSHES.pick_random(), p, loudness, pitch)


## Play a rock breaking up: louder and deeper the bigger it was.
func _crack(at: Vector3, radius: float) -> void:
	var big := clampf(radius / 3.0, 0.0, 1.0)
	_sound(CRACK, at, lerpf(-17.0, -1.0, big), lerpf(1.28, 0.88, big))


func _sound(stream: AudioStream, at: Vector3, loudness: float, pitch: float) -> void:
	var voice := _voices[_next_voice]
	_next_voice = (_next_voice + 1) % VOICES
	voice.stream = stream
	voice.position = Vector3(at.x, at.y, 0)
	voice.volume_db = loudness
	voice.pitch_scale = pitch * randf_range(0.92, 1.08)
	voice.play()


## Does [param rock] overlap an ellipsoid of the given half-extents this frame?
static func _overlaps(rock: Rock, centre: Vector3, half: Vector3) -> bool:
	var p := rock.node.position
	# The rock swept from prev_z to p.z this frame; measure from that span.
	var dz := maxf(maxf(rock.prev_z - centre.z, centre.z - p.z), 0.0)
	var x := (p.x - centre.x) / (half.x + rock.radius)
	var y := (p.y - centre.y) / (half.y + rock.radius)
	var z := dz / (half.z + rock.radius)
	return x * x + y * y + z * z < 1.0


func _create() -> Rock:
	var rock := Rock.new()
	rock.node = MeshInstance3D.new()
	add_child(rock.node)
	return rock


func _retire(i: int) -> void:
	var rock := _active[i]
	rock.node.hide()
	_active[i] = _active[-1]
	_active.pop_back()
	_idle.append(rock)


static func _random_direction() -> Vector3:
	return Vector3(randfn(0, 1), randfn(0, 1), randfn(0, 1)).normalized()
