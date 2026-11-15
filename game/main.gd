extends Node3D
## Delta Warp: fly the ship down an endless asteroid field for as long as you can.

enum State { READY, PLAYING, PAUSED, DEAD, DOCKING, DOCKED, LEAVING }

const FIELD := Vector2(10.0, 5.5)  ## How far the ship can stray from the centre line.
const STEER := 0.025  ## Ship travel per pixel of mouse movement.
const IDLE_SPEED := 45.0
const BASE_SPEED := 110.0
const TOP_SPEED := 240.0
const POINTS_PER_SECOND := 100.0
const BOOST_SPEED := 130.0  ## Extra speed while boosting.
const BOOST_SCORE := 3.0  ## Points come this much faster while boosting.
const BOOST_DRAIN := 0.2  ## Share of the battery a second of boost burns.
const BOOST_RUMBLE := 0.08
const RAM_JOLT := 0.3  ## Shake from breaking a rock on the ram plating.
const GRAZE_BONUS := 150.0  ## Points for a near miss, times the boost's share while boosting.
const WARN_EVERY := 0.45  ## Seconds between warning tones while boosting on a low battery.
const DENSER := 0.15  ## Each station passed thickens the field by this share,
const HARRIED := 0.25  ## and brings raiders this much more often.
const STICK := 2.4  ## How fast a gamepad's stick carries the ship across the field (1/s).
const SNAP := 0.8  ## How far over the other stick has to go for a hard turn,
const SNAP_RESET := 0.4  ## and how far back before it can call for the next.
const IMPACT_SLOW := 0.12  ## A crash plays out this slowly at first,
const IMPACT_TIME := 0.8  ## and time takes this long, in real seconds, to pick back up.
const FLICK := 300.0  ## Pixels of mouse travel within FLICK_WINDOW that make a flick.
const FLICK_WINDOW := 0.08
const TURN_TIME := 0.3  ## A hard turn, start to finish.
const TURN_ANGLE := PI / 2.0  ## How far the view turns in all.
const STATION_EVERY := 10000.0  ## Points between stations.
const LIFT_TIME := 0.7  ## Seconds to rise from the pad before accelerating down the bay.
const IGNITION_TIME := 0.45  ## Time to open the throttle after liftoff.
const CINEMA_TIME := 1.5  ## Fade into and out of the cutscene look.
const BARS := 74.0  ## Height of the letterbox bars in a cutscene.
const GLOW := 0.8
const RESTART_DELAY := 0.9  ## Seconds after a crash before a click restarts.
const SAVE_PATH := "user://best.cfg"

var _state := State.READY
var _paused_from := State.PLAYING
var _elapsed := 0.0  ## Seconds survived this run.
var _score := 0.0
var _power := 1.0  ## Battery charge, 0..1. Only rings refill it.
var _boost_held := false
var _boosting := false
var _flick := Vector2.ZERO  ## Recent mouse travel, fading out over FLICK_WINDOW.
var _turn := Vector2.ZERO  ## Which way the hard turn in progress goes, else zero.
var _turn_time := 0.0  ## Seconds into it.
var _next_station := STATION_EVERY  ## Score at which the next station turns up.
var _stations := 0  ## Stations landed at this run.
var _boost_charge := 1.0  ## Battery size, doubled by each station's upgrade.
var _ram_plating := false  ## Fitted at a station: boosting breaks small rocks and debris.
var _downed := 0  ## Raiders shot down this run.
var _grazes := 0  ## Near misses this frame, not yet paid out.
var _warn_due := 0.0  ## Seconds until the next low-battery tone.
var _snapped := false  ## The hard-turn stick is still over from the last turn.
var _impact := IMPACT_TIME  ## Real seconds since a crash, while time is still slowed.
var _bonus_fade: Tween
var _leaving := 0.0  ## Seconds since lifting off a station's pad.
var _parked_view := Transform3D.IDENTITY  ## Starting camera pose relative to the ship.
var _parked_fov := 0.0
var _cinema := 0.0  ## 0 in flight, 1 in a cutscene: the fog clears and the flight HUD goes.
var _since_crash := 0.0
var _speed := IDLE_SPEED
var _shake := 0.0
var _best := 0.0
var _hull_name: StringName = &"Delta"
var _pointer := Vector2.ZERO  ## Where the ship is steered to, -1..1 across the field.
var _save := ConfigFile.new()  ## Best score and settings, kept between runs.

