shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, fog_disabled;
// Ram plating at work: a field about the ship's nose, brightest at its rim,
// with streaks running back along it.

uniform vec3 color : source_color = vec3(1.0, 0.72, 0.3);
instance uniform float strength = 0.0;  // 0..1 as the field comes up.
instance uniform float struck = 0.0;  // Flares to 1 when a rock breaks on it.

varying vec3 at;

void vertex() {
	at = normalize(VERTEX);
}

void fragment() {
	float rim = pow(1.0 - abs(dot(normalize(NORMAL), normalize(VIEW))), 3.0);
	float fore = smoothstep(-0.25, 0.7, -at.z);  // Only the bow, fading out aft.
	float around = atan(at.y, at.x);
	float streaks = 0.55 + 0.45 * sin(around * 9.0 + sin(at.z * 6.0) * 2.0) * sin(at.z * 16.0 + TIME * 26.0);
	ALBEDO = color * fore * strength * ((rim * 1.6 + 0.02) * streaks + struck * (0.06 + rim));
}
