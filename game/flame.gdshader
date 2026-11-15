shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_back, fog_disabled;
// An engine's exhaust, drawn as a glowing volume inside a box: each pixel adds
// up the plume along its line of sight, so it is soft-edged from any angle.
// The box runs a unit down local y from the nozzle and spans the plume across.

const int STEPS = 22;

uniform vec3 hot : source_color = vec3(0.52, 0.82, 1.0);
uniform vec3 surge : source_color = vec3(0.66, 0.42, 1.0);  // Fringe of an afterburner.
instance uniform float boost = 0.0;  // Afterburner, 0..1.
instance uniform float kick = 1.0;  // An ignition pulse's way down the plume; 1 is none.
instance uniform float seed = 0.0;  // Sets one engine's flicker apart from another's.

varying vec3 local;
varying vec3 eye;
varying flat float radius;

void vertex() {
	VERTEX.y += 0.5;
	radius = abs(VERTEX.x);
	local = VERTEX;
	eye = (inverse(MODEL_MATRIX) * vec4(CAMERA_POSITION_WORLD, 1.0)).xyz;
}

float hash(vec3 p) {
	p = fract(p * 0.3183099 + 0.1) * 17.0;
	return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float noise(vec3 x) {
	vec3 i = floor(x);
	vec3 f = fract(x);
	f = f * f * (3.0 - 2.0 * f);
	return mix(
		mix(mix(hash(i), hash(i + vec3(1, 0, 0)), f.x),
			mix(hash(i + vec3(0, 1, 0)), hash(i + vec3(1, 1, 0)), f.x), f.y),
		mix(mix(hash(i + vec3(0, 0, 1)), hash(i + vec3(1, 0, 1)), f.x),
			mix(hash(i + vec3(0, 1, 1)), hash(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}

// Light given off at a point in the box: y down the plume, q across it.
vec3 glow(float y, vec2 q) {
	float r2 = dot(q, q);
	float flow = TIME * mix(5.0, 10.0, boost) + seed;
	float billow = noise(vec3(q * 2.0 + seed, y * 4.0 - flow));
	float strands = noise(vec3(q * 5.0 - seed, y * 10.0 - flow * 2.3));
	float rough = smoothstep(0.0, 0.45, y);  // Smooth at the nozzle, ragged downstream.
	float taper = pow(max(1.0 - y, 0.0), 0.75);

	// The plume leaves the nozzle, swells a little and tapers to a point.
	float width = mix(0.36, 0.54, smoothstep(0.0, 0.2, y)) * taper;
	width *= 1.0 + (billow - 0.5) * 0.9 * rough;
	width = max(width, 0.003);
	float plume = exp(-2.2 * r2 / (width * width)) * taper * mix(1.0, 0.35 + 1.3 * strands, rough);

	// A white-hot core, pinched into shock diamonds that fade down its length.
	float reach = mix(0.5, 0.74, boost);
	float left = max(1.0 - y / reach, 0.0);
	float diamond = 0.5 + 0.5 * cos(TAU * 4.0 * y / reach);
	float waist = width * mix(0.26, 0.44, diamond);
	float core = exp(-r2 / (waist * waist)) * left * left;
	core *= mix(0.45, 1.0 + 0.8 * boost, pow(diamond, 3.0));

	// Ignition: a bright ring that runs down the plume and spreads as it goes.
	float ring = exp(-pow((y - kick) / 0.045, 2.0)) * exp(-r2 / (width * width * 1.1));
	ring *= 1.0 - kick;

	vec3 white = mix(hot, vec3(1.0, 0.97, 0.92), 0.82);
	vec3 outer = mix(hot, hot * hot, smoothstep(0.0, 0.8, y));
	outer = mix(outer, surge, boost * smoothstep(0.15, 1.1, r2 / (width * width)));
	vec3 light = outer * plume * (1.5 + 0.9 * boost) + white * core * (3.4 + 1.2 * boost) + white * ring * 1.8;
	return light * smoothstep(1.0, 0.7, r2);  // Nothing reaches the sides of the box.
}

void fragment() {
	// From where the line of sight enters the box to where it leaves.
	vec3 ray = normalize(local - eye);
	vec3 ahead = step(0.0, ray);
	vec3 wall = mix(vec3(-radius, 0.0, -radius), vec3(radius, 1.0, radius), ahead);
	vec3 far = (wall - local) / (ray + (ahead * 2.0 - 1.0) * 1e-6);
	float span = max(min(min(far.x, far.y), far.z), 0.0) / float(STEPS);
	float jitter = fract(52.9829189 * fract(dot(FRAGCOORD.xy, vec2(0.06711056, 0.00583715))));
	vec3 sum = vec3(0.0);
	for (int i = 0; i < STEPS; i++) {
		vec3 at = local + ray * span * (float(i) + jitter);
		sum += glow(at.y, at.xz / radius);
	}
	float flicker = 0.9 + 0.2 * noise(vec3(TIME * 11.0, seed, 0.0));
	ALBEDO = min(sum * span / radius * flicker, vec3(8.0));
}
