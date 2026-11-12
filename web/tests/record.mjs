// Records the demo page (driven by a recorded clip, never the camera) to an mp4 via Playwright's video capture.
// Usage: node tests/record.mjs <out.mp4> <query> <width> <height> <startSeconds> <durationSeconds>
import { createRequire } from 'node:module';
import { mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
const require = createRequire('/Users/lekan/Dev/posepuppet/package.json');
const { chromium } = require('playwright');
const [out, query, W = '1600', H = '900', start = '0', dur = '20'] = process.argv.slice(2);
const dir = mkdtempSync(join(tmpdir(), 'wm-rec-'));
const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--autoplay-policy=no-user-gesture-required', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows'] });
const ctx = await browser.newContext({ viewport: { width: +W, height: +H }, deviceScaleFactor: 1, recordVideo: { dir, size: { width: +W, height: +H } } });
const page = await ctx.newPage();
const t0 = Date.now();
await page.goto(`http://127.0.0.1:5310/?${query}`);
await page.waitForFunction(() => window.__wm && window.__wm.last && window.__wm.frames > 60, null, { timeout: 30000 });
await page.evaluate((s) => { const v = document.getElementById('video'); v.currentTime = s; }, +start);
await page.waitForTimeout(900);                               // let the air settle after the jump
const lead = (Date.now() - t0) / 1000;
await page.waitForTimeout(+dur * 1000);
const state = await page.evaluate(() => ({ fps: window.__wm.fps, errors: window.__wm.errors }));
await ctx.close(); await browser.close();
const webm = join(dir, readdirSync(dir).find((f) => f.endsWith('.webm')));
execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-ss', String(lead), '-i', webm, '-t', dur, '-c:v', 'libx264', '-crf', '17', '-preset', 'slow', '-pix_fmt', 'yuv420p', '-r', '30', '-movflags', '+faststart', out]);
rmSync(dir, { recursive: true, force: true });
console.log(JSON.stringify({ out, lead, state }));
