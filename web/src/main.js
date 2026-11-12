// Wind Mirror: page logic. Tracks a body (recorded clip, or the camera after a click), poses the twin, asks the learned
// model for the force and its error bound every frame, and shows the live air around the twin.
import { createGL } from './gl.js';
import { Flow } from './flow.js';
import { Renderer } from './render.js';
import { Tracker } from './tracker.js';
import { bodyCapsules, standingPose, poseFromList, BONES, unit, cross, add, mul, sub, dot } from './body.js';
import { featuresFromCapsules, NG } from './geom.js';
import { Model, Q_KG_PER_M2 } from './model.js';
import { ModelB } from './model_b.js';

const qs = new URLSearchParams(location.search);
const $ = (id) => document.getElementById(id);
const canvas = $('gl'), video = $('video');
if (qs.has('keep')) canvas.dataset.keep = '1';
const S = (window.__wm = { frames: 0, fps: 0, ready: false, errors: [], log: [] });
if (qs.has('embed')) document.body.classList.add('embed', 'capture');
if (qs.has('bare')) document.body.classList.add('bare');
S.caption = (text, top) => { const c = document.getElementById('caption'); c.textContent = text || ''; c.hidden = !text; c.classList.toggle('top', !!top); };
window.addEventListener('error', (e) => S.errors.push(String(e.message)));
window.addEventListener('unhandledrejection', (e) => S.errors.push(String(e.reason && e.reason.message || e.reason)));

const ctx = createGL(canvas);
if (!ctx) { $('chip-text').textContent = 'this browser has no WebGL2'; throw new Error('no WebGL2'); }
const { gl, caps: glcaps } = ctx;
S.gl = glcaps;
const dprCap = Number(qs.get('dpr') || 2);
const tier = qs.get('tier') || (matchMedia('(max-width: 820px)').matches ? 'S' : 'M');
const flow = new Flow(gl, glcaps, { tier, nu: Number(qs.get('nu') || 0.0016), U: Number(qs.get('U') || 0.09), cs: Number(qs.get('cs') || 0.17),
  particlesW: Number(qs.get('pw') || 128), particlesH: Number(qs.get('ph') || 64) });
const renderer = new Renderer(gl, flow, qs.get('theme') || 'cream');
const substeps = Number(qs.get('sub') || 8);
S.flow = { ok: flow.ok, reason: flow.reason, grid: flow.N, cells: flow.cells, precision: flow.precision, substeps };

const tracker = new Tracker();
let model = null, shape = null;
let pose = standingPose(), caps = bodyCapsules(pose, shape);
let result = null, haveBody = false;
const smooth = { kg: 0, lift: 0, side: 0, bound: 0, init: false };
let verdict = 'idle', verdictSince = 0, unsureLevel = 0, checkMs = 0;
const loads = new Float32Array(10);
const NEUTRAL = standingPose(); let legW = 1;
const ENGINE = qs.has('noengine') ? null : (qs.get('engine') || 'http://127.0.0.1:5311');
const autoAsk = qs.get('ask') !== 'manual', ASK_MS = Number(qs.get('askms') || 250);
let engineUp = false, solving = null, lastSolveEnd = -1e9, unsureSince = 0;
const ledger = [];

