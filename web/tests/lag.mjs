// Measures how far the twin lags the tracker's raw reading (the smoothing filter's delay), from a logged clip.
// Usage: node tests/lag.mjs <outDir> name=path [...]
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
const require = createRequire('/Users/lekan/Dev/posepuppet/package.json');
const { chromium } = require('playwright');
const [out, ...clips] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--autoplay-policy=no-user-gesture-required', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows'] });
for (const c of clips) {
  const [name, path] = c.split('=');
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 })).newPage();
  await page.goto(`http://127.0.0.1:5310/?video=${encodeURIComponent(path)}&log=1&once=1&noengine`);
  await page.waitForFunction(() => window.__wm && window.__wm.ended, null, { timeout: 200000 });
  const r = await page.evaluate(() => ({ log: window.__wm.log.map((x) => ({ t: x.t, now: x.now, raw: x.raw, f: [x.pose[3][2], x.pose[5][2], x.pose[0][0]] })), fps: window.__wm.fps, inferMs: window.__wm.inferMs }));
  await page.context().close();
  // resample both signals to 240 Hz on the media clock, then find the shift that best aligns filtered to raw
  const L = r.log.filter((x) => x.raw);
  const res = {};
  ['left arm', 'right arm', 'torso lean'].forEach((label, k) => {
    const t0 = L[0].t, t1 = L[L.length - 1].t, hz = 240, n = Math.floor((t1 - t0) * hz);
    const samp = (get) => { const o = new Float64Array(n); let j = 0; for (let i = 0; i < n; i++) { const t = t0 + i / hz; while (j < L.length - 2 && L[j + 1].t < t) j++; const a = L[j], b = L[j + 1]; const w = Math.min(Math.max((t - a.t) / Math.max(b.t - a.t, 1e-6), 0), 1); o[i] = get(a) * (1 - w) + get(b) * w; } return o; };
    const raw = samp((x) => x.raw[k]), fil = samp((x) => x.f[k]);
    const d = (a) => { const o = new Float64Array(a.length - 1); for (let i = 0; i < o.length; i++) o[i] = a[i + 1] - a[i]; return o; };
    const dr = d(raw), df = d(fil);                                 // compare rates of change, so slow drifts do not dominate
    let best = 0, bestS = -Infinity;
    for (let s = 0; s <= 96; s++) { let acc = 0; for (let i = 0; i + s < df.length; i++) acc += dr[i] * df[i + s]; if (acc > bestS) { bestS = acc; best = s; } }
    let move = 0; for (let i = 0; i < dr.length; i++) move += Math.abs(dr[i]);
    res[label] = { lagMs: Math.round((best / hz) * 1000), movement: +move.toFixed(2) };
  });
  const frameGaps = []; for (let i = 1; i < L.length; i++) frameGaps.push(L[i].t - L[i - 1].t);
  frameGaps.sort((a, b) => a - b);
  const o = { name, trackedFrames: L.length, medianFrameGapMs: Math.round(frameGaps[frameGaps.length >> 1] * 1000), pageFps: +r.fps.toFixed(1), trackerMs: +r.inferMs.toFixed(1), filterLag: res };
  console.log(JSON.stringify(o));
  writeFileSync(`${out}/lag_${name}.json`, JSON.stringify(o, null, 1));
}
await browser.close();
