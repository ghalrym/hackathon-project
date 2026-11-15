class_name PowerBar
extends Control
## The boost battery: a row of cells that drain from the right.

const CELLS := 10
const LOW_CHARGE := 0.2  ## At or under this the bar turns red and pulses.
const GAP := 4.0
const FULL := Color(1.0, 0.78, 0.25)
const LOW := Color(1.0, 0.26, 0.22)
const EMPTY := Color(1.0, 1.0, 1.0, 0.14)

## Charge left, 0..1.
var charge := 1.0:
	set(value):
		if value != charge:
			charge = value
			queue_redraw()
## Burning charge right now, so the cells glow hotter.
var boosting := false:
	set(value):
		if value != boosting:
			boosting = value
			queue_redraw()


func _process(_delta: float) -> void:
	if charge <= LOW_CHARGE:
		queue_redraw()  # it is pulsing


func _draw() -> void:
	var cell := Vector2((size.x - GAP * (CELLS - 1)) / CELLS, size.y)
	var color := FULL
	var empty := EMPTY
	if charge <= LOW_CHARGE:
		var pulse := 0.5 + 0.5 * sin(Time.get_ticks_msec() * 0.012)
		color = Color(LOW, lerpf(0.45, 1.0, pulse))
		if charge <= 0.0:
			empty = Color(LOW, lerpf(0.12, 0.34, pulse))
	if boosting:
		color = color.lightened(0.45)
	for i in CELLS:
		var at := Vector2(i * (cell.x + GAP), 0)
		draw_rect(Rect2(at, cell), empty)
		var fill := clampf(charge * CELLS - i, 0.0, 1.0)
		if fill > 0.0:
			draw_rect(Rect2(at, Vector2(cell.x * fill, cell.y)), color)