// Not sure: send this exact body to the real flow solver, show its answer next to the model's guess, and let the model learn it.
const inflight = [];                                          // questions with the solver right now (at most two)
const snapshot = () => ({ pose: BONES.map((b) => (pose[b] || pose.l).slice()), body: shape, guessKg: result.force[0] * Q_KG_PER_M2, videoT: video.currentTime });
async function askSolver(snap = snapshot()) {
  if (!engineUp || inflight.length >= 2) return;
  const me = { t0: performance.now(), guessKg: snap.guessKg, videoT: snap.videoT };
  inflight.push(me); solving = inflight[0];
  S.solves = (S.solves || 0) + 1;
  try {
    const r = await (await fetch(ENGINE + '/solve', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ body: { pose: snap.pose, body: snap.body }, learn: true }) })).json();
    if (r.solver) {
      const e = { solverKg: r.solver.push_kg_at_100kmh, modelKg: r.model_before.drag_area_m2 * Q_KG_PER_M2, errPct: r.model_before.actual_error_pct, boundPct: r.model_before.error_bound_pct, sureBefore: r.model_before.sure,
        solverSeconds: r.solver.seconds, waitSeconds: (performance.now() - me.t0) / 1000, runs: r.learned ? r.learned.runs_in_model : null, after: r.learned ? r.learned.on_these_runs_now[0] : null, videoT: me.videoT };
      ledger.unshift(e); S.ledger = ledger;
      model.set(await (await fetch(ENGINE + '/model')).json());
      $('runs').textContent = `the model has learned from ${model.nRuns.toLocaleString('en-US')} solver runs`;
      const row = document.createElement('div');
      row.innerHTML = `<b>solver ${e.solverKg.toFixed(1)} kg</b> · model had said ${e.modelKg.toFixed(1)} kg <i>(${e.errPct.toFixed(0)}% off in force)</i> · learned in ${e.solverSeconds.toFixed(0)} s`;
      $('ledger').prepend(row); while ($('ledger').children.length > 2) $('ledger').lastChild.remove();
    } else S.errors.push('solver: ' + JSON.stringify(r).slice(0, 200));
  } catch (e) { S.errors.push('solver: ' + e.message); }
  inflight.splice(inflight.indexOf(me), 1); solving = inflight[0] || null; lastSolveEnd = performance.now();
}


function layout() {
  const dpr = Math.min(window.devicePixelRatio || 1, dprCap);
  const w = Math.round(canvas.clientWidth * dpr), h = Math.round(canvas.clientHeight * dpr);
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  renderer.resize(w, h);
  const portrait = h > w, mirrorOn = !$('mirror').hidden || !$('start').hidden;
  // slide the twin clear of the mirror card
  renderer.cam.shift = portrait ? [0.0, mirrorOn ? -0.30 : -0.08] : [mirrorOn ? 0.20 : 0.0, -0.06];
  if (qs.has('embed')) { renderer.cam.shift = portrait ? [0.0, 0.10] : [0.30, -0.04]; if (portrait) renderer.cam.dist = 8.2; }
  renderer.cam.dist = portrait ? 6.9 : 6.4;
  renderer.cam.target = portrait ? [0.2, 0.0, 0.95] : [0.55, 0.0, 0.95];
}
addEventListener('resize', layout);

function check(now) {
  const t0 = performance.now();
  const X = featuresFromCapsules(caps);
  result = model.check(X);
  checkMs += (performance.now() - t0 - checkMs) * 0.1;
  const f = result.force;
  const k = smooth.init ? 0.35 : 1; smooth.init = true;
  smooth.kg += k * (f[0] * Q_KG_PER_M2 - smooth.kg); smooth.lift += k * (f[1] * Q_KG_PER_M2 - smooth.lift); smooth.side += k * (f[2] * Q_KG_PER_M2 - smooth.side);
  smooth.bound += k * (result.bound - smooth.bound);
  // "sure" needs the bound under the tolerance; a little hysteresis stops the label flickering at the edge
  const want = smooth.bound <= model.tol * (verdict === 'sure' ? 1.06 : 0.96) ? 'sure' : 'unsure';
  if (want !== verdict) { if (now - verdictSince > (want === 'unsure' ? 120 : 260) || verdict === 'idle') { verdict = want; verdictSince = now; if (want === 'unsure') unsureSince = now; } } else verdictSince = now;
  for (let p = 0; p < 10; p++) { const drag = result.parts[p * 3], area = X[NG + p * 5]; const target = Math.min(Math.max(drag / Math.max(area, 0.012) / 1.7, 0), 1); loads[p] += 0.3 * (target - loads[p]); }
  S.last = { t: video.currentTime, kg: f[0] * Q_KG_PER_M2, dragArea: f[0], lift: f[1], side: f[2], bound: result.bound, sure: result.sure, signals: result.signals, area: X[0] };
  if (qs.has('log') && haveBody) S.log.push({ t: S.mediaTime ?? video.currentTime, raw: S.raw, now: performance.now(), force: [f[0], f[1], f[2]], bound: result.bound, vis: S.vis, legW, pose: BONES.map((b) => (pose[b] || pose.l).map((v) => +v.toFixed(5))) });
}

