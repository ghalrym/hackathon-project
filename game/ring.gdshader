shader_type spatial;
render_mode fog_disabled;

uniform vec3 color : source_color = vec3(1.0, 0.77, 0.30);

void fragment() {
	// Ceramic induction modules sit in a segmented metal housing. Continuous
	// guide strips along the front and back remain legible on a distant gate.
	float sector = fract(UV.x * 32.0);
	float gasket = 1.0 - smoothstep(0.025, 0.065, min(sector, 1.0-sector));
	float band = abs(sin((UV.y - 0.25) * TAU));
	float lens = (1.0 - smoothstep(0.63, 0.83, band)) * (1.0 - gasket);
	float ribs = smoothstep(0.79,0.94,cos(UV.x * TAU * 192.0));
	ALBEDO = mix(vec3(0.22,0.24,0.25),vec3(0.037,0.04,0.045),gasket + (1.0-gasket)*ribs*0.32);
	ALBEDO = mix(ALBEDO, color*0.55, lens);
	METALLIC = mix(0.78, 0.08, lens);
	ROUGHNESS = mix(0.37, 0.23, lens) + gasket*0.25;
	float pulse = 0.5 + 0.5*cos(UV.x*TAU*4.0 - TIME*3.4);
	EMISSION = color * lens * (2.2 + 2.5*pulse*pulse);
}