@onready var _ship: Ship = $Ship
@onready var _world: Node3D = $World
@onready var _asteroids: Asteroids = $World/Asteroids
@onready var _ring: Ring = $World/Ring
@onready var _warp: Warp = $World/Warp
@onready var _station: Station = $World/Station
@onready var _bolts: Bolts = $World/Bolts
@onready var _smoke: Smoke = $World/Smoke
@onready var _raiders: Raiders = $Raiders
@onready var _mothership: Mothership = $World/Mothership
@onready var _explosion: CPUParticles3D = $Explosion
@onready var _camera: Camera3D = $Camera
@onready var _environment: Environment = $WorldEnvironment.environment
@onready var _fog_begin := _environment.fog_depth_begin
@onready var _fog_end := _environment.fog_depth_end
@onready var _flight_hud: Array[Control] = [$HUD/Score, $HUD/Warp, $HUD/Best, $HUD/Power, $HUD/RingMarker]
@onready var _score_caption: Label = $HUD/Score/Caption
@onready var _score_value: Label = $HUD/Score/Value
@onready var _best_value: Label = $HUD/Best/Value
@onready var _warp_label: Label = $HUD/Warp
@onready var _power_caption: Label = $HUD/Power/Caption
@onready var _power_bar: PowerBar = $HUD/Power/Bar
@onready var _fitted_label: Label = $HUD/Power/Fitted
@onready var _ring_marker: RingMarker = $HUD/RingMarker
@onready var _notice: Label = $HUD/Notice
@onready var _bonus: Label = $HUD/Bonus
@onready var _bar_top: ColorRect = $HUD/BarTop
@onready var _bar_bottom: ColorRect = $HUD/BarBottom
@onready var _hangar: Control = $HUD/Hangar
@onready var _hangar_title: Label = $HUD/Hangar/Menu/Title
@onready var _hangar_detail: Label = $HUD/Hangar/Menu/Detail
@onready var _upgrade_button: Button = $HUD/Hangar/Menu/UpgradeOffer/Upgrade
@onready var _ram_button: Button = $HUD/Hangar/Menu/RamOffer/Ram
@onready var _homing_button: Button = $HUD/Hangar/Menu/HomingOffer/Homing
@onready var _leave_button: Button = $HUD/Hangar/Menu/Leave
@onready var _overlay: Control = $HUD/Overlay
@onready var _ship_select: ShipSelect = $HUD/ShipSelect
@onready var _debrief: Debrief = $HUD/Debrief
@onready var _volume_row: HBoxContainer = $HUD/Overlay/Volume
@onready var _title: Label = $HUD/Overlay/Title
@onready var _detail: Label = $HUD/Overlay/Detail
@onready var _prompt: Label = $HUD/Overlay/Prompt
@onready var _volume: HSlider = $HUD/Overlay/Volume/Slider
@onready var _launch_sound: AudioStreamPlayer = $Sounds/Launch
@onready var _explosion_sound: AudioStreamPlayer = $Sounds/Explosion
@onready var _blip: AudioStreamPlayer = $Sounds/Blip
@onready var _boost_sound: AudioStreamPlayer = $Sounds/Boost
@onready var _charge_sound: AudioStreamPlayer = $Sounds/Charge
@onready var _turn_sound: AudioStreamPlayer = $Sounds/Turn
@onready var _graze_sound: AudioStreamPlayer = $Sounds/Graze
@onready var _warning_sound: AudioStreamPlayer = $Sounds/Warning
@onready var _chime: AudioStreamPlayer = $Sounds/Chime
## Game sounds play on this bus, which is muted while paused.
@onready var _sfx_bus := AudioServer.get_bus_index(&"SFX")


