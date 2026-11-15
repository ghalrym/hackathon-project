class_name Ship
extends Node3D
## The player's ship: eases toward a target point, banking into turns.

const FOLLOW := 7.0  ## How fast the ship closes on its target (1/s).
## Collision ellipsoid half-extents - a little smaller than the hull.
const HALF := Vector3(0.8, 0.2, 0.85)
const SURGE := 12.0  ## How fast the afterburner comes up (1/s),
const EBB := 4.0  ## and how fast it dies away.
const SWELL := 0.35  ## How much wider the flames burn with it lit.
const KICK_TIME := 0.3  ## Seconds an ignition pulse takes to run down the flames,
const KICK_REACH := 0.25  ## and how much longer it throws them.
const RAM_UP := 9.0  ## How fast the ram plating's field comes up and drops (1/s),
const RAM_FLARE := 5.0  ## and how fast a rock's flare on it fades.
# Lateral spacing, longitudinal position of the pair, and centre hardpoint.
const GEAR_MOUNTS := {
	&"Delta": Vector3(0.36, 0.39, -0.52), &"Kestrel": Vector3(0.26, 0.38, -0.47),
	&"Manta": Vector3(0.57, 0.36, -0.34), &"Gemini": Vector3(0.54, -0.47, 0.50),
}

## Where to fly to, in the plane the ship moves in.
var target := Vector2.ZERO
## Hard turn in progress: -1..1 to the right and up. The ship throws itself
## over that way.
var lean := Vector2.ZERO
## Engine output, 0..1: scales the flames and the engine's sound.
var thrust := 1.0
## Afterburner lit: the flames surge and throw sparks.
var boosting := false:
	set(value):
		if value and not boosting:
			_kick = 0.0
		boosting = value
## Ram plating at work: its field shows about the nose.
var ramming := false
var _boost := 0.0  ## How far the afterburner has come up, 0..1.
var _ram := 0.0  ## How far the ram plating's field has come up, 0..1.
var _ram_struck := 0.0  ## Flare left from the last rock broken on it.
var _kick := 1.0  ## How far down the flames the ignition pulse has run; 1 is spent.
var _drive_emissions: Dictionary[BaseMaterial3D, float] = {}
var _lit_thrust := -1.0

@onready var _flames: Array[MeshInstance3D] = [$FlameLeft, $FlameRight]
@onready var _flame_size: Vector3 = $FlameLeft.scale
@onready var _sparks: CPUParticles3D = $Sparks
@onready var _ram_field: MeshInstance3D = $Ram
@onready var _hulls: Node3D = $Hulls
@onready var _engine: AudioStreamPlayer = $Engine
@onready var _engine_volume := _engine.volume_db


func _ready() -> void:
	# The bay probe captures the static building and luminaires around the ship.
	for node: MeshInstance3D in find_children("*", "MeshInstance3D", true, false):
		node.layers = 2
		for surface in node.mesh.get_surface_count():
			var mat := node.mesh.surface_get_material(surface) as BaseMaterial3D
			if mat and mat.emission_enabled:
				_drive_emissions[mat] = mat.emission_energy_multiplier


func select_hull(hull_name: StringName) -> void:
	var hull: Node3D = _hulls.get_node(NodePath(hull_name))
	for model in _hulls.get_children():
		model.visible = model == hull
	var nozzle: Vector3 = hull.get_node("Exhaust").position
	_flames[0].position = Vector3(-nozzle.x, nozzle.y, nozzle.z)
	_flames[1].position = nozzle
	_sparks.emission_points = PackedVector3Array([_flames[0].position, _flames[1].position])
	var mounts: Vector3 = GEAR_MOUNTS[hull_name]
	$Undercarriage/Centre.position = Vector3(0, -0.095, mounts.z)
	$Undercarriage/Port.position = Vector3(-mounts.x, -0.095, mounts.y)
	$Undercarriage/Starboard.position = Vector3(mounts.x, -0.095, mounts.y)


func lower_gear(amount: float) -> void:
	$Undercarriage.visible = amount > 0.02
	for leg: Node3D in $Undercarriage.get_children():
		leg.rotation.x = (1.0 - amount) * 1.48


func advance(delta: float, speed: float) -> void:
	var offset := target - Vector2(position.x, position.y)
	var velocity := offset * FOLLOW
	var step := offset * (1.0 - exp(-FOLLOW * delta))
	position += Vector3(step.x, step.y, 0)

	# Bank into turns and pitch with climbs.
	var tilt := 1.0 - exp(-10.0 * delta)
	rotation.z = lerpf(rotation.z, clampf(-velocity.x * 0.05, -0.75, 0.75) - lean.x * 1.2, tilt)
	rotation.y = lerpf(rotation.y, clampf(-velocity.x * 0.012, -0.2, 0.2) - lean.x * 0.5, tilt)
	rotation.x = lerpf(rotation.x, clampf(velocity.y * 0.03, -0.35, 0.35) + lean.y * 0.8, tilt)

	_boost = lerpf(_boost, 1.0 if boosting else 0.0, 1.0 - exp(-(SURGE if boosting else EBB) * delta))
	_kick = minf(_kick + delta / KICK_TIME, 1.0)
	var wide := 1.0 + SWELL * _boost
	var length := (0.7 + speed / 130.0) * thrust * (1.0 + KICK_REACH * (1.0 - _kick))
	for flame in _flames:
		flame.visible = thrust > 0.01
		flame.scale = Vector3(_flame_size.x * wide, length, _flame_size.z * wide)
		flame.set_instance_shader_parameter(&"boost", _boost)
		flame.set_instance_shader_parameter(&"kick", _kick)
	_sparks.emitting = boosting
	_ram = lerpf(_ram, 1.0 if ramming else 0.0, 1.0 - exp(-RAM_UP * delta))
	_ram_struck *= exp(-RAM_FLARE * delta)
	_ram_field.visible = _ram > 0.01
	_ram_field.set_instance_shader_parameter(&"strength", _ram)
	_ram_field.set_instance_shader_parameter(&"struck", _ram_struck)
	if absf(thrust - _lit_thrust) > 0.015:
		_lit_thrust = thrust
		for mat: BaseMaterial3D in _drive_emissions:
			mat.emission_energy_multiplier = _drive_emissions[mat] * lerpf(0.10, 1.0, thrust)
	_engine.pitch_scale = 0.65 + speed / 320.0
	_engine.volume_db = _engine_volume + linear_to_db(maxf(thrust, 0.001))


## A rock broke on the ram plating.
func ram_struck() -> void:
	_ram_struck = 1.0


## Blown up: out of sight and silent until [method reset].
func destroy() -> void:
	hide()
	_engine.stop()


func reset() -> void:
	lower_gear(0.0)
	rotation = Vector3.ZERO
	lean = Vector2.ZERO
	thrust = 1.0
	boosting = false
	ramming = false
	_boost = 0.0
	_kick = 1.0
	_ram = 0.0
	_ram_struck = 0.0
	show()
	if not _engine.playing:
		_engine.play()
