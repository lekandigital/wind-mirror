// The air you see: a coarse 3D lattice-Boltzmann simulation (D3Q19, regularised BGK with a Smagorinsky eddy viscosity,
// the same scheme as the full solver in engine/windtunnel/lbm.py) running live in WebGL2, plus tracer particles.
//
// It is a real flow simulation, but a coarse one (a few hundred thousand cells against the solver's 3.67 million) and it
// is here to be looked at. The force numbers on screen do NOT come from it; they come from the learned model.
//
// The 3D grid lives in 2D textures as an atlas of z-slices. Each cell stores 19 populations (minus their rest weights, so
// half-float precision is enough) across five RGBA textures; a sixth target holds velocity for the particles.
import { program, texture, framebuffer, bindTextures, drawFullscreen, FULLSCREEN_VS } from './gl.js';

const CX = [0, 1, -1, 0, 0, 0, 0, 1, -1, 1, -1, 1, -1, 1, -1, 0, 0, 0, 0];
const CY = [0, 0, 0, 1, -1, 0, 0, 1, -1, -1, 1, 0, 0, 0, 0, 1, -1, 1, -1];
const CZ = [0, 0, 0, 0, 0, 1, -1, 0, 0, 0, 0, 1, -1, -1, 1, 1, -1, -1, 1];
const W = [1 / 3, ...Array(6).fill(1 / 18), ...Array(12).fill(1 / 36)];
const OPP = [0, 2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15, 18, 17];
const MZ = CX.map((_, i) => CX.findIndex((__, j) => CX[j] === CX[i] && CY[j] === CY[i] && CZ[j] === -CZ[i]));
export const MAX_CAPS = 24;
const fl = (x) => (Number.isInteger(x) ? x.toFixed(1) : String(x));

const COMMON = `
precision highp float; precision highp int; precision highp sampler2D;
uniform ivec3 N; uniform int TX;
ivec2 atlas(ivec3 c) { return ivec2(c.x + (c.z % TX) * N.x, c.y + (c.z / TX) * N.y); }
ivec3 cellOf(ivec2 pix) { int tx = pix.x / N.x, ty = pix.y / N.y; return ivec3(pix.x - tx * N.x, pix.y - ty * N.y, ty * TX + tx); }
`;