func _ready() -> void:
	_save.load(SAVE_PATH)
	_best = _save.get_value("score", "best", 0.0)
	_best_value.text = _format(_best)
	_volume.value = _save.get_value("sound", "volume", 1.0)
	AudioServer.set_bus_volume_linear(0, _volume.value)
	_volume.value_changed.connect(_set_volume)
	_upgrade_button.pressed.connect(_upgrade)
	_ram_button.pressed.connect(_fit_ram)
	_homing_button.pressed.connect(_fit_homing)
	_leave_button.pressed.connect(_leave)
	_asteroids.shattered.connect(_smoke.burst)
	_asteroids.grazed.connect(func() -> void: _grazes += 1)
	_ring.appeared.connect(_chime.play)
	_ring_marker.ring = _ring
	_ring_marker.camera = _camera
	_raiders.downed.connect(_raider_downed)
	_hull_name = str(_save.get_value("ship", "hull", "Delta"))
	_ship_select.hull_selected.connect(_select_hull)
	_ship_select.launch_requested.connect(_launch)
	_debrief.retry_requested.connect(_launch)
	_debrief.change_ship_requested.connect(_open_ship_select)
	_open_ship_select()


func _open_ship_select() -> void:
	_state = State.READY
	_overlay.hide()
	_debrief.hide()
	_move_volume(_ship_select.get_node("%VolumeSlot"), Control.SIZE_SHRINK_BEGIN)
	for node in _flight_hud:
		node.hide()
	_clear_shots()
	_raiders.reset()
	_ring.reset()
	_bonus.hide()
	_end_impact()
	_station.park()
	_asteroids.hide()
	_notice.hide()
	_explosion.emitting = false
	_ship.reset()
	_ship.position = _station.global_position
	_ship.target = Vector2.ZERO
	_ship.thrust = 0.0
	_ship.lower_gear(1.0)
	_ship.advance(0.0, 0.0)
	_speed = 0.0
	_shake = 0.0
	_cinema = 1.0
	_show_cinema()
	_environment.glow_intensity = GLOW
	_warp.advance(0.0, 0.0)
	_ship_select.open(_hull_name, _format(_best) if _best > 0.0 else "")
	_hangar_preview()


func _select_hull(hull_name: StringName) -> void:
	if hull_name != _hull_name:
		_blip.play()
	_hull_name = hull_name
	_ship.select_hull(hull_name)


func _hangar_preview() -> void:
	var area := _ship_select.preview_area
	var frame := area.get_global_transform_with_canvas() * Rect2(Vector2.ZERO, area.size)
	if not frame.has_area():
		return
	_camera.fov = 54.0
	var pixel := _camera.project_position(Vector2.ZERO, 1.0).distance_to(
			_camera.project_position(Vector2.RIGHT, 1.0))
	var depth := maxf(3.65 / frame.size.x, 3.04 / frame.size.y) / pixel
	var ray := _camera.project_local_ray_normal(frame.position + frame.size * Vector2(0.46, 0.60))
	var sway := 0.07 * sin(Time.get_ticks_msec() * 0.00035)
	var arm := Vector3(0.83, 0.61, 1.0).normalized().rotated(Vector3.UP, sway)
	# Aim the menu's preview ray at the parked hull while the camera moves around it.
	_camera.position = _ship.position + arm * (depth / -ray.z)
	_camera.basis = Basis.looking_at(-arm) * Basis.looking_at(ray).inverse()


func _input(event: InputEvent) -> void:
	if event.is_action_released("boost"):
		_boost_held = false
	if event is InputEventMouseMotion:
		# The mouse is captured while flying, so steer by how far it moved.
		if _state == State.PLAYING:
			var moved := Vector2(event.screen_relative.x, -event.screen_relative.y)
			_pointer = (_pointer + moved * STEER / FIELD).clampf(-1.0, 1.0)
			_flick += moved
	elif event.is_action_pressed("ui_cancel") or event.is_action_pressed("pause"):
		if _state == State.PLAYING or _state == State.LEAVING:
			_pause()
		elif _state == State.PAUSED:
			_resume()
	elif _state == State.PLAYING:
		# Only a press made in flight boosts, not the click that launched.
		if event.is_action_pressed("boost"):
			_boost_held = true


