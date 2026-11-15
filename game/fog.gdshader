shader_type fog;

// Banks of dust sliding past with the tunnel: a tiling noise field, thin
// between the banks and thick inside them. Fills the whole world.
uniform sampler3D noise : repeat_enable, filter_linear;
uniform float travel = 0.0; // distance flown, wrapped to the tunnel length
uniform float length = 590.0; // tunnel length, one noise tile along the flight path
uniform float width = 200.0; // one noise tile across it
uniform float thin = 0.00018;
uniform float thick = 0.0036;
uniform float amount = 1.0; // thins the lot, for cutscenes
uniform vec3 tint : source_color = vec3(0.39, 0.47, 0.61);

void fog() {
	vec3 at = WORLD_POSITION;
	at.z -= travel;
	float bank = texture(noise, at / vec3(width, width, length)).r;
	DENSITY = mix(thin, thick, smoothstep(0.4, 0.75, bank)) * amount;
	ALBEDO = tint;
}
