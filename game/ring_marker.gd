class_name RingMarker
extends Control
## Brackets on the HUD around a recharge ring while it is still far off in
## the dust, so it can be lined up before it arrives.

const COLOR := Color(1.0, 0.78, 0.25)
const NEAR := 60.0  ## Closer than this the ring speaks for itself,
const FADE := 90.0  ## and the brackets fade in over this much further off.
const SMALLEST := 12.0  ## Half the brackets' span, at least, in pixels.

var ring: Ring
var camera: Camera3D

var _at := Vector2.ZERO
var _half := 0.0
var _strength := 0.0


func _process(_delta: float) -> void:
	var was := _strength
	_strength = 0.0
	if ring.visible and is_visible_in_tree() and not camera.is_position_behind(ring.global_position):
		_strength = smoothstep(NEAR, NEAR + FADE, -ring.position.z) * modulate.a
		_at = camera.unproject_position(ring.global_position)
		var rim := ring.global_position + camera.global_basis.x * (ring.mesh as TorusMesh).outer_radius
		_half = maxf(camera.unproject_position(rim).x - _at.x, SMALLEST)
	if _strength > 0.0 or was > 0.0:
		queue_redraw()


func _draw() -> void:
	if _strength <= 0.0:
		return
	var pulse := 0.65 + 0.35 * sin(Time.get_ticks_msec() * 0.008)
	var color := Color(COLOR, _strength * pulse)
	var half := _half + 8.0
	var arm := half * 0.45
	for corner: Vector2 in [Vector2(-1, -1), Vector2(1, -1), Vector2(1, 1), Vector2(-1, 1)]:
		var point := _at + corner * half
		draw_line(point, point - Vector2(corner.x * arm, 0), color, 2.0)
		draw_line(point, point - Vector2(0, corner.y * arm), color, 2.0)