let lastText = 0;
function hud(now) {
  if (now - lastText < 66) return; lastText = now;
  const sgn = (v) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(1);
  if (haveBody && result) {
    $('kg-num').textContent = smooth.kg.toFixed(0);
    $('lift').textContent = sgn(smooth.lift) + ' kg'; $('side').textContent = sgn(smooth.side) + ' kg';
    $('bound').textContent = '±' + (smooth.bound * 100).toFixed(smooth.bound < 0.1 ? 1 : 0) + '%';
    $('ms').textContent = checkMs.toFixed(1) + ' ms';
  }
  const chip = $('chip');
  // The chip is about the pose on screen now. The solver may still be working on an earlier pose; that gets its own line.
  const asking = solving && verdict === 'unsure';
  const cls = !haveBody ? 'idle' : asking ? 'solving' : verdict; S.solvingNow = !!solving; S.verdictNow = verdict;
  if (chip.className !== cls) chip.className = cls;
  $('chip-text').textContent = !haveBody ? 'waiting for a body' : asking ? `not sure · asking the real solver · ${((now - solving.t0) / 1000).toFixed(1)} s` : verdict === 'sure' ? 'answered by the model · sure' : engineUp ? 'not sure · this one needs the real solver' : 'not sure · the model would ask the real solver';
  const busy = solving && !asking ? `the solver is still checking an earlier pose · ${((now - solving.t0) / 1000).toFixed(1)} s` : '';
  if ($('busy').textContent !== busy) $('busy').textContent = busy;
  $('ask').hidden = !(engineUp && !autoAsk && haveBody && verdict === 'unsure' && !solving);
  const note = haveBody && legW < 0.5 ? 'legs out of view · standing legs assumed' : '';
  if ($('fine-a').dataset.note !== note) { $('fine-a').dataset.note = note; $('fine-a').textContent = (note ? note + ' · ' : '') + 'simple body posed from your joints · simulated tunnel · not a measurement of you'; }
}

// A small nose, drawn only (it is not part of the body the solver or the model sees), so you can tell which way the twin faces.
function withFace(c) {
  const t = unit(pose.t); let l = unit(pose.l); l = unit(sub(l, mul(t, dot(l, t))));
  const fwd = cross(l, unit(pose.h));
  const head = c[0].a, n = add(head, mul(unit(fwd), c[0].r * 0.98));
  return c.concat([{ a: n, b: add(n, [0, 0, -0.012]), r: 0.03, part: 0 }]);
}

// Before a camera or clip is chosen, the twin moves through recorded motion-capture poses (tai chi, then yoga), so the page
// shows what it does without asking for anything.
let attract = null, attractT = 0, source = 'attract', targetPose = null;
addEventListener('message', (e) => {                         // a parent page (the agent replay) can pose the twin
  if (!e.data || e.data.type !== 'wm-pose') return;
  source = 'spec'; targetPose = poseFromList(e.data.pose); shape = e.data.body || null; haveBody = true;
});
function attractPose(dt) {
  attractT += dt;
  const n = attract.frames.length, x = (attractT * attract.fps) % n, i = Math.floor(x), w0 = x - i, w = w0 * w0 * (3 - 2 * w0);
  const a = attract.frames[i].pose, b = attract.frames[(i + 1) % n].pose, p = {};
  BONES.forEach((bn, k) => { p[bn] = unit([a[k][0] + (b[k][0] - a[k][0]) * w, a[k][1] + (b[k][1] - a[k][1]) * w, a[k][2] + (b[k][2] - a[k][2]) * w]); });
  return p;
}

