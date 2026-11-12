// A thousand positions, each checked by the learned model in this tab, drawn as small clay figures.
// Olive ground: the model is sure. Orange: not sure, so it would go to the solver. The time shown is measured here.
import { poseFromList, bodyCapsules } from './body.js';
import { featuresFromCapsules } from './geom.js';
import { ModelB } from './model_b.js';

const qs = new URLSearchParams(location.search);
const $ = (id) => document.getElementById(id);
const cv = $('grid'), g = cv.getContext('2d');
const S = (window.__wm = { done: false, errors: [] });
const SOLVER_S = Number(qs.get('solver') || 5.8);              // measured seconds per solver run on the RTX 3090 Ti
const az = -0.80, el = 0.20;
const sx = [Math.cos(az), Math.sin(az), 0], up = [-Math.sin(el) * Math.sin(az) * -1, 0, 0];
// orthographic 3/4 view matching the main page's camera direction
const right = [Math.cos(az), Math.sin(az), 0], fwd = [Math.cos(el) * -Math.sin(az), Math.cos(el) * Math.cos(az), -Math.sin(el)];
const upv = [fwd[1] * right[2] - fwd[2] * right[1], fwd[2] * right[0] - fwd[0] * right[2], fwd[0] * right[1] - fwd[1] * right[0]].map((v) => -v);
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

function drawTwin(caps, cx, cy, s, sure, alpha) {
  const segs = caps.map((c) => ({ a: [dot(c.a, right), dot(c.a, upv)], b: [dot(c.b, right), dot(c.b, upv)], d: dot(c.a, fwd) + dot(c.b, fwd), r: c.r }));
  segs.sort((p, q) => q.d - p.d);
  g.lineCap = 'round';
  for (const k of segs) {
    const shade = Math.max(0, Math.min(1, 0.5 - k.d * 0.22));
    const col = sure ? [205 - 40 * shade, 180 - 42 * shade, 150 - 44 * shade] : [232 - 30 * shade, 140 - 30 * shade, 40 - 10 * shade];
    g.strokeStyle = `rgba(${col[0] | 0},${col[1] | 0},${col[2] | 0},${alpha})`;
    g.lineWidth = Math.max(k.r * 2 * s, 0.8);
    g.beginPath(); g.moveTo(cx + k.a[0] * s, cy - k.a[1] * s); g.lineTo(cx + k.b[0] * s + 0.01, cy - k.b[1] * s); g.stroke();
  }
}

async function run() {
  const [poses, model] = await Promise.all([fetch('models/thousand.json').then((r) => r.json()), ModelB.load(qs.get('m') || 'models/model_b.json')]);
  const dpr = Math.min(devicePixelRatio || 1, 2);
  const W = (cv.width = Math.round(innerWidth * dpr)), H = (cv.height = Math.round(innerHeight * dpr));
  const N = poses.length, aspect = W / H;
  const cols = Math.round(Math.sqrt(N * aspect * 0.8)), rows = Math.ceil(N / cols);
  const top = H * (aspect > 1 ? 0.27 : 0.2), cw = W / (cols + 1), ch = (H - top - H * (aspect > 1 ? 0.03 : 0.12)) / rows, s = Math.min(cw, ch) / 2.1;
  const items = poses.map((p, i) => ({ caps: null, i, x: cw * (0.9 + (i % cols)), y: top + ch * (Math.floor(i / cols) + 0.86), sure: true, shown: -1 }));
  let done = 0, ms = 0, nSure = 0;
  // warm up the code paths, so the measured time is steady-state
  for (let i = 0; i < 30; i++) model.check(featuresFromCapsules(bodyCapsules(poseFromList(poses[i].p), poses[i].b)));
  const t0 = performance.now();
  function frame(now) {
    const per = Math.max(8, Math.round(N / 75));
    const a = performance.now();
    const batch = [];
    for (let k = 0; k < per && done < N; k++, done++) {
      const it = items[done]; it.caps = bodyCapsules(poseFromList(poses[done].p), poses[done].b);
      const r = model.check(featuresFromCapsules(it.caps)); it.sure = r.sure; it.bound = r.bound; nSure += r.sure ? 1 : 0; it.shown = now; batch.push(it);
    }
    ms += performance.now() - a;
    g.clearRect(0, 0, W, H);
    for (let i = 0; i < done; i++) {
      const it = items[i], age = Math.min((now - it.shown) / 260, 1);
      g.fillStyle = it.sure ? `rgba(93,107,34,${0.16 * age})` : `rgba(217,133,18,${0.3 * age})`;
      g.beginPath(); g.ellipse(it.x, it.y, s * 0.62, s * 0.2, 0, 0, 7); g.fill();
      drawTwin(it.caps, it.x, it.y, s * (0.75 + 0.25 * age), it.sure, age);
    }
    $('n').textContent = done.toLocaleString('en-US');
    $('t').textContent = done < N ? `${(ms / 1000).toFixed(2)} s` : `${(ms / 1000).toFixed(2)} seconds.`;
    if (done >= N && !S.done) {
      S.done = true; S.ms = ms; S.nSure = nSure; S.n = N; S.wall = performance.now() - t0;
      $('tally').hidden = false; $('ns').textContent = nSure; $('nu').textContent = N - nSure;
      const sec = N * SOLVER_S; $('solo').textContent = sec >= 3600 ? `${Math.floor(sec / 3600)} h ${Math.round((sec % 3600) / 60)} min` : `${Math.round(sec / 60)} min`;
    }
    if (done < N || now - items[N - 1].shown < 400) requestAnimationFrame(frame);
  }
  setTimeout(() => requestAnimationFrame(frame), Number(qs.get('delay') || 600));
}
run().catch((e) => { S.errors.push(String(e.stack || e)); console.error(e); });