function stepShader() {
  const fetchH = (i, at) => `texelFetch(T${i >> 2}, ${at}, 0)[${i & 3}]`;
  let pull = '';
  for (let i = 1; i < 19; i++) {
    const c = `vec3(${fl(CX[i])}, ${fl(CY[i])}, ${fl(CZ[i])})`;
    const bounce = `hc[${OPP[i]}] + ${fl(6 * W[i])} * dot(${c}, m.xyz)`;
    pull += `  { ivec3 s = c - ivec3(${CX[i]}, ${CY[i]}, ${CZ[i]}); s.y = (s.y + N.y) % N.y;\n`;
    if (CZ[i] !== 0) {
      pull += `    if (s.z < 0 || s.z >= N.z) { ivec2 a = atlas(ivec3(s.x, s.y, c.z)); vec4 m = texelFetch(M, a, 0);\n`;
      pull += `      f[${i}] = ${W[i]} + (m.a > 0.5 ? ${bounce} : ${fetchH(MZ[i], 'a')}); }\n    else `;
    }
    pull += `{ ivec2 a = atlas(s); vec4 m = texelFetch(M, a, 0); f[${i}] = ${W[i]} + (m.a > 0.5 ? ${bounce} : ${fetchH(i, 'a')}); } }\n`;
  }
  let eq = '', coll = '';
  for (let i = 0; i < 19; i++) {
    eq += `  { float cu = ${fl(CX[i])} * u.x + ${fl(CY[i])} * u.y + ${fl(CZ[i])} * u.z; feq[${i}] = ${W[i]} * rho * (1.0 + 3.0 * cu + 4.5 * cu * cu - 1.5 * usq); float d = f[${i}] - feq[${i}];\n`;
    if (CX[i]) eq += `    pxx += d;`; if (CY[i]) eq += ` pyy += d;`; if (CZ[i]) eq += ` pzz += d;`;
    if (CX[i] * CY[i]) eq += ` pxy += ${fl(CX[i] * CY[i])} * d;`; if (CX[i] * CZ[i]) eq += ` pxz += ${fl(CX[i] * CZ[i])} * d;`; if (CY[i] * CZ[i]) eq += ` pyz += ${fl(CY[i] * CZ[i])} * d;`;
    eq += ` }\n`;
    const q = `${fl(CX[i] * CX[i])} * pxx + ${fl(CY[i] * CY[i])} * pyy + ${fl(CZ[i] * CZ[i])} * pzz + 2.0 * (${fl(CX[i] * CY[i])} * pxy + ${fl(CX[i] * CZ[i])} * pxz + ${fl(CY[i] * CZ[i])} * pyz) - tr`;
    coll += `  g[${i}] = feq[${i}] + om * ${fl(4.5 * W[i])} * (${q}) - ${W[i]};\n`;
  }
  const eqOf = (rho, u) => { let s = ''; for (let i = 0; i < 19; i++) s += `  { float cu = dot(vec3(${fl(CX[i])}, ${fl(CY[i])}, ${fl(CZ[i])}), ${u}); g[${i}] = ${W[i]} * ${rho} * (1.0 + 3.0 * cu + 4.5 * cu * cu - 1.5 * dot(${u}, ${u})) - ${W[i]}; }\n`; return s; };
  return `#version 300 es
${COMMON}
uniform sampler2D T0, T1, T2, T3, T4, M;
uniform float U, tau0, cs2;
layout(location=0) out vec4 O0; layout(location=1) out vec4 O1; layout(location=2) out vec4 O2; layout(location=3) out vec4 O3; layout(location=4) out vec4 O4; layout(location=5) out vec4 OV;
void main() {
  ivec2 pix = ivec2(gl_FragCoord.xy);
  ivec3 c = cellOf(pix);
  float g[19];
  vec3 uout = vec3(0.0); float rout = 0.0;
  if (c.z >= N.z) { O0 = vec4(0.0); O1 = vec4(0.0); O2 = vec4(0.0); O3 = vec4(0.0); O4 = vec4(0.0); OV = vec4(0.0); return; }
  if (c.x == N.x - 1) c.x = N.x - 2;                       // outflow: copy the neighbour's new state
  vec4 mc = texelFetch(M, atlas(c), 0);
  vec3 uin = vec3(U, 0.0, 0.0);
  if (mc.a > 0.5) {
    vec3 uw = mc.xyz;
${eqOf('1.0', 'uw')}    uout = vec3(0.0);
  } else if (c.x == 0) {
${eqOf('1.0', 'uin')}    uout = uin;
  } else {
    ivec2 ac = atlas(c);
    vec4 h0 = texelFetch(T0, ac, 0), h1 = texelFetch(T1, ac, 0), h2 = texelFetch(T2, ac, 0), h3 = texelFetch(T3, ac, 0), h4 = texelFetch(T4, ac, 0);
    float hc[19];
    hc[0] = h0.x; hc[1] = h0.y; hc[2] = h0.z; hc[3] = h0.w; hc[4] = h1.x; hc[5] = h1.y; hc[6] = h1.z; hc[7] = h1.w; hc[8] = h2.x; hc[9] = h2.y; hc[10] = h2.z; hc[11] = h2.w;
    hc[12] = h3.x; hc[13] = h3.y; hc[14] = h3.z; hc[15] = h3.w; hc[16] = h4.x; hc[17] = h4.y; hc[18] = h4.z;
    float f[19];
    f[0] = hc[0] + ${W[0]};
${pull}
    float rho = 0.0; vec3 mom = vec3(0.0);
    for (int i = 0; i < 19; i++) rho += f[i];
    mom.x = f[1] - f[2] + f[7] - f[8] + f[9] - f[10] + f[11] - f[12] + f[13] - f[14];
    mom.y = f[3] - f[4] + f[7] - f[8] - f[9] + f[10] + f[15] - f[16] + f[17] - f[18];
    mom.z = f[5] - f[6] + f[11] - f[12] - f[13] + f[14] + f[15] - f[16] - f[17] + f[18];
    vec3 u = mom / rho;
    float usq = dot(u, u);
    if (!(rho > 0.5 && rho < 1.6) || !(usq < 0.16)) {         // guard: a cell that went wrong restarts as free stream
${eqOf('1.0', 'uin')}      uout = uin;
    } else {
      float feq[19]; float pxx = 0.0, pyy = 0.0, pzz = 0.0, pxy = 0.0, pxz = 0.0, pyz = 0.0;
${eq}
      float qn = sqrt(pxx * pxx + pyy * pyy + pzz * pzz + 2.0 * (pxy * pxy + pxz * pxz + pyz * pyz));
      float tau = 0.5 * (tau0 + sqrt(tau0 * tau0 + 25.4558441 * cs2 * qn / rho));
      float om = 1.0 - 1.0 / tau;
      float tr = (pxx + pyy + pzz) / 3.0;
${coll}
      uout = u; rout = rho - 1.0;
    }
  }
  O0 = vec4(g[0], g[1], g[2], g[3]); O1 = vec4(g[4], g[5], g[6], g[7]); O2 = vec4(g[8], g[9], g[10], g[11]); O3 = vec4(g[12], g[13], g[14], g[15]); O4 = vec4(g[16], g[17], g[18], 0.0);
  OV = vec4(uout, rout);
}`;
}

