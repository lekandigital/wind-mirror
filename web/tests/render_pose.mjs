// Draws one fixed body in the tunnel (with the live air) and saves a PNG. Used by the agent's render tool.
// Usage: node tests/render_pose.mjs <out.png> <base64url JSON {pose, body}> [width] [height] [seconds]
import { createRequire } from 'node:module';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const require = createRequire('/Users/lekan/Dev/posepuppet/package.json');
const { chromium } = require('playwright');
const [out, spec, W = '1280', H = '800', secs = '6'] = process.argv.slice(2);
const up = () => new Promise((res) => { http.get('http://127.0.0.1:5310/', (r) => { r.resume(); res(true); }).on('error', () => res(false)); });
let server = null;
if (!(await up())) { server = spawn('node', [fileURLToPath(new URL('../serve.mjs', import.meta.url)), '5310'], { stdio: 'ignore' }); for (let i = 0; i < 30 && !(await up()); i++) await new Promise((r) => setTimeout(r, 100)); }
const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--disable-background-timer-throttling', '--disable-renderer-backgrounding'] });
const page = await (await browser.newContext({ viewport: { width: +W, height: +H }, deviceScaleFactor: 1 })).newPage();
await page.goto(`http://127.0.0.1:5310/?spec=${spec}`);
await page.waitForFunction(() => window.__wm && window.__wm.frames > 30, null, { timeout: 30000 });
await page.waitForTimeout(+secs * 1000);
await page.screenshot({ path: out });
const errors = await page.evaluate(() => window.__wm.errors);
await browser.close();
if (server) server.kill();
if (errors.length) { console.error(errors.join('\n')); process.exit(1); }
console.log(out);
