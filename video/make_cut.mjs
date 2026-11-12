// Builds the rough cut from the working demo: records each beat from the real pages (driven by recorded clips, never the
// camera), renders the cards, and joins them. Private: the takes contain the performer's June footage.
// Usage: node video/make_cut.mjs <16x9|9x16> [segment ...]      (no segment names = all, then assemble)
import { createRequire } from 'node:module';
import { mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync, readFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const require = createRequire('/Users/lekan/Dev/posepuppet/package.json');
const { chromium } = require('playwright');
const ROOT = fileURLToPath(new URL('..', import.meta.url));
const [fmt = '16x9', ...only] = process.argv.slice(2);
const [W, H] = fmt === '9x16' ? [1080, 1920] : [1920, 1080];
const work = join(ROOT, 'video/work', fmt); mkdirSync(work, { recursive: true }); mkdirSync(join(ROOT, 'video/out'), { recursive: true });
const BASE = 'http://127.0.0.1:5310';
const NUM = JSON.parse(readFileSync(join(ROOT, 'video/numbers.json')));
const ARGS = ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--autoplay-policy=no-user-gesture-required', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows'];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
const ff = (args) => execFileSync('ffmpeg', ['-y', '-loglevel', 'error', ...args]);
const ENC = ['-c:v', 'libx264', '-crf', '17', '-preset', 'slow', '-pix_fmt', 'yuv420p', '-r', '30', '-an'];

// A take: open a page, wait until it is live, optionally seek the clip, then record `dur` seconds while `drive` sets captions.
async function take(name, { url, start = null, dur, drive = null, ready = '() => window.__wm && window.__wm.last && window.__wm.frames > 300', settle = 1500, before = null }) {
  if (before) await before();
  const dir = mkdtempSync(join(tmpdir(), 'wm-cut-'));
  const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ARGS });
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, recordVideo: { dir, size: { width: W, height: H } } });
  const page = await ctx.newPage();
  const t0 = Date.now();
  await page.goto(BASE + url);
  await page.waitForFunction(ready, null, { timeout: 40000 });
  if (start !== null) { await page.evaluate((s) => { document.getElementById('video').currentTime = s; }, start); await sleep(settle); }
  const lead = (Date.now() - t0) / 1000, tStart = Date.now();
  const elapsed = () => (Date.now() - tStart) / 1000;
  const log = [];
  if (drive) await drive(page, elapsed, log); 
  const rest = dur - elapsed(); if (rest > 0) await sleep(rest * 1000);
  const state = await page.evaluate(() => { const w = window.__wm || {}; return { fps: w.fps, errors: w.errors, ledger: w.ledger, last: w.last, inferMs: w.inferMs, checkMs: w.checkMs, flow: w.flow, ms: w.ms, nSure: w.nSure, n: w.n }; });
  await ctx.close(); await browser.close();
  const webm = join(dir, readdirSync(dir).find((f) => f.endsWith('.webm')));
  const out = join(work, name + '.mp4');
  ff(['-ss', String(lead), '-i', webm, '-t', String(dur), ...ENC, out]);
  rmSync(dir, { recursive: true, force: true });
  writeFileSync(join(work, name + '.json'), JSON.stringify({ name, url, start, dur, lead, state, log }, null, 1));
  const EV = join(ROOT, 'evidence/results');
  if (name === 'b_loop' && fmt === '16x9' && state.ledger) writeFileSync(join(EV, 'loop_take.json'), JSON.stringify({ format: fmt, ledger: state.ledger, log }, null, 1));
  if (name === 'c_thousand' && fmt === '16x9' && state.ms) writeFileSync(join(EV, 'thousand.json'), JSON.stringify({ format: fmt, ms: state.ms, nSure: state.nSure, n: state.n }, null, 1));
  if (name === 'a_fly' && fmt === '16x9' && state.fps) writeFileSync(join(EV, 'page_perf.json'), JSON.stringify({ fps: state.fps, inferMs: state.inferMs, checkMs: state.checkMs, w: W, h: H, grid: state.flow.grid.join(' × ') }, null, 1));
  console.log(name, 'fps', state.fps && state.fps.toFixed(0), 'errors', (state.errors || []).length, log.length ? JSON.stringify(log) : '');
}
const cap = (page, text, top = false) => page.evaluate(([t, tp]) => window.__wm.caption(t, tp), [text, top]);