## Menu controls consume their clicks before the pause and retry shortcuts.
func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_accept") or _is_click(event):
		match _state:
			State.PAUSED:
				_resume()
			State.DEAD:
				if _since_crash > RESTART_DELAY:
					_launch()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_WINDOW_FOCUS_OUT and _state in [State.PLAYING, State.LEAVING]:
		_pause()


func _process(frame_delta: float) -> void:
	if _impact < IMPACT_TIME:
		_impact += frame_delta / Engine.time_scale
		Engine.time_scale = lerpf(IMPACT_SLOW, 1.0, smoothstep(0.35, 1.0, _impact / IMPACT_TIME))
	if _state == State.PAUSED:
		return
	var delta := minf(frame_delta, 0.05)
	if _state == State.READY:
		_hangar_preview()
		return

	var docking := _state == State.DOCKING or _state == State.DOCKED
	var lifting := _state == State.LEAVING and _leaving < LIFT_TIME
	_cinema = move_toward(_cinema, 1.0 if docking or lifting else 0.0, delta / CINEMA_TIME)
	_show_cinema()
	if docking:
		_dock_step(delta)
		return

	var boosting := _state == State.PLAYING and _boost_held and _power > 0.0
	if boosting and not _boosting:
		_boost_sound.play()
	_boosting = boosting

	if _state == State.PLAYING:
		_steer_by_pad(delta)
	_flick *= exp(-delta / FLICK_WINDOW)
	if _turn != Vector2.ZERO:
		_advance_turn(delta)
	elif boosting and maxf(absf(_flick.x), absf(_flick.y)) > FLICK:
		_start_turn()

	var cruise := 25.0  # coasting through the wreckage
	match _state:
		State.PLAYING:
			_elapsed += delta
			cruise = _cruise_speed(_elapsed)
			if boosting:
				cruise += BOOST_SPEED
				_power = maxf(_power - BOOST_DRAIN / _boost_charge * delta, 0.0)
				_shake = maxf(_shake, BOOST_RUMBLE)
				if _power <= PowerBar.LOW_CHARGE:
					_warn_due -= delta
					if _warn_due <= 0.0:
						_warn_due = WARN_EVERY
						_warning_sound.play()
			_score += POINTS_PER_SECOND * (BOOST_SCORE if boosting else 1.0) * delta
			if _score >= _next_station and not _station.visible and not _mothership.visible:
				_station.appear()
				_asteroids.quiet = true
				_raiders.dismiss()
		State.LEAVING:
			_leaving += delta
			var lift := smoothstep(0.0, LIFT_TIME, _leaving)
			_ship.lower_gear(1.0 - smoothstep(0.18, 0.94, lift))
			_pointer = Vector2(0.0, lift * Station.HOVER / FIELD.y)
			_ship.thrust = lift
			cruise = _cruise_speed(_elapsed) * smoothstep(LIFT_TIME, LIFT_TIME + IGNITION_TIME, _leaving)
		State.DEAD:
			_since_crash += delta
			if _since_crash > RESTART_DELAY and not _debrief.visible:
				_reveal_debrief()
	_speed = lerpf(_speed, cruise, 1.0 - exp(-2.5 * delta))

	if _state != State.DEAD:
		_ship.target = _pointer * FIELD
		_ship.boosting = boosting
		_ship.ramming = boosting and _ram_plating
		_ship.advance(delta, _speed)
	var playing := _state == State.PLAYING
	_asteroids.advance(delta, _speed, _field_rate() if playing else 0.0, _ship.position)
	_warp.advance(delta, _speed)
	_ring.advance(delta, _speed, playing)
	if _station.visible and _state != State.DEAD:
		_station.advance(delta, _speed)
	# Mid-turn the field is swinging past, so nothing can be shot, hit or collected.
	var steady := playing and _turn == Vector2.ZERO
	var firing := steady and Input.is_action_pressed("shoot")
	if playing and not _station.visible:
		# Leave enough room before the next station even if the player boosts throughout.
		var room_for_pass := _next_station - _score > Mothership.DURATION * POINTS_PER_SECOND * BOOST_SCORE
		_mothership.advance(frame_delta, _speed * delta, _speed, _ship.position, _asteroids, steady, room_for_pass)
		_shake = maxf(_shake, _mothership.rumble)
	_raiders.advance(delta, _speed, _ship.position, _elapsed, playing and not _station.visible,
			steady, firing, _asteroids)
	_bolts.advance(delta, firing, _ship.position, _speed, _asteroids, _raiders)
	_smoke.advance(delta, _speed)
	if steady:
		if _ram_plating and boosting and _asteroids.ram(_ship.position, Ship.HALF) > 0:
			_shake = maxf(_shake, RAM_JOLT)
			_ship.ram_struck()
		if _station.in_range():
			_dock()
		elif _asteroids.hits(_ship.position, Ship.HALF):
			_crash()
		elif _ring.threaded(_ship.position):
			_recharge()
		elif _grazes > 0:
			_graze(boosting)
	_grazes = 0

	_follow_ship(delta)
	if _state == State.LEAVING:
		_departure_view()
		if _station.cleared_exit(_ship):
			_state = State.PLAYING
			_asteroids.quiet = false
			_asteroids.show()
	_environment.glow_intensity = lerpf(_environment.glow_intensity, GLOW, 1.0 - exp(-3.0 * delta))
	_score_caption.text = "Score x%d" % BOOST_SCORE if boosting else "Score"
	_score_value.text = _format(_score)
	_power_caption.text = "Power" if _boost_charge == 1.0 else "Power x%d" % _boost_charge
	_power_bar.charge = _power
	_power_bar.boosting = boosting
	_warp_label.text = "Warp %.1f" % (_speed / BASE_SPEED)
	_prompt.modulate.a = 0.675 + 0.325 * cos(Time.get_ticks_msec() / 1400.0 * TAU)
	_notice.visible = playing and _station.arriving
	_notice.modulate.a = _prompt.modulate.a


