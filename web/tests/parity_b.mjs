// Checks the browser's model B against the Python engine on 80 bodies.
import { readFileSync } from 'node:fs';
import { ModelB } from '../src/model_b.js';
import { poseFromList, bodyCapsules } from '../src/body.js';
import { featuresFromCapsules } from '../src/geom.js';
const model = new ModelB(JSON.parse(readFileSync(new URL('../models/model_b.json', import.meta.url))));
const cases = JSON.parse(readFileSync(new URL('./parity_b_cases.json', import.meta.url)));
let wf = 0, wb = 0, ws = 0, mism = 0, t = 0, e2eF = 0, e2eB = 0, e2eM = 0, e2eN = 0;
for (const c of cases) {
  const t0 = performance.now(); const r = model.check(Float64Array.from(c.features)); t += performance.now() - t0;
  for (let d = 0; d < 3; d++) wf = Math.max(wf, Math.abs(r.force[d] - c.force[d]));
  wb = Math.max(wb, Math.abs(r.bound - c.bound) / c.bound);
  r.signals.forEach((v, i) => { ws = Math.max(ws, Math.abs(v - c.signals[i]) / (Math.abs(c.signals[i]) + 1e-6)); });
  if (r.sure !== c.sure) mism++;
  if (c.pose) {                                                // end to end: pose -> browser geometry -> browser model
    const pose = poseFromList(c.pose); if (!c.has_lh) delete pose.lh;
    const q = model.check(featuresFromCapsules(bodyCapsules(pose, c.body)));
    for (let d = 0; d < 3; d++) e2eF = Math.max(e2eF, Math.abs(q.force[d] - c.force[d]));
    e2eB = Math.max(e2eB, Math.abs(q.bound - c.bound) / c.bound); if (q.sure !== c.sure) e2eM++; e2eN++;
  }
}
console.log(JSON.stringify({ cases: cases.length, runsInStore: model.N, worstForceDiff_m2: wf, worstBoundRelDiff: wb, worstSignalRelDiff: ws, sureMismatch: mism, msPerCheck: t / cases.length, endToEnd: { cases: e2eN, worstForceDiff_m2: e2eF, worstBoundRelDiff: e2eB, sureMismatch: e2eM } }));
if (wf > 2e-3 || wb > 0.02 || mism > 0 || e2eF > 2e-3 || e2eB > 0.02 || e2eM > 0) { console.error('PARITY FAILED'); process.exit(1); }
