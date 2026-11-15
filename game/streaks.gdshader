shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, fog_disabled;

// Each star is a line whose two ends start at the same point; UV.x marks the
// tail. VERTEX.z is the star's offset along the tunnel.
uniform float travel = 0.0; // distance flown, wrapped to the tunnel length
uniform float streak = 4.0; // tail length
uniform float near = 30.0;
uniform float far = -560.0;

void vertex() {
	float z = far + mod(VERTEX.z + travel, near - far);
	VERTEX.z = z - UV.x * streak;
	COLOR.rgb *= 1.0 - UV.x;
}

void fragment() {
	ALBEDO = COLOR.rgb * 2.0;
}
