// Small WebGL2 helpers. No dependencies.

export function createGL(canvas) {
  const gl = canvas.getContext('webgl2', { antialias: false, alpha: false, depth: false, stencil: false, powerPreference: 'high-performance', preserveDrawingBuffer: !!canvas.dataset.keep });
  if (!gl) return null;
  const caps = {
    float: !!gl.getExtension('EXT_color_buffer_float'),
    halfFloat: !!gl.getExtension('EXT_color_buffer_half_float'),
    floatLinear: !!gl.getExtension('OES_texture_float_linear'),
    drawBuffers: gl.getParameter(gl.MAX_DRAW_BUFFERS),
    maxTex: gl.getParameter(gl.MAX_TEXTURE_SIZE),
    renderer: (() => { const e = gl.getExtension('WEBGL_debug_renderer_info'); return e ? gl.getParameter(e.UNMASKED_RENDERER_WEBGL) : 'unknown'; })(),
  };
  return { gl, caps };
}

export function program(gl, vsSrc, fsSrc, name = '') {
  const mk = (type, src) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      const log = gl.getShaderInfoLog(s);
      const lines = src.split('\n').map((l, i) => `${i + 1}: ${l}`).join('\n');
      throw new Error(`shader compile failed (${name}):\n${log}\n${lines.slice(0, 6000)}`);
    }
    return s;
  };
  const p = gl.createProgram();
  gl.attachShader(p, mk(gl.VERTEX_SHADER, vsSrc)); gl.attachShader(p, mk(gl.FRAGMENT_SHADER, fsSrc));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(`program link failed (${name}): ${gl.getProgramInfoLog(p)}`);
  const uniforms = {};
  const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
  for (let i = 0; i < n; i++) { const info = gl.getActiveUniform(p, i); const nm = info.name.replace(/\[0\]$/, ''); uniforms[nm] = gl.getUniformLocation(p, info.name); }
  return { p, u: uniforms };
}

export const FULLSCREEN_VS = `#version 300 es
void main() { vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2)); gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0); }`;

export function texture(gl, w, h, internal, format, type, filter = gl.NEAREST, data = null) {
  const t = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, t);
  gl.texImage2D(gl.TEXTURE_2D, 0, internal, w, h, 0, format, type, data);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  return t;
}

export function framebuffer(gl, textures) {
  const fb = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
  const bufs = [];
  textures.forEach((t, i) => { gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0 + i, gl.TEXTURE_2D, t, 0); bufs.push(gl.COLOR_ATTACHMENT0 + i); });
  gl.drawBuffers(bufs);
  const ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  return { fb, ok, bufs };
}

export function bindTextures(gl, prog, map) {
  let unit = 0;
  for (const [name, tex] of Object.entries(map)) {
    gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, tex);
    if (prog.u[name] !== undefined) gl.uniform1i(prog.u[name], unit);
    unit++;
  }
}

export function drawFullscreen(gl) { gl.drawArrays(gl.TRIANGLES, 0, 3); }

// Camera maths (column-major 4x4, as WebGL expects).
export function lookAt(eye, target, up) {
  const f = nrm(sub(target, eye)), s = nrm(crs(f, up)), u = crs(s, f);
  return { eye, f, s, u };
}
export function viewProj(cam, fovY, aspect, near = 0.05, far = 60, shift = [0, 0]) {
  const { eye, f, s, u } = cam;
  const V = [s[0], u[0], -f[0], 0, s[1], u[1], -f[1], 0, s[2], u[2], -f[2], 0, -dot(s, eye), -dot(u, eye), dot(f, eye), 1];
  const t = 1 / Math.tan(fovY / 2);
  const P = [t / aspect, 0, 0, 0, 0, t, 0, 0, 0, 0, (far + near) / (near - far), -1, 0, 0, (2 * far * near) / (near - far), 0];
  const T = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  T[12] = shift[0]; T[13] = shift[1];                        // slide the picture: clip.xy += shift * clip.w
  return mat4mul(T, mat4mul(P, V));
}
export function mat4mul(a, b) {
  const o = new Array(16).fill(0);
  for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) for (let k = 0; k < 4; k++) o[c * 4 + r] += a[k * 4 + r] * b[c * 4 + k];
  return o;
}
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const crs = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const nrm = (a) => { const n = Math.hypot(a[0], a[1], a[2]); return [a[0] / n, a[1] / n, a[2] / n]; };
