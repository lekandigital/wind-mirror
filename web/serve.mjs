// Tiny static server for the demo: loopback only, byte-range support (needed to seek recorded clips).
// Usage: node serve.mjs [port]
import http from 'node:http';
import { createReadStream, statSync, realpathSync, mkdirSync, writeFileSync } from 'node:fs';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('.', import.meta.url));
const port = Number(process.argv[2] || 5310);
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.wasm': 'application/wasm',
  '.mp4': 'video/mp4', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.task': 'application/octet-stream', '.bin': 'application/octet-stream', '.webm': 'video/webm' };
http.createServer((req, res) => {
  if (req.method === 'POST' && req.url.startsWith('/report')) {      // a page run with ?report=1 posts its own state here (used to check real Safari)
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => {
      try {
        const j = JSON.parse(Buffer.concat(chunks).toString());
        const dir = join(root, 'tests', 'reports'); mkdirSync(dir, { recursive: true });
        const name = `${Date.now()}`;
        if (j.image) { writeFileSync(join(dir, name + '.jpg'), Buffer.from(j.image.split(',')[1], 'base64')); delete j.image; }
        writeFileSync(join(dir, name + '.json'), JSON.stringify(j, null, 1));
        res.writeHead(200); res.end('ok');
      } catch (e) { res.writeHead(400); res.end('bad report'); }
    });
    return;
  }
  try {
    let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    if (p.endsWith('/')) p += 'index.html';
    let file = join(root, normalize(p));
    if (!file.startsWith(root)) { res.writeHead(403); return res.end(); }
    file = realpathSync(file);                               // follow links to private clips kept outside the repo
    const st = statSync(file);
    const head = { 'Content-Type': TYPES[extname(file)] || 'application/octet-stream', 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store' };
    const m = /bytes=(\d*)-(\d*)/.exec(req.headers.range || '');
    if (m) {
      const start = m[1] ? Number(m[1]) : 0, end = m[2] ? Math.min(Number(m[2]), st.size - 1) : st.size - 1;
      res.writeHead(206, { ...head, 'Content-Range': `bytes ${start}-${end}/${st.size}`, 'Content-Length': end - start + 1 });
      createReadStream(file, { start, end }).pipe(res);
    } else { res.writeHead(200, { ...head, 'Content-Length': st.size }); createReadStream(file).pipe(res); }
  } catch (e) { res.writeHead(404); res.end('not found'); }
}).listen(port, '127.0.0.1', () => console.log(`Wind Mirror on http://127.0.0.1:${port}/`));