const MASK_FS = `#version 300 es
${COMMON}
uniform vec3 origin; uniform float dx; uniform float inflate; uniform int nc;
uniform vec4 capA[${MAX_CAPS}]; uniform vec4 capB[${MAX_CAPS}]; uniform vec3 velA[${MAX_CAPS}]; uniform vec3 velB[${MAX_CAPS}];
out vec4 O;
void main() {
  ivec3 c = cellOf(ivec2(gl_FragCoord.xy));
  if (c.z >= N.z) { O = vec4(0.0); return; }
  vec3 p = origin + (vec3(c) + 0.5) * dx;
  float best = 1e9; vec3 v = vec3(0.0);
  for (int j = 0; j < ${MAX_CAPS}; j++) {
    if (j >= nc) break;
    vec3 a = capA[j].xyz, ba = capB[j].xyz - a, pa = p - a;
    float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-9), 0.0, 1.0);
    float d = length(pa - ba * h) - capA[j].w;
    if (d < best) { best = d; v = mix(velA[j], velB[j], h); }
  }
  O = best < inflate ? vec4(v, 1.0) : vec4(0.0);
}`;

const INIT_FS = `#version 300 es
${COMMON}
uniform float U;
layout(location=0) out vec4 O0; layout(location=1) out vec4 O1; layout(location=2) out vec4 O2; layout(location=3) out vec4 O3; layout(location=4) out vec4 O4; layout(location=5) out vec4 OV;
void main() {
  float g[19]; vec3 u = vec3(U, 0.0, 0.0);
${(() => { let s = ''; for (let i = 0; i < 19; i++) s += `  { float cu = dot(vec3(${fl(CX[i])}, ${fl(CY[i])}, ${fl(CZ[i])}), u); g[${i}] = ${W[i]} * (1.0 + 3.0 * cu + 4.5 * cu * cu - 1.5 * dot(u, u)) - ${W[i]}; }\n`; return s; })()}
  O0 = vec4(g[0], g[1], g[2], g[3]); O1 = vec4(g[4], g[5], g[6], g[7]); O2 = vec4(g[8], g[9], g[10], g[11]); O3 = vec4(g[12], g[13], g[14], g[15]); O4 = vec4(g[16], g[17], g[18], 0.0);
  OV = vec4(u, 0.0);
}`;

