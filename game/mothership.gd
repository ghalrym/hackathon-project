class_name Mothership
extends Node3D
## A rare broadside pass. The carrier overtakes from behind the camera, keeps
## station off the lane while its batteries break up rocks ahead of the ship,
## then burns away into the fog. Every rock it breaks becomes debris to dodge.

const DURATION := 24.0  ## Includes flying in and peeling away.
const ENTRY := 5.0  ## Overtaking from behind the camera into its station.
const EXIT := 4.0
const MEAN_WAIT := 360.0  ## Average random wait in seconds of open flight.
const REPEAT_GRACE := 90.0
const SIZE := 4.0  ## Scale of the carrier model, which is built about 28 units long.
const STATION_DEPTH := Vector2(75.0, 125.0)  ## It drifts ahead from the first depth to the second.
const STATION_HEIGHT := 15.0
const STATION_ACROSS := 0.55  ## Hull centre, as a share of the half-width of the view.
const REFERENCE_FOV := 70.0  ## Placement ignores the speed zoom so the hull stays put in the world.
const CHARGE := 0.5
const FLASH := 0.24
const LANCE_GAP := Vector2(2.0, 3.0)  ## Seconds between main lance shots.
const BATTERY_GAP := Vector2(0.55, 1.0)  ## Seconds between broadside battery shots.
const BATTERY_FLASH := 0.16
const BATTERY_REACH := 10.0  ## Batteries take rocks this far wide of the ship's course.
## Broadside bays along the flank, in model space; the flank facing the lane fires.
const BAYS: Array[Vector3] = [
	Vector3(6.94, 0.28, 6.25), Vector3(6.94, 0.28, 3.48), Vector3(6.94, 0.28, 0.71),
	Vector3(6.94, 0.28, -2.06), Vector3(6.94, 0.28, -4.83),
]
const BEAMS := 6

## Camera shake the main scene adds while the hull passes overhead.
var rumble := 0.0

var _wait := 0.0
var _age := 0.0
var _side := 1.0
var _shot_due := 0.0
var _battery_due := 0.0
var _flash_left := 0.0
var _impact := Vector3.ZERO
var _bolts: Array[Bolt] = []


class Bolt:
	var node: MeshInstance3D
	var bay := Vector3.ZERO  ## Where on the hull it fired from, in model space.
	var impact := Vector3.ZERO
	var left := 0.0


@onready var _carrier: Node3D = $Carrier
@onready var _drives: Node3D = $Carrier/Drives
@onready var _emitter: Node3D = $Carrier/Emitter
@onready var _beam: MeshInstance3D = $Beam
@onready var _charge: MeshInstance3D = $Charge
@onready var _arrival: AudioStreamPlayer3D = $Carrier/Arrival
@onready var _discharge: AudioStreamPlayer3D = $Carrier/Discharge
@onready var _battery: AudioStreamPlayer3D = $Carrier/Battery


func _ready() -> void:
	_carrier.scale = Vector3.ONE * SIZE
	for i in BEAMS:
		var bolt := Bolt.new()
		bolt.node = _beam.duplicate()
		add_child(bolt.node)
		_bolts.append(bolt)


func reset() -> void:
	retire()
	_wait = 5.0 + _random_wait()


## An exponential wait gives even a short run a small chance of a visit.
static func _random_wait() -> float:
	return -MEAN_WAIT * log(maxf(randf(), 0.000001))


func retire() -> void:
	hide()
	_hold_fire()
	rumble = 0.0
	_arrival.stop()
	_discharge.stop()
	_battery.stop()


func _hold_fire() -> void:
	_beam.hide()
	_charge.hide()
	_flash_left = 0.0
	for bolt in _bolts:
		bolt.left = 0.0
		bolt.node.hide()


## The clock uses full unpaused frames; travel is the distance the field
## actually advanced on its capped movement step.
func advance(delta: float, travel: float, speed: float, ship: Vector3, rocks: Asteroids,
		steady: bool, room_for_pass: bool) -> void:
	if not visible:
		_wait -= delta
		if _wait > 0.0 or not steady or not room_for_pass:
			return
		_side = -1.0 if randf() < 0.5 else 1.0
		_age = 0.0
		_shot_due = ENTRY + CHARGE
		_battery_due = ENTRY * 0.7
		_wait = REPEAT_GRACE + _random_wait()
		show()
		_arrival.play()
	else:
		_age += delta
		if _age >= DURATION:
			retire()
			return
	_fly(get_viewport().get_camera_3d())
	if not steady or _age >= DURATION - EXIT:
		_hold_fire()
		return
	_fire_lance(delta, travel, speed, ship, rocks)
	_fire_batteries(delta, travel, speed, ship, rocks)


