class_name Debrief
extends Control
## The crash screen: how the run went, and the way back into the next one.

signal retry_requested
signal change_ship_requested

const FADE_TIME := 0.45
const RISE := 18.0  ## The card drifts up this far as it fades in.

@onready var _card: VBoxContainer = %Card
@onready var _retry: Button = %Retry
@onready var volume_slot: HBoxContainer = %VolumeSlot

var _tween: Tween


func _ready() -> void:
	_retry.pressed.connect(retry_requested.emit)
	%ChangeShip.pressed.connect(change_ship_requested.emit)
	resized.connect(_layout)
	_card.minimum_size_changed.connect(_layout)
	volume_slot.minimum_size_changed.connect(_layout)
	_layout()


## Fill in the run's numbers while the screen is still hidden.
## [param upgrades] names what was fitted at stations, or is empty.
func load_run(score: String, best: String, record: bool, seconds: float, stations: int,
		raiders: int, upgrades: String, hull_name: StringName) -> void:
	%Score.text = score
	%NewBest.visible = record
	%Best.visible = not record
	%Best.text = "Best %s" % best
	%TimeValue.text = "%d:%02d" % [int(seconds) / 60, int(seconds) % 60]
	%StationsValue.text = str(stations)
	%RaidersValue.text = str(raiders)
	%Upgrades.text = "UPGRADES  %s" % ("NONE" if upgrades.is_empty() else upgrades.to_upper())
	%ShipValue.text = String(hull_name).to_upper()


func reveal() -> void:
	show()
	_layout()
	var rest := _card.position
	_card.position.y += RISE
	modulate.a = 0.0
	if _tween:
		_tween.kill()
	_tween = create_tween().set_parallel().set_ease(Tween.EASE_OUT).set_trans(Tween.TRANS_CUBIC)
	_tween.tween_property(self, "modulate:a", 1.0, FADE_TIME)
	_tween.tween_property(_card, "position:y", rest.y, FADE_TIME)
	_retry.grab_focus()


func _layout() -> void:
	var zoom := 1.0
	if size.y > size.x * 1.15:
		# Small portrait windows enlarge the card relative to the game's 1280px canvas.
		var stretch := get_viewport().get_stretch_transform().get_scale().x
		zoom = clampf(1.0 / stretch, 1.0, size.x * 0.9 / _card.get_combined_minimum_size().x)
	_card.scale = Vector2.ONE * zoom
	_card.size = _card.get_combined_minimum_size()
	_card.position = (size - _card.size * zoom) * Vector2(0.5, 0.46)
	volume_slot.scale = Vector2.ONE * zoom
	volume_slot.size = volume_slot.get_combined_minimum_size()
	volume_slot.position = Vector2((size.x - volume_slot.size.x * zoom) * 0.5,
			size.y - (volume_slot.size.y + 24.0) * zoom)
