class_name Smoke
extends MultiMeshInstance3D
## Dust clouds left where rocks are shot apart: puffs that billow out, hang in
## the lane and come back past the ship with everything else.

const LIFE := Vector2(4.5, 6.5)  ## Seconds a puff lasts.
const DRAG := 1.8  ## How quickly the billowing slows (1/s).
const OPACITY := 0.8  ## Of one puff at its thickest; a cloud stacks many.
const BEHIND_Z := 16.0  ## Puffs this far behind the ship are out of sight.
const DUST := Color(0.17, 0.155, 0.14)
const FLASH := Color(3.0, 1.7, 0.8)  ## The moment of the hit, before the dust.


class Puff:
	var at := Vector3.ZERO
	var drift := Vector3.ZERO
	var size := 1.0  ## Radius it billows out to.
	var age := 0.0
	var life := 1.0
	var roll := 0.0  ## Turn about the line of sight,
	var spin := 0.0  ## and how fast that changes.
	var shade := 1.0
	var grain := 0.0  ## Which patch of the noise it wears.


var _puffs: Array[Puff] = []


## Throw up a cloud for a rock of [param radius] shot apart at [param at].
func burst(at: Vector3, radius: float) -> void:
	var across := 4.6 * pow(radius, 0.6)  # the cloud's radius once it has spread
	var room := multimesh.instance_count - _puffs.size()
	for i in mini(clampi(roundi(3 + 12 * radius), 4, 40), room):
		var puff := Puff.new()
		var out := Vector3(randfn(0, 1), randfn(0, 1), randfn(0, 1)).normalized()
		puff.at = at + out * radius * randf()
		# Slowed by drag, a puff ends up drift / DRAG from where it began.
		puff.drift = out * across * 0.5 * DRAG * randf()
		puff.size = across * randf_range(0.45, 0.7)
		puff.life = randf_range(LIFE.x, LIFE.y)
		puff.roll = randf() * TAU
		puff.spin = randf_range(-0.25, 0.25)
		puff.shade = randf_range(0.75, 1.1)
		puff.grain = randf()
		_puffs.append(puff)


## Billow the clouds and carry them toward the ship with the rest of the world.
func advance(delta: float, speed: float) -> void:
	var slow := exp(-DRAG * delta)
	for i in range(_puffs.size() - 1, -1, -1):
		var puff := _puffs[i]
		puff.age += delta
		puff.at += puff.drift * delta + Vector3(0, 0, speed * delta)
		puff.drift *= slow
		if puff.age >= puff.life or puff.at.z > BEHIND_Z:
			_puffs[i] = _puffs[-1]
			_puffs.pop_back()

	for i in _puffs.size():
		var puff := _puffs[i]
		var t := puff.age / puff.life
		var size := puff.size * (0.35 + 0.65 * (1.0 - exp(-2.5 * puff.age)) + 0.15 * t)
		var color := (DUST * puff.shade).lerp(FLASH, exp(-8.0 * puff.age))
		color.a = OPACITY * smoothstep(0.0, 0.04, puff.age) * (1.0 - smoothstep(0.55, 1.0, t))
		multimesh.set_instance_transform(i, Transform3D(Basis.from_scale(Vector3.ONE * size), puff.at))
		multimesh.set_instance_color(i, color)
		multimesh.set_instance_custom_data(i, Color(puff.roll + puff.spin * puff.age, puff.grain, t, 0.0))
	multimesh.visible_instance_count = _puffs.size()


func clear() -> void:
	_puffs.clear()
	multimesh.visible_instance_count = 0
