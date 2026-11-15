class_name Raiders
extends Node3D
## Now and then other ships come past and fly with the player for a while,
## keeping out of its line of fire as best they can. Shooting one down is
## worth a bounty, but it flies apart into wreckage the player then has to
## get out of the way of.

const RAIDER: PackedScene = preload("res://game/raider.tscn")
## The pieces a raider breaks into, each placed where it sat on the ship.
const WRECK: PackedScene = preload("res://assets/models/raider-wreck.glb")
const BOUNTY := 1000.0  ## Points for shooting one down.
const FIRST := Vector2(20.0, 30.0)  ## Seconds into a run before the first comes.
const BETWEEN := Vector2(25.0, 40.0)  ## Seconds after one lot has gone before the next.
const PAIRS_AFTER := 90.0  ## Seconds into a run after which they may come in pairs,
const PAIR_CHANCE := 0.4  ## this often.
const START_Z := 30.0  ## Behind the camera, so they come past the ship.
const PASS := Vector2(4.0, 6.0)  ## How wide of the ship they come past.
const SPACE := 4.0  ## How close they let each other come.
const BLAST := 7.0  ## How hard a wreck's pieces can be flung apart; most go slower.
const WEAVE_KEPT := 0.1  ## Share of the raider's speed across the lane its wreck keeps.
const SHARDS := 24  ## Smaller bits of hull thrown out along with the big pieces.
const SHARD_SIZE := Vector2(0.35, 0.65)  ## Of the piece each is a bit of.
## How quickly the wreckage loses the raider's way (u/s²): the player runs
## into it a second or so after shooting it down.
const LOSE_WAY := 26.0

## A raider was shot down at [param at].
signal downed(at: Vector3)

## How much more often they come: it grows with each station passed.
var pressure := 1.0

var _ships: Array[Raider] = []
var _wait := 0.0  ## Seconds until the next lot comes.
var _steady := false
var _rocks: Asteroids  ## Where wreckage goes.
var _pieces: Array[MeshInstance3D] = []  ## Of a whole raider's model, unbroken.

@onready var _explosion: CPUParticles3D = $Explosion
@onready var _bang: AudioStreamPlayer3D = $Bang


func _ready() -> void:
	for i in 2:
		var raider: Raider = RAIDER.instantiate()
		add_child(raider)
		raider.retire()
		_ships.append(raider)
	var wreck := WRECK.instantiate()
	for piece: MeshInstance3D in wreck.find_children("*", "MeshInstance3D", true, false):
		_pieces.append(piece)
	add_child(wreck)
	wreck.hide()


## A fresh run: none about, and the first a while off.
func reset() -> void:
	clear()
	_wait = randf_range(FIRST.x, FIRST.y)


## Gone at once, as when the ship lands at a station.
func clear() -> void:
	for raider in _ships:
		raider.retire()


## Any about pull away and leave: the run is over, or a station is coming.
func dismiss() -> void:
	for raider in _ships:
		raider.leave()


## [param speed] is the player's, [param ship] where it is. New ones only
## turn up while [param calling]. While [param steady] (the field is not
## swinging past in a hard turn) they steer around rocks, can hit them and
## can be shot.
func advance(delta: float, speed: float, ship: Vector3, elapsed: float, calling: bool,
		steady: bool, firing: bool, rocks: Asteroids) -> void:
	_steady = steady
	_rocks = rocks
	if calling and _ships.all(func(raider: Raider) -> bool: return raider.mode == Raider.Mode.GONE):
		_wait -= delta * pressure
		if _wait <= 0.0:
			_wait = randf_range(BETWEEN.x, BETWEEN.y)
			_call(speed, ship, 2 if elapsed > PAIRS_AFTER and randf() < PAIR_CHANCE else 1)
	for raider in _ships:
		if raider.mode == Raider.Mode.GONE:
			continue
		raider.fly(delta, speed, ship, firing, rocks if steady else null, _crowd(raider))
		if steady and raider.mode != Raider.Mode.GONE and rocks.hits(raider.position, Raider.HULL):
			_wreck(raider)