async function card(name, kind, payload, dur) {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const page = await (await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1 })).newPage();
  await page.goto(`file://${join(ROOT, 'video/cards.html')}?card=${kind}&n=${encodeURIComponent(JSON.stringify(payload))}`);
  await page.waitForFunction(() => window.__ready); await sleep(300);
  const png = join(work, name + '.png');
  await page.screenshot({ path: png }); await browser.close();
  ff(['-loop', '1', '-i', png, '-t', String(dur), ...ENC, join(work, name + '.mp4')]);
  console.log(name, 'card');
}

const SEG = {
  a_fly: () => take('a_fly', { url: '/?video=private/fly_720.mp4&noengine=1', start: 0.3, dur: 6.6, drive: async (page, el) => {
    await cap(page, 'Her webcam is a wind tunnel.'); await sleep(3000); await cap(page, ''); await sleep(350);
    await cap(page, 'A small learned model says how hard\nthe wind pushes. In under a millisecond.'); } }),
  b_loop: () => take('b_loop', { url: '/?video=private/puppet_720.mp4&askms=200', start: 12.2, dur: 25.4,
    before: async () => { await fetch('http://127.0.0.1:5311/reset', { method: 'POST' }); },
    drive: async (page, el, log) => {
      let stage = 0, tLedger = 0, n = 0, tAsk = 0, told = false;
      while (el() < 25.2) {
        const s = await page.evaluate(() => ({ solving: window.__wm.solvingNow, n: (window.__wm.ledger || []).length, v: window.__wm.verdictNow, t: document.getElementById('video').currentTime }));
        if (stage === 0 && el() > 1.4) { await cap(page, 'She turns side-on.'); stage = 1; }
        if (stage <= 1 && s.solving) { await cap(page, 'It is not sure about this one.\nIt says so, and asks the real solver.'); stage = 2; tAsk = el(); log.push(['asked', +el().toFixed(2), +s.t.toFixed(2)]); }
        if (stage === 2 && !told && el() - tAsk > 3.8) { await cap(page, 'The real flow solver is running: 3.67 million cells.\nAbout ten seconds to solve it and relearn.'); told = true; }
        if (stage === 2 && s.n >= 1) { await cap(page, 'The solver answers. The model learns it.'); stage = 3; tLedger = el(); log.push(['answered', +el().toFixed(2)]); }
        if (s.n > n) { n = s.n; log.push(['learned', n, +el().toFixed(2)]); }
        if (stage === 3 && el() - tLedger > 4.0) { await cap(page, ''); stage = 4; }
        if (stage === 4 && s.t > 14.9 && s.t < 18.3 && el() > 15) { await cap(page, 'The clip repeats: she turns again.\nNow it is sure.'); stage = 5; log.push(['second turn', +el().toFixed(2), s.v]); }
        if (stage === 5 && s.v !== 'sure') log.push(['NOT SURE on the second turn', +el().toFixed(2), +s.t.toFixed(2), s.v, s.solving]);
        await sleep(90);
      } } }),
  c_thousand: () => take('c_thousand', { url: `/thousand.html?delay=900&solver=${NUM.solver_seconds}`, dur: 5.2, ready: '() => window.__wm', settle: 0 }),
  d_agent: () => take('d_agent', { url: '/agent.html?run=models/agent_run.json&secs=10.0&lead=0.9', dur: 13.2, ready: '() => window.__wm', settle: 0 }),
  e_tuck: () => take('e_tuck', { url: `/?spec=${b64(NUM.final_pose)}&noengine=1&bare=1`, dur: 3.4, drive: async (page) => { await cap(page, `The position it found. Solver: ${NUM.final_kg_exact} kg.\nStanding: ${NUM.base_kg_exact} kg. Her turn to try it: to be filmed.`, true); } }),
  f_numbers: () => card('f_numbers', 'numbers', { rows: NUM.rows }, 3.9),
  g_end: () => card('g_end', 'end', {}, 3.2),
};
const order = ['a_fly', 'b_loop', 'c_thousand', 'd_agent', 'e_tuck', 'f_numbers', 'g_end'];
for (const s of (only.length ? only : order)) if (SEG[s]) await SEG[s]();
if (!only.length || only.includes('assemble')) {
  const list = join(work, 'list.txt');
  writeFileSync(list, order.filter((s) => existsSync(join(work, s + '.mp4'))).map((s) => `file '${join(work, s + '.mp4')}'`).join('\n'));
  const out = join(ROOT, 'video/out', `wind-mirror-roughcut-${fmt}.mp4`);
  ff(['-f', 'concat', '-safe', '0', '-i', list, ...ENC, '-movflags', '+faststart', out]);
  console.log('assembled', out, execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', out]).toString().trim(), 's');
}
