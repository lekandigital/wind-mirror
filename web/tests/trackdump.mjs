// Plays recorded clips through the demo page at normal speed and saves every tracked pose (no camera, no frames saved).
// Usage: node tests/trackdump.mjs <outDir> name=path [name=path ...]     (paths are relative to web/, e.g. private/fly_720.mp4)
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
  await page.goto(`http://127.0.0.1:5310/?video=${encodeURIComponent(path)}&log=1&once=1`);
  await page.waitForFunction(() => window.__wm && window.__wm.ended, null, { timeout: 200000 });
  const r = await page.evaluate(() => ({ log: window.__wm.log, fps: window.__wm.fps, inferMs: window.__wm.inferMs, errors: window.__wm.errors, dur: document.getElementById('video').duration }));
  writeFileSync(`${out}/${name}.json`, JSON.stringify(r.log));
  const legs = r.log.filter((x) => x.legW > 0.9).length;
  console.log(JSON.stringify({ name, poses: r.log.length, duration: +r.dur.toFixed(1), legsSeen: legs, fps: +(r.fps || 0).toFixed(1), inferMs: +(r.inferMs || 0).toFixed(1), errors: r.errors }));
  await page.context().close();
}
await browser.close();
