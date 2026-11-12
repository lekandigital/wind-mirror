// Plays a clip through the page with the engine connected and reports every solver call the page made.
// Usage: node tests/loop.mjs <outDir> <query> <seconds> [shotTimes]
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
const require = createRequire('/Users/lekan/Dev/posepuppet/package.json');
const { chromium } = require('playwright');
const [out, query, secs = '40', shots = ''] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--autoplay-policy=no-user-gesture-required', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows'] });
const page = await (await browser.newContext({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1 })).newPage();
await page.goto(`http://127.0.0.1:5310/?${query}`);
let prev = 0;
for (const t of (shots ? shots.split(',').map(Number) : []).concat([+secs])) { await page.waitForTimeout((t - prev) * 1000); prev = t; await page.screenshot({ path: `${out}/t${String(t).padStart(3, '0')}.png` }); }
const r = await page.evaluate(() => ({ engine: window.__wm.engine, model: window.__wm.model, solves: window.__wm.solves, ledger: window.__wm.ledger, errors: window.__wm.errors, fps: window.__wm.fps }));
writeFileSync(`${out}/loop.json`, JSON.stringify(r, null, 1));
console.log(JSON.stringify(r, null, 1));
await browser.close();
