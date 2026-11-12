// Checks that the browser code gives the same capsules, features, forces and doubt as the Python that made the training data.
import { readFileSync } from 'node:fs';
import { poseFromList, bodyCapsules } from '../src/body.js';
import { featuresFromCapsules, NAMES } from '../src/geom.js';
import { Model } from '../src/model.js';

const cases = JSON.parse(readFileSync(new URL('./parity_cases.json', import.meta.url)));
const model = new Model(JSON.parse(readFileSync(new URL('../models/model_a.json', import.meta.url))));
let worstCap = 0, worstFeat = 0, worstFeatName = '', worstForce = 0, worstBound = 0, sureMismatch = 0, t = 0;
for (const c of cases) {
  const pose = poseFromList(c.pose);
  if (!c.has_lh) delete pose.lh;
  const caps = bodyCapsules(pose, c.body);
  caps.forEach((k, i) => { for (let d = 0; d < 3; d++) worstCap = Math.max(worstCap, Math.abs(k.a[d] - c.capsules[i].a[d]), Math.abs(k.b[d] - c.capsules[i].b[d])); });
  const t0 = performance.now();
  const X = featuresFromCapsules(caps);
  const r = model.check(X);
  t += performance.now() - t0;
  X.forEach((v, i) => { const d = Math.abs(v - c.features[i]); if (d > worstFeat) { worstFeat = d; worstFeatName = NAMES[i]; } });
  for (let d = 0; d < 3; d++) worstForce = Math.max(worstForce, Math.abs(r.force[d] - c.force[d]));
  worstBound = Math.max(worstBound, Math.abs(r.bound - c.bound) / c.bound);
  if (r.sure !== c.sure) sureMismatch++;
}
console.log(JSON.stringify({ cases: cases.length, worstCapsuleDiff_m: worstCap, worstFeatureDiff: worstFeat, worstFeatureName: worstFeatName, worstForceDiff_m2: worstForce, worstBoundRelDiff: worstBound, sureMismatch, msPerPose: t / cases.length }));
if (worstCap > 1e-9 || worstFeat > 2e-3 || worstForce > 2e-3 || sureMismatch > 0) { console.error('PARITY FAILED'); process.exit(1); }
