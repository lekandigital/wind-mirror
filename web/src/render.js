// Draws the tunnel: the clay twin (ray-marched capsules with soft joins), the studio floor, and the tracer streaks.
import { program, texture, framebuffer, bindTextures, drawFullscreen, FULLSCREEN_VS, lookAt, viewProj } from './gl.js';
import { SAMPLE_VEL, MAX_CAPS } from './flow.js';

const SCENE_FS = `#version 300 es
precision highp float; precision highp int;
uniform vec2 res; uniform vec2 shift; uniform vec3 eye, camF, camS, camU; uniform float tanHalf;
uniform int nc; uniform vec4 capA[${MAX_CAPS}]; uniform vec4 capB[${MAX_CAPS}];
uniform float partLoad[10]; uniform vec3 bMin, bMax; uniform float unsure; uniform float time; uniform vec3 boxMin, boxMax;
uniform vec3 bgTop, bgBot, floorCol, clayCol, hotCol, warnCol;
layout(location=0) out vec4 O; layout(location=1) out vec4 OD;

float smin(float a, float b, float k) { float h = max(k - abs(a - b), 0.0) / k; return min(a, b) - h * h * k * 0.25; }
float map(vec3 p) {
  float d = 1e9;
  for (int j = 0; j < ${MAX_CAPS}; j++) {
    if (j >= nc) break;
    vec3 a = capA[j].xyz, ba = capB[j].xyz - a, pa = p - a;
    float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-9), 0.0, 1.0);
    d = smin(d, length(pa - ba * h) - capA[j].w, 0.035);
  }
  return d;
}
float partLoadAt(vec3 p) {
  float best = 1e9; float load = 0.0; float wsum = 0.0;
  for (int j = 0; j < ${MAX_CAPS}; j++) {
    if (j >= nc) break;
    vec3 a = capA[j].xyz, ba = capB[j].xyz - a, pa = p - a;
    float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-9), 0.0, 1.0);
    float d = length(pa - ba * h) - capA[j].w;
    float w = exp(-max(d, 0.0) * 40.0);
    load += w * partLoad[int(capB[j].w + 0.5)]; wsum += w;
  }
  return load / max(wsum, 1e-6);
}
vec3 normalAt(vec3 p) {
  const vec2 e = vec2(0.0025, -0.0025);
  return normalize(e.xyy * map(p + e.xyy) + e.yyx * map(p + e.yyx) + e.yxy * map(p + e.yxy) + e.xxx * map(p + e.xxx));
}
bool boxHit(vec3 ro, vec3 rd, out float t0, out float t1) {
  vec3 inv = 1.0 / rd, a = (bMin - ro) * inv, b = (bMax - ro) * inv;
  vec3 lo = min(a, b), hi = max(a, b);
  t0 = max(max(lo.x, lo.y), max(lo.z, 0.0)); t1 = min(min(hi.x, hi.y), hi.z);
  return t1 > t0;
}
float shadow(vec3 ro, vec3 rd) {
  float t0, t1; if (!boxHit(ro, rd, t0, t1)) return 1.0;
  float res_ = 1.0, t = max(t0, 0.02);
  for (int i = 0; i < 28; i++) {
    float h = map(ro + rd * t);
    res_ = min(res_, 7.0 * h / t);
    t += clamp(h, 0.02, 0.2);
    if (res_ < 0.02 || t > t1) break;
  }
  return clamp(res_, 0.0, 1.0);
}
void main() {
  vec2 uv = (gl_FragCoord.xy * 2.0 - res) / res.y - shift * vec2(res.x / res.y, 1.0);
  vec3 rd = normalize(camF + (uv.x * camS + uv.y * camU) * tanHalf);
  vec3 L = normalize(vec3(-0.45, -0.5, 0.85));
  vec3 bg = mix(bgBot, bgTop, clamp(uv.y * 0.5 + 0.55, 0.0, 1.0));
  vec3 col = bg; float dist = 1e3;
  // floor (z = 0)
  if (rd.z < -1e-4) {
    float tf = -eye.z / rd.z; vec3 p = eye + rd * tf;
    float sh = shadow(p + vec3(0.0, 0.0, 0.002), L);
    float occ = clamp(map(p) * 2.2, 0.0, 1.0);
    vec3 fc = floorCol * (0.62 + 0.38 * sh) * (0.8 + 0.2 * occ);
    // faint tunnel markings: the footprint of the live-air box and lines along the wind
    vec2 q = p.xy;
    float inBox = step(boxMin.x, q.x) * step(q.x, boxMax.x) * step(boxMin.y, q.y) * step(q.y, boxMax.y);
    float ly = abs(fract(q.y * 2.0 + 0.5) - 0.5) / fwidth(q.y * 2.0);
    fc = mix(fc, fc * 0.93, inBox * (1.0 - clamp(ly, 0.0, 1.0)) * 0.6);
    float fog = 1.0 - exp(-tf * 0.055);
    col = mix(fc, bg, clamp(fog * 1.15, 0.0, 1.0)); dist = tf;
  }
  // the twin
  float t0, t1;
  if (boxHit(eye, rd, t0, t1)) {
    float t = t0; bool hit = false;
    for (int i = 0; i < 72; i++) {
      float h = map(eye + rd * t);
      if (h < 0.0015) { hit = true; break; }
      t += h; if (t > t1) break;
    }
    if (hit && t < dist) {
      vec3 p = eye + rd * t, n = normalAt(p);
      float dif = clamp(dot(n, L) * 0.6 + 0.4, 0.0, 1.0);
      float sh = 0.55 + 0.45 * shadow(p + n * 0.01, L);
      float ao = clamp(0.5 + 0.5 * map(p + n * 0.06) / 0.06, 0.0, 1.0);
      float hemi = 0.5 + 0.5 * n.z;
      float load = clamp(partLoadAt(p), 0.0, 1.0);
      float wind = clamp(-n.x, 0.0, 1.0);                         // the windward face
      vec3 base = mix(clayCol, hotCol, load * wind * wind * 0.5);
      base = mix(base, warnCol, unsure * 0.22);
      vec3 c = base * (0.34 + 0.72 * dif * sh) * (0.72 + 0.28 * ao) * (0.86 + 0.14 * hemi);
      float fres = pow(1.0 - clamp(dot(n, -rd), 0.0, 1.0), 3.0);
      vec3 hv = normalize(L - rd);
      c += vec3(1.0, 0.97, 0.9) * (0.10 * pow(clamp(dot(n, hv), 0.0, 1.0), 24.0) * sh + 0.16 * fres);
      c = mix(c, warnCol, unsure * fres * 0.55);
      col = c; dist = t;
    }
  }
  O = vec4(col, 1.0); OD = vec4(dist, 0.0, 0.0, 1.0);
}`;

