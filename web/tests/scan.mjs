// Runs a saved model over logged poses of recorded clips and prints where it is not sure.
// Usage: node tests/scan.mjs <model.json> <tracked_dir> [clip ...]
import { readFileSync, readdirSync } from 'node:fs';
import { poseFromList, bodyCapsules } from '../src/body.js';
import { featuresFromCapsules } from '../src/geom.js';
import { ModelB } from '../src/model_b.js';
const [mpath, dir, ...only] = process.argv.slice(2);
const model = new ModelB(JSON.parse(readFileSync(mpath)));
for (const f of readdirSync(dir).filter((x) => x.endsWith('.json')).sort()) {
  const name = f.replace('.json', '');
  if (only.length && !only.includes(name)) continue;
  const L = JSON.parse(readFileSync(`${dir}/${f}`));
  let nUnsure = 0; const segs = []; let cur = null; let kgMin = 1e9, kgMax = -1e9;
  for (let i = 0; i < L.length; i += 2) {
    const r = model.check(featuresFromCapsules(bodyCapsules(poseFromList(L[i].pose), null)));
    const kg = r.force[0] * 48.19; kgMin = Math.min(kgMin, kg); kgMax = Math.max(kgMax, kg);
    if (!r.sure) { nUnsure++; if (cur && L[i].t - cur.b < 0.25) { cur.b = L[i].t; cur.max = Math.max(cur.max, r.bound); } else { cur = { a: L[i].t, b: L[i].t, max: r.bound }; segs.push(cur); } }
  }
  const long = segs.filter((s) => s.b - s.a >= 0.3).map((s) => `${s.a.toFixed(1)}-${s.b.toFixed(1)}s (±${(s.max * 100).toFixed(0)}%)`);
  console.log(`${name.padEnd(16)} poses ${String(Math.ceil(L.length / 2)).padStart(5)}  unsure ${(100 * nUnsure / Math.ceil(L.length / 2)).toFixed(0).padStart(3)}%  push ${kgMin.toFixed(0)}-${kgMax.toFixed(0)} kg  unsure stretches: ${long.join(', ') || 'none'}`);
}