## World speed and lane rocks per second both ramp with time survived.
static func _cruise_speed(t: float) -> float:
	return BASE_SPEED + (TOP_SPEED - BASE_SPEED) * (1.0 - exp(-t / 75.0))


static func _rock_rate(t: float) -> float:
	return 3.0 + 8.0 * (1.0 - exp(-t / 70.0))


## Lane rocks per second right now: each station passed thickens the field.
func _field_rate() -> float:
	return _rock_rate(_elapsed) * (1.0 + DENSER * _stations)


## A gamepad's left stick carries the ship about the field; throwing the
## right one over while boosting calls for a hard turn, as a flick does.
func _steer_by_pad(delta: float) -> void:
	var stick := Input.get_vector(&"steer_left", &"steer_right", &"steer_down", &"steer_up")
	_pointer = (_pointer + stick * STICK * delta).clampf(-1.0, 1.0)
	var over := Input.get_vector(&"turn_left", &"turn_right", &"turn_down", &"turn_up")
	if over.length() < SNAP_RESET:
		_snapped = false
	elif over.length() > SNAP and not _snapped:
		_snapped = true
		_flick = over * FLICK * 2.0


static func _is_click(event: InputEvent) -> bool:
	return event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT


func _launch() -> void:
	var from_hangar := _state == State.READY
	if from_hangar:
		_ship_select.hide()
		if _save.get_value("ship", "hull", "Delta") != String(_hull_name):
			_save.set_value("ship", "hull", String(_hull_name))
			_save.save(SAVE_PATH)
	_overlay.hide()
	_debrief.hide()
	for node in _flight_hud:
		node.show()
	_elapsed = 0.0
	_score = 0.0
	_power = 1.0
	_pointer = Vector2.ZERO
	_next_station = STATION_EVERY
	_stations = 0
	_boost_charge = 1.0
	_ram_plating = false
	_bolts.homing = false
	_downed = 0
	_grazes = 0
	_warn_due = 0.0
	_raiders.pressure = 1.0
	_bonus.hide()
	_end_impact()
	_show_fitted()
	_boost_held = false
	_boosting = false
	_asteroids.clear_lane()
	_mothership.reset()
	_clear_shots()
	_raiders.reset()
	_ring.reset()
	_end_turn()
	if from_hangar:
		_leave()
	else:
		_state = State.PLAYING
		_asteroids.quiet = false
		_station.dismiss()
		_ship.reset()
		_follow_ship(0.0)
		_launch_sound.play()
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _pause() -> void:
	_paused_from = _state
	_state = State.PAUSED
	_boost_held = false
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	AudioServer.set_bus_mute(_sfx_bus, true)
	_blip.play()
	_move_volume(_overlay, Control.SIZE_SHRINK_CENTER)
	_show_overlay("Paused", Color.WHITE, "", "Click to resume")
	_overlay.show()


