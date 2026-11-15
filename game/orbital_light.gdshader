shader_type sky;

// Directional radiance for polished materials outside the bay. The dark
// background and distant stars are drawn separately by the flight scene.
void sky() {
	vec3 direction = EYEDIR;
	vec3 sun = normalize(vec3(-0.456, 0.684, 0.570));
	vec3 planet = normalize(vec3(-0.57, -0.76, -0.31));
	float disc = dot(direction, planet);
	float surface = smoothstep(0.77, 0.80, disc);
	float rim = exp(-abs(disc - 0.79) * 62.0);
	float sunlight = max(dot(direction, sun), 0.0);
	COLOR = vec3(0.026, 0.034, 0.053);
	COLOR += vec3(0.20, 0.33, 0.49) * surface + vec3(0.53, 0.69, 0.82) * rim;
	COLOR += vec3(0.52, 0.45, 0.36) * pow(sunlight, 7.0);
	COLOR += vec3(4.8, 4.2, 3.5) * pow(sunlight, 190.0);
}