const STREAK_VS = `#version 300 es
precision highp float; precision highp int; precision highp sampler2D;
${SAMPLE_VEL}
uniform sampler2D PA, PB; uniform ivec2 psize; uniform mat4 VP; uniform vec2 res; uniform float width, U; uniform vec3 eye; uniform vec3 boxMin, boxMax; uniform vec3 camF, focus;
out float vSpeed; out float vAlpha; out float vDist; out float vAcross;
void main() {
  int id = gl_InstanceID; ivec2 pix = ivec2(id % psize.x, id / psize.x);
  vec4 a = texelFetch(PA, pix, 0), b = texelFetch(PB, pix, 0);
  bool fresh = a.w < b.w || a.w < 0.02 || b.w < 0.0;              // respawned or waiting at the rake: no streak this frame
  vec4 ca = VP * vec4(a.xyz, 1.0), cb = VP * vec4(b.xyz, 1.0);
  vec2 sa = ca.xy / ca.w, sb = cb.xy / cb.w;
  vec2 d = (sa - sb) * res * 0.5; float len = length(d);
  vec2 dir = len > 1e-3 ? d / len : vec2(1.0, 0.0), nrm = vec2(-dir.y, dir.x);
  float end = float(gl_VertexID & 1), side = float((gl_VertexID >> 1) & 1) * 2.0 - 1.0;
  vec2 pos = mix(sb, sa, end) + (nrm * side * width + dir * (end * 2.0 - 1.0) * width * 0.6) / res * 2.0;
  vec3 u = sampleVel(a.xyz).xyz;
  vSpeed = length(u) / U; vAcross = side;
  float edge = smoothstep(boxMin.x, boxMin.x + 0.5, a.x) * smoothstep(boxMax.x, boxMax.x - 0.9, a.x);
  float near = mix(0.22, 1.0, smoothstep(-0.75, -0.05, dot(a.xyz - focus, camF)));   // filaments between the camera and the body are drawn faint, so the twin stays readable
  vAlpha = fresh || ca.w <= 0.0 || cb.w <= 0.0 ? 0.0 : edge * near;
  vDist = distance(eye, a.xyz);
  gl_Position = vec4(pos, 0.0, 1.0);
}`;
const STREAK_FS = `#version 300 es
precision highp float;
uniform sampler2D sceneD; uniform vec3 colFast, colMid, colSlow; uniform float opacity;
in float vSpeed; in float vAlpha; in float vDist; in float vAcross;
out vec4 O;
void main() {
  float sd = texelFetch(sceneD, ivec2(gl_FragCoord.xy), 0).r;
  if (vDist > sd + 0.02 || vAlpha <= 0.0) discard;
  float s = clamp(vSpeed, 0.0, 1.3);
  vec3 c = s > 0.62 ? mix(colMid, colFast, smoothstep(0.62, 0.95, s)) : mix(colSlow, colMid, smoothstep(0.15, 0.62, s));
  float a = vAlpha * opacity * (1.0 - 0.55 * abs(vAcross)) * (0.55 + 0.45 * smoothstep(0.95, 0.4, s));
  O = vec4(c * a, a);
}`;
const FADE_FS = `#version 300 es
precision highp float; uniform sampler2D T; uniform float fade; out vec4 O;
void main() { O = texelFetch(T, ivec2(gl_FragCoord.xy), 0) * fade; if (O.a < 0.003) O = vec4(0.0); }`;
const COMP_FS = `#version 300 es
precision highp float; uniform sampler2D S, T; uniform vec2 res; out vec4 O;
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  vec4 s = texelFetch(S, p, 0), t = texelFetch(T, p, 0);
  vec3 c = t.rgb + s.rgb * (1.0 - t.a);
  vec2 uv = gl_FragCoord.xy / res - 0.5;
  c *= 1.0 - 0.16 * dot(uv, uv);                                   // a touch of vignette
  O = vec4(c, 1.0);
}`;