func _resume() -> void:
	_state = _paused_from
	_overlay.hide()
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	AudioServer.set_bus_mute(_sfx_bus, false)
	_blip.play()


## A hard turn toward the flick. The world swings through the first half of
## the turn, a fresh field is swapped in while it is moving fastest, and
## that swings through the second half into place.
func _start_turn() -> void:
	if absf(_flick.x) > absf(_flick.y):
		_turn = Vector2(signf(_flick.x), 0.0)
	else:
		_turn = Vector2(0.0, signf(_flick.y))
	_turn_time = 0.0
	_ship.lean = _turn
	_turn_sound.play()


func _advance_turn(delta: float) -> void:
	var half := TURN_TIME / 2.0
	var swap := _turn_time < half
	_turn_time += delta
	if _turn_time >= TURN_TIME:
		_end_turn()
		return
	var angle := TURN_ANGLE / 2.0
	if _turn_time < half:
		angle *= pow(_turn_time / half, 2.0)
	else:
		angle *= -pow(1.0 - (_turn_time - half) / half, 2.0)
		if swap:
			_asteroids.reroll(_field_rate() / _speed, _ship.position)
			_clear_shots()
			if _station.arriving:
				_station.appear()  # still ahead, on the new heading
			if _ring.visible:
				_ring.reset()
			_shake = 0.5
			_environment.glow_intensity = 1.8
	# Turning the ship left swings the world right, about the ship.
	var swing := Basis(Vector3.UP, angle * _turn.x) * Basis(Vector3.RIGHT, -angle * _turn.y)
	_world.transform = Transform3D(swing, _ship.position - swing * _ship.position)


func _end_turn() -> void:
	_turn = Vector2.ZERO
	_flick = Vector2.ZERO
	_ship.lean = Vector2.ZERO
	_world.transform = Transform3D.IDENTITY


## The cutscene look: the fog clears, the flight HUD fades out and the
## letterbox bars slide in.
func _show_cinema() -> void:
	var look := smoothstep(0.0, 1.0, _cinema)
	_warp.fog = 1.0 - 0.8 * look
	_environment.fog_depth_begin = lerpf(_fog_begin, 3000.0, look)
	_environment.fog_depth_end = lerpf(_fog_end, 8000.0, look)
	for node in _flight_hud:
		node.modulate.a = 1.0 - look
	_bar_top.offset_bottom = BARS * look
	_bar_bottom.offset_top = -BARS * look


## The station takes the ship from here and lands it.
func _dock() -> void:
	_state = State.DOCKING
	_boost_held = false
	_stations += 1
	_next_station += STATION_EVERY
	_raiders.pressure = 1.0 + HARRIED * _stations
	_bonus.hide()
	_asteroids.clear_lane()
	_clear_shots()
	_raiders.clear()
	_ring.reset()
	_station.begin_landing(_ship, _camera)
	_turn_sound.play()


## A frame of the landing cutscene, or of sitting in the hangar after it.
func _dock_step(delta: float) -> void:
	if _state == State.DOCKED:
		_station.idle(_camera, _ship)
	else:
		_speed = _station.land(delta, _ship, _camera)
		if _station.landed:
			_arrive()
	_asteroids.advance(delta, _speed, 0.0, _ship.position)
	_warp.advance(delta, _speed)
	_environment.glow_intensity = lerpf(_environment.glow_intensity, GLOW, 1.0 - exp(-3.0 * delta))


