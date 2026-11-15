class_name Ring
extends MeshInstance3D
## The recharge ring: every so often one comes down the lane, and flying
## through it refills the battery.

const SPAWN_Z := -430.0
const BEHIND_Z := 20.0
const REACH := Vector2(7.0, 3.5)  ## How far off the centre line it can appear.
const WAIT := Vector2(12.0, 20.0)  ## Seconds between rings, shortest and longest.

## One has set off down the lane.
signal appeared

var _due := 0.0
var _prev_z := 0.0

@onready var _hole: float = (mesh as TorusMesh).inner_radius


func _ready() -> void:
	reset()


## Move the ring toward the camera. While [param sending], the next one sets
## off once the wait is up.
func advance(delta: float, speed: float, sending: bool) -> void:
	if visible:
		_prev_z = position.z
		position.z += speed * delta
		if position.z > BEHIND_Z:
			reset()
	elif sending:
		_due -= delta
		if _due <= 0.0:
			position = Vector3(randf_range(-REACH.x, REACH.x), randf_range(-REACH.y, REACH.y), SPAWN_Z)
			_prev_z = SPAWN_Z
			show()
			appeared.emit()


## Did a ship at [param centre] pass through the ring this frame?
func threaded(centre: Vector3) -> bool:
	if not visible or _prev_z >= centre.z or position.z < centre.z:
		return false
	return Vector2(position.x - centre.x, position.y - centre.y).length() < _hole


## Take the ring away and start the wait for the next one.
func reset() -> void:
	hide()
	_due = randf_range(WAIT.x, WAIT.y)
