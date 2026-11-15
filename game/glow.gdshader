shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, fog_disabled;

// The light at the end of the warp tunnel: a soft halo with a hot core.
uniform vec3 tint : source_color = vec3(0.25, 0.43, 1.0);

void fragment() {
	float d = 1.0 - min(length(UV - 0.5) * 2.0, 1.0);
	ALBEDO = tint * 0.3 * pow(d, 3.0) + vec3(0.75, 0.9, 1.0) * pow(d, 14.0);
}