// Shared GLSL: sample the velocity atlas at a world position (trilinear: hardware bilinear inside a slice, manual between slices).
export const SAMPLE_VEL = `
uniform sampler2D V; uniform sampler2D Mk; uniform vec3 origin; uniform float dx; uniform ivec3 N; uniform int TX; uniform vec2 atlasSize;
vec2 tileUV(vec2 gxy, int z) { vec2 q = clamp(gxy, vec2(0.5), vec2(N.xy) - 0.5); return (q + vec2(float(z % TX) * float(N.x), float(z / TX) * float(N.y))) / atlasSize; }
vec4 sampleVel(vec3 p) {
  vec3 g = (p - origin) / dx;
  float zf = clamp(g.z - 0.5, 0.0, float(N.z) - 1.001);
  int z0 = int(floor(zf)); float fz = zf - float(z0);
  return mix(texture(V, tileUV(g.xy, z0)), texture(V, tileUV(g.xy, z0 + 1)), fz);
}
bool inSolid(vec3 p) {
  ivec3 c = ivec3(floor((p - origin) / dx));
  if (any(lessThan(c, ivec3(0))) || any(greaterThanEqual(c, N))) return false;
  return texelFetch(Mk, ivec2(c.x + (c.z % TX) * N.x, c.y + (c.z / TX) * N.y), 0).a > 0.5;
}`;

const PART_FS = `#version 300 es
precision highp float; precision highp int; precision highp sampler2D;
${SAMPLE_VEL}
uniform sampler2D P; uniform float dt, speed, time, U; uniform vec3 boxMin, boxMax; uniform ivec2 rake; uniform vec4 rakeYZ; uniform int pw;
out vec4 O;
float hash(vec3 p) { p = fract(p * vec3(443.897, 441.423, 437.195)); p += dot(p, p.yzx + 19.19); return fract((p.x + p.y) * p.z); }
void main() {
  ivec2 pix = ivec2(gl_FragCoord.xy);
  vec4 s = texelFetch(P, pix, 0);
  vec3 p = s.xyz; float age = s.w;
  vec3 seed = vec3(vec2(pix) * 0.37, time * 1.31);
  bool dead = age > 9.0 || any(lessThan(p, boxMin)) || any(greaterThan(p, boxMax)) || (age > 0.0 && inSolid(p));
  if (dead) {
    // tracers are released from a rake of fixed points just inside the inlet, like smoke filaments in a wind tunnel
    int id = pix.x + pix.y * pw, cell = id % (rake.x * rake.y);
    vec2 g = (vec2(float(cell % rake.x), float(cell / rake.x)) + 0.5) / vec2(rake);
    p = vec3(boxMin.x + 0.04, mix(rakeYZ.x, rakeYZ.y, g.x), mix(rakeYZ.z, rakeYZ.w, g.y)) + (vec3(hash(seed), hash(seed + 3.7), hash(seed + 9.1)) - 0.5) * vec3(0.03, 0.014, 0.014);
    age = -hash(seed + 5.3) * 1.2;                               // wait a moment before release, so releases are staggered
  } else if (age < 0.0) {
    age += dt;
  } else {
    vec3 u = sampleVel(p).xyz;
    vec3 pm = p + 0.5 * dt * speed * u;                        // midpoint step
    p += dt * speed * sampleVel(pm).xyz;
    age += dt;
  }
  O = vec4(p, age);
}`;

const TIERS = { S: 0.0625, M: 0.05, L: 0.04, XL: 0.034 };

