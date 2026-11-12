// Body tracking: MediaPipe pose landmarks -> the twin's 12 bone directions, with low-lag smoothing.
// The camera is only opened by an explicit click (see main.js); recorded clips go through the same path.
import { unit, sub, mul, dot } from './body.js';

const VISION = new URL('../vendor/mediapipe/vision_bundle.mjs', import.meta.url).href;
const WASM = new URL('../vendor/mediapipe/wasm', import.meta.url).href;
const MODELS = { lite: new URL('../vendor/mediapipe/pose_landmarker_lite.task', import.meta.url).href, full: new URL('../vendor/mediapipe/pose_landmarker_full.task', import.meta.url).href };

// One-Euro filter (Casiez et al. 2012): heavy smoothing when still, almost none when moving fast.
class OneEuro {
  constructor(n, minCutoff = 1.6, beta = 0.6, dCutoff = 1.0) { this.n = n; this.minCutoff = minCutoff; this.beta = beta; this.dCutoff = dCutoff; this.x = null; this.dx = new Float64Array(n); this.t = 0; }
  static alpha(cutoff, dt) { const tau = 1 / (2 * Math.PI * cutoff); return 1 / (1 + tau / dt); }
  filter(v, t) {
    if (!this.x) { this.x = Float64Array.from(v); this.t = t; return this.x; }
    const dt = Math.max(t - this.t, 1e-3); this.t = t;
    const ad = OneEuro.alpha(this.dCutoff, dt);
    for (let i = 0; i < this.n; i++) {
      const d = (v[i] - this.x[i]) / dt;
      this.dx[i] += ad * (d - this.dx[i]);
      const a = OneEuro.alpha(this.minCutoff + this.beta * Math.abs(this.dx[i]), dt);
      this.x[i] += a * (v[i] - this.x[i]);
    }
    return this.x;
  }
  reset() { this.x = null; this.dx.fill(0); }
}

// MediaPipe world landmarks (x to image right, y down, z away from the camera) -> tunnel frame (x downwind, y, z up).
// The person faces the camera, and the wind comes from the camera.
const toWorld = (p) => [p[2], -p[0], -p[1]];

export function retarget(lm) {
  const p = (i) => toWorld(lm[i]);
  const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];
  const pel = mid(p(23), p(24)), neck = mid(p(11), p(12));
  const t = unit(sub(neck, pel));
  const orth = (v) => unit(sub(v, mul(t, dot(v, t))));
  const l = orth(unit(sub(p(11), p(12))));
  const lh = orth(unit(sub(p(23), p(24))));
  const h = unit(sub(mid(p(7), p(8)), neck));
  return { t, l, h, lh, uaL: unit(sub(p(13), p(11))), faL: unit(sub(p(15), p(13))), uaR: unit(sub(p(14), p(12))), faR: unit(sub(p(16), p(14))),
    thL: unit(sub(p(25), p(23))), shL: unit(sub(p(27), p(25))), thR: unit(sub(p(26), p(24))), shR: unit(sub(p(28), p(26))) };
}

export class Tracker {
  constructor() { this.lm = null; this.filter = new OneEuro(99); this.ready = false; this.inferMs = 0; this.frames = 0; this.lastVideoTime = -1; this.visibility = null; this.delegate = 'GPU'; }

  async init(model = 'full') {
    const { FilesetResolver, PoseLandmarker } = await import(/* @vite-ignore */ VISION);
    const files = await FilesetResolver.forVisionTasks(WASM);
    const make = (delegate) => PoseLandmarker.createFromOptions(files, { baseOptions: { modelAssetPath: MODELS[model] || MODELS.full, delegate }, runningMode: 'VIDEO', numPoses: 1 });
    try { this.landmarker = await make('GPU'); } catch (e) { this.landmarker = await make('CPU'); this.delegate = 'CPU'; }
    this.ready = true;
  }

  // Call once per displayed frame. Returns {pose, visibility, fresh} or null when no body has been seen yet.
  // Ask the browser to tell us when a new picture arrives, so each one is tracked once (not once per screen refresh).
  attach(video) {
    if (this.video === video || !video.requestVideoFrameCallback) return;
    this.video = video; this.rvfc = true;
    const cb = (now, meta) => { this.newFrame = true; this.mediaTime = meta.mediaTime; video.requestVideoFrameCallback(cb); };
    video.requestVideoFrameCallback(cb);
  }

  update(video, nowMs) {
    if (!this.ready || video.readyState < 2) return this.out || null;
    this.attach(video);
    if (this.rvfc) { if (!this.newFrame) return this.out ? { ...this.out, fresh: false } : null; this.newFrame = false; }
    else { if (video.currentTime === this.lastVideoTime) return this.out ? { ...this.out, fresh: false } : null; this.mediaTime = video.currentTime; }
    this.lastVideoTime = video.currentTime;
    const t0 = performance.now();
    const r = this.landmarker.detectForVideo(video, nowMs);
    this.inferMs += (performance.now() - t0 - this.inferMs) * 0.1;
    if (!r.worldLandmarks || !r.worldLandmarks.length) { this.missed = (this.missed || 0) + 1; return this.out ? { ...this.out, fresh: false, lost: true } : null; }
    this.frames++;
    const wl = r.worldLandmarks[0];
    const flat = new Float64Array(99);
    for (let i = 0; i < 33; i++) { flat[i * 3] = wl[i].x; flat[i * 3 + 1] = wl[i].y; flat[i * 3 + 2] = wl[i].z; }
    const rawLm = []; for (let i = 0; i < 33; i++) rawLm.push([flat[i * 3], flat[i * 3 + 1], flat[i * 3 + 2]]);
    const rawPose = retarget(rawLm);
    const f = this.filter.filter(flat, nowMs / 1000);
    const lm = []; for (let i = 0; i < 33; i++) lm.push([f[i * 3], f[i * 3 + 1], f[i * 3 + 2]]);
    const vis = wl.map((q) => q.visibility ?? 1);
    const g = (ids) => Math.min(...ids.map((i) => vis[i]));
    this.out = { pose: retarget(lm), rawPose, mediaTime: this.mediaTime, raw: wl, image: r.landmarks[0], fresh: true, lost: false,
      visibility: { arms: g([11, 12, 13, 14, 15, 16]), legs: g([23, 24, 25, 26, 27, 28]), all: g([11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]) } };
    return this.out;
  }
}