## A bolt flew straight ahead from [param from] to [param to_z] this frame.
## Returns whether a raider stopped it; the last one a raider can take
## brings it down.
func shoot(from: Vector3, to_z: float) -> bool:
	if not _steady:
		return false
	for raider in _ships:
		if raider.struck(from, to_z):
			if raider.wrecked:
				var at := raider.position
				_wreck(raider)
				downed.emit(at)
			return true
	return false


## Where the nearest raider ahead of a homing bolt at [param from] is, within
## [param look] down the lane. INF when there is none.
func target(from: Vector3, look: float) -> Vector3:
	var found := Vector3.INF
	for raider in _ships:
		var ahead := from.z - raider.position.z
		if raider.mode == Raider.Mode.GONE or ahead < Raider.LENGTH or ahead > look:
			continue
		if not found.is_finite() or raider.position.z > found.z:
			found = raider.position
	return found


## Send [param count] past the [param ship], a pair one on each side.
func _call(speed: float, ship: Vector3, count: int) -> void:
	var side := Vector2.from_angle(randf() * TAU)
	for i in count:
		var lane := Vector2(ship.x, ship.y) + side * randf_range(PASS.x, PASS.y)
		lane = lane.clamp(-Raider.ROOM, Raider.ROOM)
		_ships[i].launch(Vector3(lane.x, lane.y, START_Z + 12.0 * i), speed, ship)
		side = -side


## Which way [param raider] should ease to keep its distance from the others.
func _crowd(raider: Raider) -> Vector2:
	var push := Vector2.ZERO
	for other in _ships:
		if other == raider or other.mode == Raider.Mode.GONE:
			continue
		if absf(raider.position.z - other.position.z) > 8.0:
			continue
		var off := Vector2(raider.position.x - other.position.x, raider.position.y - other.position.y)
		var gap := off.length()
		if gap < SPACE:
			push += off / maxf(gap, 0.01) * (1.0 - gap / SPACE)
	return push


func _wreck(raider: Raider) -> void:
	_explosion.position = raider.position
	_explosion.restart()
	_bang.position = raider.position
	_bang.play()
	_break_up(raider)
	raider.retire()


## Fly apart: the hull's pieces, and smaller bits of them, carry on with the
## raider's way, flung out from the middle, and lose it until the player
## runs into the wreckage.
func _break_up(raider: Raider) -> void:
	var hull := raider.model.global_transform
	for piece in _pieces:
		_fling(raider, piece.mesh, hull * piece.transform, 1.0)
	for i in SHARDS:
		var piece: MeshInstance3D = _pieces.pick_random()
		var place := hull * piece.transform
		place.basis = Basis.from_euler(Vector3(randf(), randf(), randf()) * TAU) * place.basis
		_fling(raider, piece.mesh, place, randf_range(SHARD_SIZE.x, SHARD_SIZE.y))


## Send one piece of [param raider] off from [param place], shrunk to [param shrink].
func _fling(raider: Raider, mesh: Mesh, place: Transform3D, shrink: float) -> void:
	place.basis = place.basis.scaled_local(Vector3.ONE * shrink)
	var out := place.origin - raider.global_position
	out = (out + Vector3(randfn(0, 0.4), randfn(0, 0.4), randfn(0, 0.4))).normalized()
	var size := mesh.get_aabb().size * place.basis.get_scale()
	# It keeps the raider's speed down the lane but little of its weaving, and
	# more of it hangs together than flies wide, as with a shot rock.
	var way := raider.velocity * Vector3(WEAVE_KEPT, WEAVE_KEPT, 1.0)
	_rocks.scatter(mesh, raider.hull, place, size.length() * 0.35,
			way + out * pow(randf(), 1.5) * BLAST, LOSE_WAY)
