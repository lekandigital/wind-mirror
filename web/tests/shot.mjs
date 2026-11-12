// Opens the demo in Chromium with a recorded clip and saves screenshots + state. No camera is ever requested.
// Usage: node tests/shot.mjs <outDir> [query] [width] [height] [seconds,comma,separated] [headed]
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
const require = createRequire('/Users/lekan/Dev/posepuppet/package.json');
const { chromium } = require('playwright');
const [out, query = 'video=private/fly_720.mp4', W = '1600', H = '900', times = '3,6,9', headed = ''] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ headless: !headed, channel: 'chrome', args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--autoplay-policy=no-user-gesture-required', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows'] });
const page = await (await browser.newContext({ viewport: { width: +W, height: +H }, deviceScaleFactor: 1 })).newPage();
const logs = [];
page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') logs.push(m.type() + ': ' + m.text().slice(0, 600)); });
page.on('pageerror', (e) => logs.push('pageerror: ' + String(e).slice(0, 1500)));
await page.goto(`http://127.0.0.1:5310/?${query}`);
let prev = 0;
for (const t of times.split(',').map(Number)) {
  await page.waitForTimeout((t - prev) * 1000); prev = t;
  await page.screenshot({ path: `${out}/t${String(t).padStart(2, '0')}.png` });
}
const state = await page.evaluate(() => { const s = window.__wm; return { frames: s.frames, fps: s.fps, gl: s.gl, flow: s.flow, tracker: s.tracker, inferMs: s.inferMs, checkMs: s.checkMs, last: s.last, vis: s.vis, verdict: s.verdict, errors: s.errors }; });
writeFileSync(`${out}/state.json`, JSON.stringify({ state, logs }, null, 1));
console.log(JSON.stringify({ state, logs }, null, 1).slice(0, 3000));
await browser.close();
