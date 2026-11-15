class_name Station
extends Node3D
## A space station. Its origin is where a ship parks, in the middle of a hangar
## bay that runs straight through it along z. It comes down the lane like
## everything else, then takes over the ship and the camera to bring the ship
## in to land.

const APPEAR := 760.0  ## How far ahead a station shows up, well beyond the fog.
const DOCK_RANGE := 430.0  ## It takes over once the ship is this close.
const DOCK_TIME := 9.0  ## The landing, from takeover to touchdown.
const FLYBY_SHOT := 3.2  ## When the landing cuts to the camera off the bay mouth,
const BAY_SHOT := 4.3  ## and when it cuts to the one inside.
const ENTRANCE := 56.0  ## z of the mouth the ship flies in through.
const EXIT := -80.0  ## Far edge of the frame around the outbound bay mouth.
const HOVER := 1.6  ## Height above the pad the ship flies through the bay at.
const GONE := 280.0  ## Once it is this far behind the ship, none of it is in view.
const MENU_VIEW := Vector3(5.2, 1.7, -6.4)  ## Where the camera rests while parked.

## Still on its way to the ship, as opposed to landed at or left behind.
var arriving := false
## The ship is down on the pad.
var landed: bool:
	get:
		return _time >= DOCK_TIME

var _time := 0.0  ## Seconds into the landing.
var _run := 0.0  ## How far away the pad was when it began.
var _from := Vector2.ZERO  ## Where across the lane the ship was then.
var _view_from := Transform3D.IDENTITY  ## The camera then, relative to the ship.
var _fov_from := 0.0


func appear() -> void:
	position = Vector3(0, 0, -APPEAR)
	arriving = true
	show()


func park() -> void:
	position = Vector3.ZERO
	arriving = false
	_time = DOCK_TIME
	show()
	$Ventilation.play()


func cleared_exit(ship: Ship) -> bool:
	return to_local(ship.global_position).z < EXIT - Ship.HALF.z


func dismiss() -> void:
	arriving = false
	$Ventilation.stop()
	hide()


## Drift toward the ship, and on past it, with the rest of the world.
func advance(delta: float, speed: float) -> void:
	position.z += speed * delta
	if position.z > GONE:
		dismiss()


func in_range() -> bool:
	return arriving and position.z >= -DOCK_RANGE


func begin_landing(ship: Ship, camera: Camera3D) -> void:
	arriving = false
	$Ventilation.play()
	_time = 0.0
	_run = -position.z
	_from = Vector2(ship.position.x, ship.position.y)
	_view_from = camera.transform.translated(-ship.position)
	_fov_from = camera.fov


## Fly the ship in to the pad and take the camera through the landing's three
## shots. Returns the speed the world is passing at.
func land(delta: float, ship: Ship, camera: Camera3D) -> float:
	_time = minf(_time + delta, DOCK_TIME)
	var u := _time / DOCK_TIME
	# Come in fast and ease to a stop exactly on the pad.
	position.z = -_run * pow(1.0 - u, 3.0)
	var speed := 3.0 * _run * pow(1.0 - u, 2.0) / DOCK_TIME

	# Line up with the bay on the way in, then settle onto the pad.
	var height := HOVER * (1.0 - smoothstep(0.8, 1.0, u))
	ship.target = _from.lerp(Vector2(0, height), smoothstep(0.0, 0.35, u))
	ship.thrust = 1.0 - smoothstep(0.85, 1.0, u)
	ship.lower_gear(smoothstep(0.71, 0.86, u))
	ship.advance(delta, speed)

	var at := ship.position
	if _time < FLYBY_SHOT:
		# Hang back from the chase view as the station comes out of the haze and
		# the ship flies on toward it.
		var k := smoothstep(0.0, 1.0, _time / FLYBY_SHOT)
		camera.fov = lerpf(_fov_from, 46.0, k)
		camera.position = at + _view_from.origin.lerp(Vector3(4.5, 2.0, 15.0), k)
		var ahead := at + _view_from.basis * Vector3(0, 0, -40)
		camera.look_at(ahead.lerp(to_global(Vector3(0, 10, ENTRANCE)), k))
	elif _time < BAY_SHOT:
		# Low on the approach, just off the ship's line: it sweeps past the lens
		# and on into the bay mouth.
		camera.position = to_global(Vector3(-7.0, 0.4, ENTRANCE + 34.0))
		camera.look_at(at)
		var tight := rad_to_deg(2.0 * atan(4.5 / camera.position.distance_to(at)))
		camera.fov = clampf(tight, 30.0, 60.0)
	else:
		# Inside, backing away ahead of the ship as it slows, and coming to rest
		# with it.
		var k := smoothstep(0.0, 1.0, (_time - BAY_SHOT) / (DOCK_TIME - BAY_SHOT))
		var lead := Vector3(3.0, 1.8, -9.0).lerp(MENU_VIEW, k)
		_look_from(camera, Vector3(0, 0, to_local(at).z) + lead, at, k)
	return speed


## The camera while parked: resting ahead of the ship, drifting a little.
func idle(camera: Camera3D, ship: Ship) -> void:
	var sway := sin(Time.get_ticks_msec() / 1000.0 * 0.35) * 0.06
	_look_from(camera, MENU_VIEW.rotated(Vector3.UP, sway), ship.position, 1.0)


## Aim the camera at the ship from a point in the bay. [param aside] slides the
## ship toward the left of the frame, leaving room for the hangar menu.
func _look_from(camera: Camera3D, from: Vector3, at: Vector3, aside: float) -> void:
	camera.fov = 42.0
	camera.position = to_global(from)
	camera.look_at(at + Vector3(0, 0.4, 0))
	camera.h_offset = 2.6 * aside