export class Flow {
  constructor(gl, caps, opts = {}) {
    this.gl = gl;
    this.ok = false;
    const dx = TIERS[opts.tier || 'M'] || TIERS.M;
    this.dx = dx;
    this.boxMin = [-1.5, -1.4, 0.0]; this.boxMax = [3.3, 1.4, 2.5];
    this.N = [Math.round((this.boxMax[0] - this.boxMin[0]) / dx), Math.round((this.boxMax[1] - this.boxMin[1]) / dx), Math.round((this.boxMax[2] - this.boxMin[2]) / dx)];
    this.TX = Math.ceil(Math.sqrt(this.N[2] * this.N[1] / this.N[0]));
    this.TY = Math.ceil(this.N[2] / this.TX);
    this.aw = this.N[0] * this.TX; this.ah = this.N[1] * this.TY;
    this.U = opts.U || 0.09; this.nu = opts.nu || 0.004; this.cs = opts.cs || 0.16;
    this.cells = this.N[0] * this.N[1] * this.N[2];
    if (caps.drawBuffers < 6 || !(caps.float || caps.halfFloat)) { this.reason = 'this browser cannot render to enough float targets'; return; }
    const useFloat = caps.float;
    const internal = useFloat ? gl.RGBA32F : gl.RGBA16F, type = useFloat ? gl.FLOAT : gl.HALF_FLOAT;
    this.precision = useFloat ? 'float32' : 'float16';
    const mkSet = () => {
      const T = [0, 1, 2, 3, 4].map(() => texture(gl, this.aw, this.ah, internal, gl.RGBA, type));
      const V = texture(gl, this.aw, this.ah, gl.RGBA16F, gl.RGBA, gl.HALF_FLOAT, gl.LINEAR);
      const f = framebuffer(gl, [...T, V]);
      return { T, V, fb: f.fb, ok: f.ok, bufs: f.bufs };
    };
    this.A = mkSet(); this.B = mkSet();
    if (!this.A.ok || !this.B.ok) { this.reason = 'float framebuffer incomplete'; return; }
    this.mask = texture(gl, this.aw, this.ah, gl.RGBA16F, gl.RGBA, gl.HALF_FLOAT);
    this.maskFb = framebuffer(gl, [this.mask]);
    this.pStep = program(gl, FULLSCREEN_VS, stepShader(), 'lbm step');
    this.pMask = program(gl, FULLSCREEN_VS, MASK_FS, 'mask');
    this.pInit = program(gl, FULLSCREEN_VS, INIT_FS, 'init');
    this.pPart = program(gl, FULLSCREEN_VS, PART_FS, 'particles');
    // tracer particles
    this.pw = opts.particlesW || 128; this.ph = opts.particlesH || 64;
    this.rake = opts.rake || [9, 13]; this.rakeYZ = opts.rakeYZ || [-0.72, 0.72, 0.12, 2.0];
    const init = new Float32Array(this.pw * this.ph * 4);
    for (let i = 0; i < this.pw * this.ph; i++) {
      init[i * 4] = this.boxMin[0] + Math.random() * (this.boxMax[0] - this.boxMin[0]);
      init[i * 4 + 1] = this.boxMin[1] + Math.random() * (this.boxMax[1] - this.boxMin[1]);
      init[i * 4 + 2] = this.boxMin[2] + Math.random() * (this.boxMax[2] - this.boxMin[2]);
      init[i * 4 + 3] = 10.0;                                   // start 'dead': every tracer begins at the rake
    }
    const pt = () => { const t = texture(gl, this.pw, this.ph, gl.RGBA32F, gl.RGBA, gl.FLOAT, gl.NEAREST, init); return { t, f: framebuffer(gl, [t]) }; };
    this.particlesFloat = caps.float;
    if (!caps.float) { this.reason = 'particles need float render targets'; return; }
    this.PA = pt(); this.PB = pt();
    if (!this.PA.f.ok) { this.reason = 'particle framebuffer incomplete'; return; }
    this.capA = new Float32Array(MAX_CAPS * 4); this.capB = new Float32Array(MAX_CAPS * 4);
    this.velA = new Float32Array(MAX_CAPS * 3); this.velB = new Float32Array(MAX_CAPS * 3);
    this.prevCaps = null; this.nc = 0; this.steps = 0; this.time = 0;
    this.reset();
    this.ok = true;
  }

  _grid(prog) { const gl = this.gl; gl.uniform3i(prog.u.N, this.N[0], this.N[1], this.N[2]); gl.uniform1i(prog.u.TX, this.TX); }