export const THEMES = {
  cream: { bgTop: [0.955, 0.93, 0.875], bgBot: [0.90, 0.865, 0.79], floor: [0.93, 0.90, 0.83], clay: [0.85, 0.76, 0.66], hot: [0.86, 0.30, 0.16], warn: [0.93, 0.52, 0.12],
    fast: [0.36, 0.42, 0.14], mid: [0.80, 0.52, 0.10], slow: [0.80, 0.24, 0.12], opacity: 0.42 },
  olive: { bgTop: [0.16, 0.18, 0.11], bgBot: [0.10, 0.115, 0.07], floor: [0.20, 0.22, 0.14], clay: [0.84, 0.72, 0.60], hot: [0.95, 0.36, 0.18], warn: [0.98, 0.60, 0.16],
    fast: [0.80, 0.86, 0.55], mid: [0.98, 0.72, 0.28], slow: [0.98, 0.38, 0.20], opacity: 0.55 },
};

export class Renderer {
  constructor(gl, flow, theme = 'cream') {
    this.gl = gl; this.flow = flow; this.theme = THEMES[theme] || THEMES.cream;
    this.pScene = program(gl, FULLSCREEN_VS, SCENE_FS, 'scene');
    this.pComp = program(gl, FULLSCREEN_VS, COMP_FS, 'composite');
    if (flow && flow.ok) {
      this.pStreak = program(gl, STREAK_VS, STREAK_FS, 'streaks');
      this.pFade = program(gl, FULLSCREEN_VS, FADE_FS, 'fade');
    }
    this.w = 0; this.h = 0;
    this.capA = new Float32Array(MAX_CAPS * 4); this.capB = new Float32Array(MAX_CAPS * 4);
    this.partLoad = new Float32Array(10);
    this.cam = { az: -0.80, el: 0.20, dist: 6.4, target: [0.55, 0.0, 0.95], fov: 0.5, shift: [0, 0] };
  }

  resize(w, h) {
    if (w === this.w && h === this.h) return;
    const gl = this.gl; this.w = w; this.h = h;
    this.sceneC = texture(gl, w, h, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE);
    this.sceneD = texture(gl, w, h, gl.RGBA16F, gl.RGBA, gl.HALF_FLOAT);
    this.sceneFb = framebuffer(gl, [this.sceneC, this.sceneD]);
    this.trailA = texture(gl, w, h, gl.RGBA16F, gl.RGBA, gl.HALF_FLOAT); this.trailB = texture(gl, w, h, gl.RGBA16F, gl.RGBA, gl.HALF_FLOAT);
    this.trailFbA = framebuffer(gl, [this.trailA]); this.trailFbB = framebuffer(gl, [this.trailB]);
  }

  camera() {
    const c = this.cam, ce = Math.cos(c.el), aspect = this.w / this.h;
    const dist = c.dist * (aspect < 1 ? 1.0 + 0.55 * (1 / aspect - 1) : 1.0);     // pull back on tall screens
    const eye = [c.target[0] + dist * ce * Math.sin(c.az), c.target[1] + dist * ce * -Math.cos(c.az), c.target[2] + dist * Math.sin(c.el)];
    const L = lookAt(eye, c.target, [0, 0, 1]);
    return { ...L, tanHalf: Math.tan(c.fov / 2), VP: viewProj(L, c.fov, aspect, 0.05, 60, c.shift), shift: c.shift };
  }

