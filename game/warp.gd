class_name Warp
extends Node3D
## The warp tunnel: stars and dust streaking past, a static sky, and a glow
## dead ahead.

const COUNT := 1800
const NEAR := 30.0
const FAR := -560.0
const TINTS: Array[Color] = [
	Color("ffffff"), Color("bfe3ff"), Color("8fc7ff"), Color("d9c8ff"),
]

## How thick the dust is, 0..1.
var fog := 1.0:
	set(value):
		fog = value
		_fog.set_shader_parameter("amount", value)

var _travel := 0.0

@onready var _streaks: ShaderMaterial = $Streaks.material_override
@onready var _fog: ShaderMaterial = $Fog.material


func _ready() -> void:
	$Streaks.mesh = _streak_mesh()
	$Sky.mesh = _sky_mesh()
	_streaks.set_shader_parameter("near", NEAR)
	_streaks.set_shader_parameter("far", FAR)
	_fog.set_shader_parameter("length", NEAR - FAR)


func advance(delta: float, speed: float) -> void:
	_travel = fposmod(_travel + speed * delta, NEAR - FAR)
	_streaks.set_shader_parameter("travel", _travel)
	_streaks.set_shader_parameter("streak", speed * 0.08)
	_fog.set_shader_parameter("travel", _travel)


## One line per star. The shader slides them down the tunnel and stretches the
## tails, so nothing here needs updating per frame.
func _streak_mesh() -> ArrayMesh:
	var vertices := PackedVector3Array()
	var colors := PackedColorArray()
	var uvs := PackedVector2Array()
	for i in COUNT:
		var radius := 5.0 + 150.0 * pow(randf(), 1.6)
		var across := Vector2.from_angle(randf() * TAU) * radius
		var star := Vector3(across.x, across.y, randf() * (NEAR - FAR))
		var tint := (TINTS[i % TINTS.size()] * randf_range(0.35, 1.0)).srgb_to_linear()
		for end in 2:  # head, then tail
			vertices.append(star)
			colors.append(tint)
			uvs.append(Vector2(end, 0))

	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_COLOR] = colors
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_LINES, arrays)
	# The shader moves the stars, so say where they actually end up.
	mesh.custom_aabb = AABB(Vector3(-160, -160, FAR - 40), Vector3(320, 320, NEAR - FAR + 40))
	return mesh


func _sky_mesh() -> ArrayMesh:
	var vertices := PackedVector3Array()
	for i in 900:
		vertices.append(Vector3(randfn(0, 1), randfn(0, 1), randfn(0, 1)).normalized() * 1200.0)
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_POINTS, arrays)
	return mesh
