// Screenshot the built page in slices so it can be looked at. Usage: node shot.js <page.html> <out_prefix> [width]
const { chromium } = require('/Users/lekan/Dev/posepuppet/node_modules/playwright');
const SHELL = '/Users/lekan/Library/Caches/ms-playwright/chromium_headless_shell-1254/chrome-headless-shell-mac-arm64/chrome-headless-shell';
(async () => {
  const [page_, prefix, w] = process.argv.slice(2);
  const width = Number(w || 980);
  const browser = await chromium.launch({ headless: true, executablePath: SHELL });
  const page = await browser.newPage({ viewport: { width, height: 1300 }, deviceScaleFactor: 1 });
  await page.goto('file://' + page_);
  await page.evaluate(() => document.querySelectorAll('details').forEach((d) => (d.open = true)));
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  let i = 0;
  for (let y = 0; y < h; y += 1300) {
    await page.screenshot({ path: `${prefix}_${String(i).padStart(2, '0')}.jpg`, type: 'jpeg', quality: 70, clip: { x: 0, y, width, height: Math.min(1300, h - y) }, fullPage: true });
    i++;
  }
  console.log(JSON.stringify({ height: h, slices: i, horizontal_overflow: overflow }));
  await browser.close();
})();
