class_name ShipSelect
extends Control
## The launch menu shows the same airframe that the player will fly.

signal hull_selected(hull_name: StringName)
signal launch_requested

const BAR := 74.0  ## Height of the letterbox bars the menu sits between.
const MARGIN := 0.055  ## Side margin, as a fraction of the width.
## What the controls panel says with a mouse and keyboard, and with a gamepad.
const BINDINGS := {
	&"SteerKey": ["MOUSE", "LEFT STICK"],
	&"BoostKey": ["LMB / SPACE", "A / RT"],
	&"TurnKey": ["BOOST + FLICK", "BOOST + RIGHT STICK"],
	&"ShootKey": ["RMB / F", "X / RB"],
	&"PauseKey": ["ESC", "START"],
}

@onready var _choices: HBoxContainer = %Choices
@onready var _selector: VBoxContainer = %Selector
@onready var _index: Label = %Index
@onready var _ship_name: Label = %Name
@onready var _spec: Label = %Spec
@onready var _launch: Button = %Launch
@onready var _best: Control = %Best
@onready var _best_value: Label = %Value
@onready var _controls: VBoxContainer = $Controls
@onready var _status: HBoxContainer = $Status
@onready var preview_area: Control = %PreviewArea


func _ready() -> void:
	for button: Button in _choices.get_children():
		button.pressed.connect(_select.bind(button))
	%Prev.pressed.connect(_step.bind(-1))
	%Next.pressed.connect(_step.bind(1))
	_launch.pressed.connect(launch_requested.emit)
	Input.joy_connection_changed.connect(_show_bindings.unbind(2))
	_show_bindings()
	resized.connect(_layout)
	visibility_changed.connect(_layout)
	for node: Control in [_selector, _controls, _status, $Wordmark, _launch]:
		node.minimum_size_changed.connect(_layout)
	_layout()


## An empty best score hides it.
func open(hull_name: StringName, best_score: String) -> void:
	show()
	_best.visible = not best_score.is_empty()
	_best_value.text = best_score
	var button: Button = _choices.get_child(0)
	for choice: Button in _choices.get_children():
		if choice.name == hull_name:
			button = choice
			break
	button.button_pressed = true
	_select(button)
	_launch.grab_focus()


## The controls panel names the gamepad's buttons while one is plugged in.
func _show_bindings() -> void:
	var pad := 0 if Input.get_connected_joypads().is_empty() else 1
	for key: StringName in BINDINGS:
		(_controls.get_node("Keys").get_node(NodePath(key)) as Label).text = BINDINGS[key][pad]


## Arrow keys and A/D page through the hulls; the launch button keeps focus.
func _input(event: InputEvent) -> void:
	if not is_visible_in_tree() or event.is_echo():
		return
	var key := event as InputEventKey
	if event.is_action_pressed("ui_left") or (key and key.pressed and key.physical_keycode == KEY_A):
		_step(-1)
	elif event.is_action_pressed("ui_right") or (key and key.pressed and key.physical_keycode == KEY_D):
		_step(1)
	else:
		return
	get_viewport().set_input_as_handled()


func _step(by: int) -> void:
	var current := _choices.get_child(0) as Button
	for choice: Button in _choices.get_children():
		if choice.button_pressed:
			current = choice
	var count := _choices.get_child_count()
	var button: Button = _choices.get_child(posmod(current.get_index() + by, count))
	button.button_pressed = true
	_select(button)


func _select(button: Button) -> void:
	_index.text = "%02d / %02d" % [button.get_index() + 1, _choices.get_child_count()]
	_ship_name.text = String(button.name).to_upper()
	_spec.text = button.accessibility_description
	hull_selected.emit(button.name)


func _layout() -> void:
	var tall := size.y > size.x * 1.15
	var zoom := 1.0
	if tall:
		# Small portrait windows enlarge these controls relative to the game's 1280px canvas.
		var stretch := get_viewport().get_stretch_transform().get_scale().x
		var widest := maxf(_selector.get_combined_minimum_size().x, _controls.get_combined_minimum_size().x)
		zoom = clampf(1.0 / stretch, 1.0, size.x * 0.85 / widest)
	var density := get_viewport().get_stretch_transform().get_scale().x * zoom
	get_viewport().oversampling_override = maxf(1.0, density) if tall and is_visible_in_tree() else 0.0

	var margin := size.x * MARGIN
	_place($Wordmark, Vector2(margin, BAR * 0.5), Vector2(0.0, 0.5), 1.0)
	_place(_status, Vector2(size.x - margin, BAR * 0.5), Vector2(1.0, 0.5), 1.0)
	$SideShade.visible = not tall

	if tall:
		preview_area.anchor_left = MARGIN
		preview_area.anchor_right = 1.0 - MARGIN
		preview_area.anchor_top = (BAR + 16.0) / size.y
		preview_area.anchor_bottom = 0.42
		var below := size.y * 0.43
		var selector := _place(_selector, Vector2(size.x * 0.5, below), Vector2(0.5, 0.0), zoom)
		_place(_controls, Vector2(size.x * 0.5, selector.end.y + 48.0 * zoom), Vector2(0.5, 0.0), zoom)
		_place(_launch, Vector2(size.x * 0.5, size.y - BAR - 32.0 * zoom), Vector2(0.5, 1.0), zoom)
	else:
		preview_area.anchor_left = 0.3
		preview_area.anchor_right = 1.0 - MARGIN * 0.9
		preview_area.anchor_top = 0.09
		preview_area.anchor_bottom = 0.68
		var hero_x := size.x * (preview_area.anchor_left + preview_area.anchor_right) * 0.5
		_place(_selector, Vector2(hero_x, size.y * 0.64), Vector2(0.5, 0.0), 1.0)
		_place(_controls, Vector2(margin, size.y * 0.5), Vector2(0.0, 0.5), 1.0)
		_place(_launch, Vector2(hero_x, size.y - BAR * 0.5), Vector2(0.5, 0.5), 1.0)


## Sizes a control to its contents and puts its pivot point at the spot.
## Returns where it ended up.
func _place(node: Control, spot: Vector2, pivot: Vector2, zoom: float) -> Rect2:
	node.scale = Vector2.ONE * zoom
	node.size = node.get_combined_minimum_size()
	node.position = spot - node.size * zoom * pivot
	return Rect2(node.position, node.size * zoom)