let last = performance.now(), fpsT = last, fpsN = 0;
function frame(now) {
  if (S.stopped) return;
  const dt = Math.min((now - last) / 1000, 0.05); last = now;
  const tr = tracker.ready ? tracker.update(video, now) : null;
  if (tr && tr.fresh) {
    pose = tr.pose; S.vis = tr.visibility; S.mediaTime = tr.mediaTime; S.raw = [tr.rawPose.uaL[2], tr.rawPose.uaR[2], tr.rawPose.t[0]];
    // When the camera cannot see the legs (someone at a desk), stand the twin on straight legs and say so.
    legW += (Math.min(Math.max((tr.visibility.legs - 0.35) / 0.3, 0), 1) - legW) * 0.2;
    if (legW < 0.999) for (const b of ['thL', 'shL', 'thR', 'shR']) pose[b] = unit(add(mul(pose[b], legW), mul(NEUTRAL[b], 1 - legW)));
    S.legW = legW;
    caps = bodyCapsules(pose, shape); haveBody = true; if (model) check(now);
  }
  else if (source === 'spec' && targetPose && model) {
    const k = 1 - Math.exp(-dt * 7);
    for (const b of BONES) { const a = pose[b] || pose.l, t = targetPose[b] || targetPose.l; pose[b] = unit([a[0] + (t[0] - a[0]) * k, a[1] + (t[1] - a[1]) * k, a[2] + (t[2] - a[2]) * k]); }
    caps = bodyCapsules(pose, shape); check(now);
  }
  else if (source === 'attract' && attract && model) { pose = attractPose(dt); caps = bodyCapsules(pose, shape); haveBody = true; check(now); }
  else if (model && !result) check(now);
  unsureLevel += ((verdict === 'unsure' && haveBody ? 1 : 0) - unsureLevel) * Math.min(dt * 8, 1);
  if (autoAsk && engineUp && haveBody && verdict === 'unsure' && source === 'video' && now - unsureSince > ASK_MS && result && result.bound > model.tol) {
    if (!inflight.length && now - lastSolveEnd > 1200) askSolver();
    else if (inflight.length === 1 && now - inflight[0].t0 > 1500) askSolver();                   // a second doubtful pose is sent while the first is being solved
  }
  if (flow.ok) { flow.setBody(caps, substeps); flow.step(substeps); flow.advect(dt, substeps / Math.max(dt, 1e-3)); }
  renderer.draw(withFace(caps), loads, unsureLevel, dt);
  hud(now);
  S.frames++; fpsN++;
  if (now - fpsT > 1000) { S.fps = (fpsN * 1000) / (now - fpsT); fpsN = 0; fpsT = now; S.inferMs = tracker.inferMs; S.checkMs = checkMs; S.verdict = verdict; }
  requestAnimationFrame(frame);
}

async function startVideo(src, { flip = false, loop = true, note = '' } = {}) {
  source = 'video'; haveBody = false; smooth.init = false;
  $('mirror').hidden = false; $('mirror').classList.toggle('flip', flip); $('mirror-note').textContent = note; $('start').hidden = true;
  layout();
  if (typeof src === 'string') { video.src = src; video.loop = loop && !qs.has('once'); video.onended = () => { S.ended = true; }; } else video.srcObject = src;
  await video.play().catch((e) => S.errors.push('video: ' + e.message));
  if (!tracker.ready) await tracker.init(qs.get('model') || 'full');
  S.tracker = { delegate: tracker.delegate };
}