## Parked on the pad: open the hangar menu.
func _arrive() -> void:
	_state = State.DOCKED
	_speed = 0.0
	_hangar_title.text = "Station %d" % _stations
	_upgrade_button.text = "Double boost charge"
	_upgrade_button.disabled = false
	_ram_button.text = "Ram plating fitted" if _ram_plating else "Ram plating"
	_ram_button.disabled = _ram_plating
	_homing_button.text = "Homing bolts fitted" if _bolts.homing else "Homing bolts"
	_homing_button.disabled = _bolts.homing
	_show_hangar_detail()
	_hangar.show()
	_upgrade_button.grab_focus()
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func _show_hangar_detail() -> void:
	_hangar_detail.text = "Score %s\nBoost charge x%d\nField ahead %d%% denser" % [
			_format(_score), _boost_charge, roundi(DENSER * _stations * 100.0)]


## The station's offers, one to a visit and kept for this run. A battery that
## lasts twice as long,
func _upgrade() -> void:
	_boost_charge *= 2.0
	_upgrade_button.text = "Boost charge doubled"
	_fitted()


## plating that breaks small rocks and debris while boosting,
func _fit_ram() -> void:
	_ram_plating = true
	_ram_button.text = "Ram plating fitted"
	_fitted()


## or bolts that seek their target but take ten times as long to load.
func _fit_homing() -> void:
	_bolts.homing = true
	_homing_button.text = "Homing bolts fitted"
	_fitted()


## One offer taken: the others are withdrawn until the next station.
func _fitted() -> void:
	for button: Button in [_upgrade_button, _ram_button, _homing_button]:
		button.disabled = true
	_show_hangar_detail()
	_show_fitted()
	_leave_button.grab_focus()
	_charge_sound.play()


## What has been fitted at stations this run, by name.
func _fitted_names(with_battery: bool) -> PackedStringArray:
	var names := PackedStringArray()
	if with_battery and _boost_charge > 1.0:
		names.append("Boost x%d" % _boost_charge)
	if _ram_plating:
		names.append("Ram plating")
	if _bolts.homing:
		names.append("Homing bolts")
	return names


## The flight HUD lists the fittings above the battery, whose own caption
## already gives its size.
func _show_fitted() -> void:
	var names := _fitted_names(false)
	_fitted_label.text = " · ".join(names)
	_fitted_label.visible = not names.is_empty()


## Lift off and fly out the far end of the bay, back into the run.
func _leave() -> void:
	_state = State.LEAVING
	_leaving = 0.0
	_hangar.hide()
	_parked_view = _camera.get_camera_transform().translated(-_ship.position)
	_parked_fov = _camera.fov
	_camera.h_offset = 0.0
	_asteroids.quiet = true
	_launch_sound.play()
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


## Swing around the rising ship and settle into its normal chase view.
func _departure_view() -> void:
	var blend := smoothstep(0.0, LIFT_TIME + IGNITION_TIME, _leaving)
	if blend >= 1.0:
		return
	var chase_arm := _camera.position - _ship.position
	var parked_aim := _parked_view.origin - _parked_view.basis.z * _parked_view.origin.length()
	var chase_aim := chase_arm - _camera.basis.z * chase_arm.length()
	_camera.position = _ship.position + _parked_view.origin.slerp(chase_arm, blend)
	var up := _parked_view.basis.y.slerp(_camera.basis.y, blend)
	_camera.look_at(_ship.position + parked_aim.lerp(chase_aim, blend), up)
	_camera.fov = lerpf(_parked_fov, _camera.fov, blend)


## Bolts in flight and the smoke of rocks already shot go with the old field.
func _clear_shots() -> void:
	_bolts.clear()
	_smoke.clear()


## Shot down a raider: its bounty.
func _raider_downed(_at: Vector3) -> void:
	_score += Raiders.BOUNTY
	_downed += 1
	_show_bonus("Bounty +%s" % _format(Raiders.BOUNTY))
	_shake = maxf(_shake, 0.35)
	_environment.glow_intensity = 1.6