  reset() {
    const gl = this.gl;
    for (const S of [this.A, this.B]) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, S.fb); gl.drawBuffers(S.bufs); gl.viewport(0, 0, this.aw, this.ah);
      gl.useProgram(this.pInit.p); this._grid(this.pInit); gl.uniform1f(this.pInit.u.U, this.U);
      drawFullscreen(gl);
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }

  // caps: [{a, b, r}] in world metres. substeps: how many solver steps this frame will take (for wall velocities).
  setBody(caps, substeps) {
    const gl = this.gl;
    const n = Math.min(caps.length, MAX_CAPS);
    const vmax = 0.12;
    for (let j = 0; j < n; j++) {
      const c = caps[j], p = this.prevCaps && this.prevCaps[j];
      this.capA.set([c.a[0], c.a[1], c.a[2], c.r], j * 4); this.capB.set([c.b[0], c.b[1], c.b[2], c.r], j * 4);
      for (const [arr, cur, prev] of [[this.velA, c.a, p && p.a], [this.velB, c.b, p && p.b]]) {
        let v = [0, 0, 0];
        if (prev && substeps > 0) v = [0, 1, 2].map((k) => (cur[k] - prev[k]) / this.dx / substeps);   // cells per step
        const m = Math.hypot(v[0], v[1], v[2]);
        if (m > vmax) v = v.map((x) => (x * vmax) / m);
        arr.set(v, j * 3);
      }
    }
    this.prevCaps = caps.slice(0, n).map((c) => ({ a: [...c.a], b: [...c.b] }));
    this.nc = n;
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.maskFb.fb); gl.drawBuffers(this.maskFb.bufs); gl.viewport(0, 0, this.aw, this.ah);
    gl.useProgram(this.pMask.p); this._grid(this.pMask);
    gl.uniform3fv(this.pMask.u.origin, this.boxMin); gl.uniform1f(this.pMask.u.dx, this.dx); gl.uniform1f(this.pMask.u.inflate, 0.3 * this.dx); gl.uniform1i(this.pMask.u.nc, n);
    gl.uniform4fv(this.pMask.u.capA, this.capA); gl.uniform4fv(this.pMask.u.capB, this.capB); gl.uniform3fv(this.pMask.u.velA, this.velA); gl.uniform3fv(this.pMask.u.velB, this.velB);
    drawFullscreen(gl);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }

  step(n) {
    const gl = this.gl, P = this.pStep;
    gl.useProgram(P.p); this._grid(P);
    gl.uniform1f(P.u.U, this.U); gl.uniform1f(P.u.tau0, 0.5 + 3 * this.nu); gl.uniform1f(P.u.cs2, this.cs * this.cs);
    gl.viewport(0, 0, this.aw, this.ah);
    for (let i = 0; i < n; i++) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.B.fb); gl.drawBuffers(this.B.bufs);
      bindTextures(gl, P, { T0: this.A.T[0], T1: this.A.T[1], T2: this.A.T[2], T3: this.A.T[3], T4: this.A.T[4], M: this.mask });
      drawFullscreen(gl);
      const t = this.A; this.A = this.B; this.B = t;
      this.steps++;
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }

  velUniforms(prog) {
    const gl = this.gl;
    gl.uniform3fv(prog.u.origin, this.boxMin); gl.uniform1f(prog.u.dx, this.dx);
    gl.uniform3i(prog.u.N, this.N[0], this.N[1], this.N[2]); gl.uniform1i(prog.u.TX, this.TX); gl.uniform2f(prog.u.atlasSize, this.aw, this.ah);
  }

  // dt seconds of wall time; speed converts lattice velocity to metres per second on screen.
  advect(dt, stepsPerSecond) {
    const gl = this.gl, P = this.pPart;
    this.time += dt;
    this.speed = this.dx * stepsPerSecond;                      // a tracer moves exactly as fast as the flow pattern itself
    gl.useProgram(P.p);
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.PB.f.fb); gl.drawBuffers(this.PB.f.bufs); gl.viewport(0, 0, this.pw, this.ph);
    bindTextures(gl, P, { P: this.PA.t, V: this.A.V, Mk: this.mask });
    this.velUniforms(P);
    gl.uniform1f(P.u.dt, dt); gl.uniform1f(P.u.speed, this.speed); gl.uniform1f(P.u.time, this.time % 1000); gl.uniform1f(P.u.U, this.U);
    gl.uniform3fv(P.u.boxMin, this.boxMin); gl.uniform3fv(P.u.boxMax, this.boxMax);
    gl.uniform2i(P.u.rake, this.rake[0], this.rake[1]); gl.uniform4fv(P.u.rakeYZ, this.rakeYZ); gl.uniform1i(P.u.pw, this.pw);
    drawFullscreen(gl);
    const t = this.PA; this.PA = this.PB; this.PB = t;           // PA = current, PB = previous
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }
}
