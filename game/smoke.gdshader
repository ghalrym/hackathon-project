shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_disabled;

// A puff of rock dust on a quad that faces the camera: thick in the middle,
// ragged at the rim. Enough of them stacked up hide what is behind.
uniform sampler2D noise : repeat_enable, filter_linear_mipmap;
uniform sampler2D depth_texture : hint_depth_texture, repeat_disable, filter_nearest;

varying vec2 grain; // which patch of the noise this puff wears
varying float age; // 0..1 through its life

void vertex() {
	float roll = INSTANCE_CUSTOM.x;
	grain = vec2(INSTANCE_CUSTOM.y, INSTANCE_CUSTOM.y * 1.7);
	age = INSTANCE_CUSTOM.z;
	// Face the camera, turned about the line of sight by the puff's own roll.
	float size = length(MODEL_MATRIX[0].xyz);
	vec2 corner = mat2(vec2(cos(roll), sin(roll)), vec2(-sin(roll), cos(roll))) * VERTEX.xy;
	MODELVIEW_MATRIX = VIEW_MATRIX * mat4(
			MAIN_CAM_INV_VIEW_MATRIX[0], MAIN_CAM_INV_VIEW_MATRIX[1],
			MAIN_CAM_INV_VIEW_MATRIX[2], MODEL_MATRIX[3]);
	VERTEX = vec3(corner * size, 0.0);
}

void fragment() {
	// The same noise twice: one scale eats into the rim, the other mottles
	// the body. Both creep as the puff ages, so it churns.
	float churn = texture(noise, UV * 0.4 + grain + age * 0.15).r;
	float mottle = texture(noise, UV * 0.9 - grain + age * 0.1).r;
	float rim = length(UV * 2.0 - 1.0);
	float body = smoothstep(1.0, 0.15, rim + (churn - 0.5) * 0.9) * smoothstep(1.0, 0.75, rim);

	// Thin out against whatever the puff cuts through, and against the lens.
	float scene = texture(depth_texture, SCREEN_UV).r;
	vec4 behind = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, scene, 1.0);
	float soft = clamp((VERTEX.z - behind.z / behind.w) / 1.5, 0.0, 1.0);
	float close = clamp((-VERTEX.z - 0.4) / 3.0, 0.0, 1.0);

	ALBEDO = COLOR.rgb * mix(0.55, 1.2, mottle);
	ALPHA = COLOR.a * body * soft * close;
}
