shader_type spatial;

// The player's hull in the other side's colours: the white panels go dark,
// the red trim goes amber and the cyan lights burn orange. It flashes white
// where a bolt hits.
uniform sampler2D paint : source_color, filter_linear_mipmap, repeat_disable;
uniform sampler2D lights : source_color, filter_linear_mipmap, repeat_disable;
uniform sampler2D relief : hint_normal, filter_linear_mipmap, repeat_disable;
uniform sampler2D coating : filter_linear_mipmap, repeat_disable;
uniform vec3 hull : source_color = vec3(0.22, 0.22, 0.25);
uniform vec3 trim : source_color = vec3(1.0, 0.5, 0.1);
uniform vec3 glow : source_color = vec3(1.0, 0.36, 0.08);
uniform float glow_energy = 3.0;
instance uniform float flash = 0.0;

void fragment() {
	vec3 c = texture(paint, UV).rgb;
	float shade = dot(c, vec3(0.3, 0.59, 0.11));
	float red = smoothstep(0.1, 0.35, c.r - max(c.g, c.b));
	float glass = smoothstep(0.05, 0.2, c.b - c.r);
	vec3 base = mix(hull * (0.35 + 1.3 * shade), trim * (0.4 + 0.7 * c.r), red);
	ALBEDO = mix(base, c, glass);
	vec2 finish = texture(coating, UV).gb;
	METALLIC = finish.y;
	ROUGHNESS = finish.x;
	NORMAL_MAP = texture(relief, UV).rgb;
	vec3 e = texture(lights, UV).rgb;
	EMISSION = glow * max(e.r, max(e.g, e.b)) * glow_energy + vec3(4.0 * flash);
	if (UV.x > 2.0) {
		// A wreck exposes the honeycomb between the two metal skins.
		vec2 cell = UV * vec2(160.0, 120.0);
		cell.x += 0.5 * mod(floor(cell.y),2.0);
		vec2 edge = abs(fract(cell)-0.5);
		float web = smoothstep(0.30,0.48,max(edge.x,edge.y));
		ALBEDO = mix(vec3(0.05,0.045,0.04),vec3(0.40,0.36,0.30),web);
		METALLIC = 0.78;
		ROUGHNESS = 0.67;
		NORMAL_MAP = vec3(0.5,0.5,1.0);
		EMISSION = vec3(0.0);
	}
}