## A rock went by close enough to count: worth more at boost speed.
func _graze(boosting: bool) -> void:
	var points := GRAZE_BONUS * _grazes * (BOOST_SCORE if boosting else 1.0)
	_score += points
	_show_bonus("Close call +%s" % _format(points))
	_graze_sound.play()
	_environment.glow_intensity = maxf(_environment.glow_intensity, 1.3)


## Flash up [param text] under the station notice and let it fade.
func _show_bonus(text: String) -> void:
	_bonus.text = text
	_bonus.modulate.a = 1.0
	_bonus.show()
	if _bonus_fade:
		_bonus_fade.kill()
	_bonus_fade = create_tween()
	_bonus_fade.tween_interval(0.6)
	_bonus_fade.tween_property(_bonus, "modulate:a", 0.0, 0.5)


func _recharge() -> void:
	_power = 1.0
	_warn_due = 0.0
	_charge_sound.play()
	_environment.glow_intensity = 1.5


## Time runs at its own speed again, as before a crash slowed it.
func _end_impact() -> void:
	_impact = IMPACT_TIME
	Engine.time_scale = 1.0


func _crash() -> void:
	_state = State.DEAD
	_since_crash = 0.0
	_impact = 0.0
	Engine.time_scale = IMPACT_SLOW
	_asteroids.smash(_ship.position, Ship.HALF)
	_shake = 1.0
	_environment.glow_intensity = 2.0
	_explosion.position = _ship.position
	_explosion.restart()
	_explosion_sound.play()
	_ship.destroy()
	_raiders.dismiss()
	_mothership.retire()
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

	var score := _score
	var record := score > _best
	if record:
		_best = score
		_save.set_value("score", "best", _best)
		_save.save(SAVE_PATH)
		_best_value.text = _format(_best)
	_debrief.load_run(_format(score), _format(_best), record, _elapsed, _stations, _downed,
			" · ".join(_fitted_names(true)), _hull_name)


## The flight HUD gives way to the run's summary.
func _reveal_debrief() -> void:
	for node in _flight_hud:
		node.hide()
	_notice.hide()
	_move_volume(_debrief.volume_slot, Control.SIZE_SHRINK_BEGIN)
	_debrief.reveal()


## The volume slider lives on whichever menu is showing.
func _move_volume(slot: Control, alignment: Control.SizeFlags) -> void:
	if _volume_row.get_parent() != slot:
		_volume_row.reparent(slot, false)
	_volume_row.size_flags_horizontal = alignment


## Master volume, set from the slider on the title, pause and crash screens.
func _set_volume(volume: float) -> void:
	AudioServer.set_bus_volume_linear(0, volume)
	_save.set_value("sound", "volume", volume)
	_save.save(SAVE_PATH)


## Set the overlay's text; showing it is up to the caller.
func _show_overlay(title: String, color: Color, detail: String, prompt: String) -> void:
	_title.text = title
	_title.modulate = color
	_detail.text = detail
	_detail.visible = not detail.is_empty()
	_prompt.text = prompt


## Chase camera: trails the ship, widens with speed, rolls a little into turns.
func _follow_ship(delta: float) -> void:
	_shake *= exp(-4.0 * delta)
	var at := _ship.position
	var jolt := Vector2(randf() - 0.5, randf() - 0.5) * _shake
	_camera.fov = minf(58.0 + 24.0 * (_speed - IDLE_SPEED) / (TOP_SPEED - IDLE_SPEED), 90.0)
	_camera.position = Vector3(at.x * 0.55 + jolt.x, at.y * 0.55 + 3.0 + jolt.y, 7.0)
	_camera.look_at(Vector3(at.x * 0.7, at.y * 0.7 + 0.6, -40.0))
	_camera.rotate_object_local(Vector3.BACK, _ship.rotation.z * 0.15)


## Whole points with thousands separators: 12345.6 -> "12,345".
static func _format(points: float) -> String:
	var digits := str(int(points))
	var out := ""
	for i in digits.length():
		if i > 0 and (digits.length() - i) % 3 == 0:
			out += ","
		out += digits[i]
	return out