  // caps: body capsules (world metres); loads: per-part 0..1; unsure: 0..1; dt seconds
  draw(caps, loads, unsure, dt) {
    const gl = this.gl, T = this.theme, cam = this.camera();
    const n = Math.min(caps.length, MAX_CAPS);
    const bMin = [1e9, 1e9, 1e9], bMax = [-1e9, -1e9, -1e9];
    for (let j = 0; j < n; j++) {
      const c = caps[j];
      this.capA.set([c.a[0], c.a[1], c.a[2], c.r], j * 4); this.capB.set([c.b[0], c.b[1], c.b[2], c.part], j * 4);
      for (let k = 0; k < 3; k++) { bMin[k] = Math.min(bMin[k], c.a[k] - c.r - 0.06, c.b[k] - c.r - 0.06); bMax[k] = Math.max(bMax[k], c.a[k] + c.r + 0.06, c.b[k] + c.r + 0.06); }
    }
    if (loads) this.partLoad.set(loads);
    // 1. scene
    const P = this.pScene;
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.sceneFb.fb); gl.drawBuffers(this.sceneFb.bufs); gl.viewport(0, 0, this.w, this.h);
    gl.disable(gl.BLEND);
    gl.useProgram(P.p);
    gl.uniform2f(P.u.res, this.w, this.h); gl.uniform2f(P.u.shift, cam.shift[0], cam.shift[1]); gl.uniform3fv(P.u.eye, cam.eye); gl.uniform3fv(P.u.camF, cam.f); gl.uniform3fv(P.u.camS, cam.s); gl.uniform3fv(P.u.camU, cam.u); gl.uniform1f(P.u.tanHalf, cam.tanHalf);
    gl.uniform1i(P.u.nc, n); gl.uniform4fv(P.u.capA, this.capA); gl.uniform4fv(P.u.capB, this.capB); gl.uniform1fv(P.u.partLoad, this.partLoad);
    gl.uniform3fv(P.u.bMin, bMin); gl.uniform3fv(P.u.bMax, bMax); gl.uniform1f(P.u.unsure, unsure);
    const fb = this.flow && this.flow.ok ? this.flow : { boxMin: [-1.5, -1.4, 0], boxMax: [3.3, 1.4, 2.5] };
    gl.uniform3fv(P.u.boxMin, fb.boxMin); gl.uniform3fv(P.u.boxMax, fb.boxMax);
    gl.uniform3fv(P.u.bgTop, T.bgTop); gl.uniform3fv(P.u.bgBot, T.bgBot); gl.uniform3fv(P.u.floorCol, T.floor); gl.uniform3fv(P.u.clayCol, T.clay); gl.uniform3fv(P.u.hotCol, T.hot); gl.uniform3fv(P.u.warnCol, T.warn);
    drawFullscreen(gl);
    // 2. streaks into the trail buffer
    if (this.flow && this.flow.ok) {
      const F = this.flow;
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.trailFbB.fb); gl.drawBuffers(this.trailFbB.bufs);
      gl.useProgram(this.pFade.p); bindTextures(gl, this.pFade, { T: this.trailA }); gl.uniform1f(this.pFade.u.fade, Math.exp(-dt / 0.42));
      drawFullscreen(gl);
      const S = this.pStreak;
      gl.useProgram(S.p);
      bindTextures(gl, S, { PA: F.PA.t, PB: F.PB.t, V: F.A.V, Mk: F.mask, sceneD: this.sceneD });
      F.velUniforms(S);
      gl.uniform2i(S.u.psize, F.pw, F.ph); gl.uniformMatrix4fv(S.u.VP, false, cam.VP); gl.uniform2f(S.u.res, this.w, this.h);
      gl.uniform1f(S.u.width, Math.max(0.9, this.h / 760)); gl.uniform1f(S.u.U, F.U); gl.uniform3fv(S.u.eye, cam.eye);
      gl.uniform3fv(S.u.boxMin, F.boxMin); gl.uniform3fv(S.u.boxMax, F.boxMax); gl.uniform3fv(S.u.camF, cam.f); gl.uniform3f(S.u.focus, 0.0, 0.0, 1.0);
      gl.uniform3fv(S.u.colFast, T.fast); gl.uniform3fv(S.u.colMid, T.mid); gl.uniform3fv(S.u.colSlow, T.slow); gl.uniform1f(S.u.opacity, T.opacity);
      gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, F.pw * F.ph);
      gl.disable(gl.BLEND);
      const t = this.trailA; this.trailA = this.trailB; this.trailB = t;
      const f = this.trailFbA; this.trailFbA = this.trailFbB; this.trailFbB = f;
    }
    // 3. composite
    gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.viewport(0, 0, this.w, this.h);
    gl.useProgram(this.pComp.p); bindTextures(gl, this.pComp, { S: this.sceneC, T: this.trailA }); gl.uniform2f(this.pComp.u.res, this.w, this.h);
    drawFullscreen(gl);
  }
}