async function boot() {
  layout();
  if (qs.get('m') === 'a') model = await Model.load('models/model_a.json');
  else {
    // With the engine service reachable (the solver behind the page), the model comes from it and can learn; otherwise a saved copy is used.
    if (ENGINE) try { const r = await fetch(ENGINE + '/model', { signal: AbortSignal.timeout(2500) }); if (r.ok) { model = new ModelB(await r.json()); engineUp = true; } } catch (e) { /* no engine */ }
    if (!model) model = await ModelB.load(qs.get('m') || 'models/model_b.json');
  }
  S.engine = engineUp; S.model = { version: model.version, runs: model.nRuns };
  $('runs').textContent = model.nRuns ? `the model has learned from ${model.nRuns.toLocaleString('en-US')} solver runs` + (engineUp ? '' : ' · solver not connected') : '';
  $('fine-b').textContent = flow.ok ? `air shown: live coarse simulation, ${flow.N.join(' × ')} cells, slowed down · force: learned model` : 'live air unavailable in this browser · force: learned model';
  requestAnimationFrame(frame);
  S.ready = true;
  if (qs.has('embed')) source = 'spec';
  if (!qs.has('video') && !qs.has('spec') && !qs.has('embed')) fetch('models/attract.json').then((r) => r.json()).then((j) => { attract = j; $('fine-a').textContent = 'recorded motion-capture poses (CMU) · simulated tunnel · not a measurement of anyone'; }).catch(() => {});
  if (qs.has('spec')) {                                    // a fixed body given in the address (used by the agent's render tool)
    const sp = JSON.parse(atob(qs.get('spec').replace(/-/g, '+').replace(/_/g, '/')));
    source = 'spec'; pose = poseFromList(sp.pose); shape = sp.body || null; caps = bodyCapsules(pose, shape); haveBody = true; result = null; smooth.init = false;
    document.body.classList.add('capture'); check(performance.now()); verdict = result.sure ? 'sure' : 'unsure';
  }
  if (qs.has('video')) { document.body.classList.add('capture'); await startVideo(qs.get('video'), { note: qs.get('note') || 'recorded clip' }); }
  $('cam-btn').onclick = async () => {
    // The camera is opened only here, by this click.
    try { const stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' }, audio: false }); await startVideo(stream, { flip: true, note: 'your camera · stays in this tab' }); }
    catch (e) { $('start').querySelector('p').textContent = 'The camera could not be opened (' + e.name + '). You can still watch the recorded demo.'; }
  };
  $('demo-btn').onclick = () => { $('start').hidden = true; layout(); };
  $('ask').onclick = () => askSolver();
  $('clip-btn').onclick = () => $('clip-file').click();
  $('clip-file').onchange = () => { const f = $('clip-file').files[0]; if (f) startVideo(URL.createObjectURL(f), { note: 'recorded clip · stays in this tab' }); };
}
boot().catch((e) => { S.errors.push(String(e.stack || e)); console.error(e); });

// ?report=1: after a while the page posts its own state (and a small picture of itself) to the local server, then stops.
// This is how a real Safari window is checked without scripting the browser.
if (qs.has('report')) setTimeout(() => {
  let image = null;
  try { image = canvas.toDataURL('image/jpeg', 0.7); } catch (e) { S.errors.push('snapshot: ' + e.message); }
  const body = { ua: navigator.userAgent, w: innerWidth, h: innerHeight, dpr: devicePixelRatio, gl: S.gl, flow: S.flow, fps: S.fps, frames: S.frames, tracker: S.tracker, inferMs: S.inferMs, checkMs: S.checkMs,
    last: S.last, verdict: S.verdict, vis: S.vis, errors: S.errors, videoTime: video.currentTime, image };
  fetch('/report', { method: 'POST', body: JSON.stringify(body) }).finally(() => { S.stopped = true; document.title = 'Wind Mirror · report sent, this tab can be closed'; });
}, Number(qs.get('report')) > 1 ? Number(qs.get('report')) * 1000 : 14000);