func _fire_lance(delta: float, travel: float, speed: float, ship: Vector3, rocks: Asteroids) -> void:
	_shot_due -= delta
	_flash_left = maxf(_flash_left - delta, 0.0)
	if _flash_left > 0.0:
		_impact.z += travel
	if _shot_due <= 0.0:
		var hit := rocks.shatter_in_path(ship, speed)
		if hit.is_finite():
			_impact = hit
			_flash_left = FLASH
			_shot_due = randf_range(LANCE_GAP.x, LANCE_GAP.y)
			_discharge.play()
		else:
			_shot_due = 0.18  # Hold the charge until a suitable rock comes past.

	var muzzle := _carrier.transform * _emitter.position
	var charge := 1.0 - smoothstep(0.0, CHARGE, _shot_due)
	var flash := _flash_left / FLASH
	_charge.visible = charge > 0.01 or flash > 0.0
	if _charge.visible:
		_charge.position = muzzle
		_charge.scale = Vector3.ONE * (0.35 + maxf(charge, flash) * 1.65) * SIZE * 0.6
	_beam.visible = flash > 0.0
	if _beam.visible:
		_stretch(_beam, muzzle, _impact, (0.10 + 0.42 * flash) * SIZE * 0.6)


## Quick shots from the bays on the flank facing the lane, each breaking up
## a rock somewhere ahead of the ship.
func _fire_batteries(delta: float, travel: float, speed: float, ship: Vector3, rocks: Asteroids) -> void:
	_battery_due -= delta
	if _battery_due <= 0.0:
		var hit := rocks.shatter_in_path(ship, speed, BATTERY_REACH)
		var bolt := _free_bolt()
		if hit.is_finite() and bolt:
			bolt.impact = hit
			bolt.left = BATTERY_FLASH
			bolt.bay = BAYS.pick_random() * Vector3(-_side, 1.0, 1.0)
			_battery.pitch_scale = randf_range(1.3, 1.6)
			_battery.play()
			_battery_due = randf_range(BATTERY_GAP.x, BATTERY_GAP.y)
		else:
			_battery_due = 0.12
	for bolt in _bolts:
		if bolt.left <= 0.0:
			continue
		bolt.left -= delta
		bolt.impact.z += travel
		var flash := maxf(bolt.left, 0.0) / BATTERY_FLASH
		bolt.node.visible = flash > 0.0
		if bolt.node.visible:
			_stretch(bolt.node, _carrier.transform * bolt.bay, bolt.impact, 0.25 + 0.55 * flash)


func _free_bolt() -> Bolt:
	for bolt in _bolts:
		if bolt.left <= 0.0:
			return bolt
	return null


## Lay a unit box from [param from] to [param to], [param width] across.
static func _stretch(beam: MeshInstance3D, from: Vector3, to: Vector3, width: float) -> void:
	var line := to - from
	beam.position = from + line * 0.5
	beam.basis = Basis.looking_at(line) * Basis.from_scale(Vector3(width, width, line.length()))


func _fly(camera: Camera3D) -> void:
	# Surges past the camera, then eases into station.
	var enter := 1.0 - pow(1.0 - minf(_age / ENTRY, 1.0), 3.0)
	var leave := smoothstep(DURATION - EXIT, DURATION, _age)
	var cruise := clampf((_age - ENTRY) / (DURATION - EXIT - ENTRY), 0.0, 1.0)
	var aspect := camera.get_viewport().get_visible_rect().size.aspect()
	# Stand farther off in a narrow window so the broadside stays in view.
	var narrow := maxf(1.0, 1.6 / aspect)
	var station := lerpf(STATION_DEPTH.x, STATION_DEPTH.y, smoothstep(0.0, 1.0, cruise)) * narrow
	var half_width := (station + camera.position.z) * tan(deg_to_rad(REFERENCE_FOV * 0.5)) * aspect

	# Overtake from behind and above the camera, settling into station.
	var depth := lerpf(-45.0, station, enter) + 330.0 * leave * leave
	var across := lerpf(34.0, half_width * STATION_ACROSS, enter) + 40.0 * leave
	var height := lerpf(30.0, STATION_HEIGHT, enter) + 2.5 * sin(_age * 0.37) + 50.0 * leave
	_carrier.position = Vector3(_side * across, height, -depth)

	# Turn the flank slowly toward the lane, then bank away.
	var yaw := lerpf(0.12, 0.38, enter) + 0.22 * cruise - 0.9 * leave
	# Banked so the deck faces the lane.
	var roll := lerpf(0.12, 0.34, enter) + 0.035 * sin(_age * 0.29) + 0.3 * leave
	var pitch := lerpf(0.1, 0.02, enter) + 0.015 * sin(_age * 0.41) - 0.08 * leave
	_carrier.rotation = Vector3(pitch, _side * yaw, _side * roll)
	_drives.scale.z = 1.0 + 0.06 * sin(_age * 16.0) + 0.5 * (1.0 - enter) + 2.0 * leave

	# The hull is overhead early in the overtake: shake the camera with it.
	rumble = 0.14 * (1.0 - smoothstep(0.0, 0.6, enter)) * smoothstep(0.0, 0.6, _age)
