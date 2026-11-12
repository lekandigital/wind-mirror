// Times one full answer in JavaScript (twin geometry + wind's-eye features + model B with its bound) on logged poses.
import { readFileSync } from 'node:fs';
import { poseFromList, bodyCapsules } from '../src/body.js';
import { featuresFromCapsules } from '../src/geom.js';
import { ModelB } from '../src/model_b.js';
const model = new ModelB(JSON.parse(readFileSync(new URL('../models/model_b.json', import.meta.url))));
const L = JSON.parse(readFileSync(process.argv[2])).filter((_, i) => i % 3 === 0).slice(0, 400);
const run = () => { const tf = [], tm = []; for (const r of L) { const a = performance.now(); const X = featuresFromCapsules(bodyCapsules(poseFromList(r.pose), null)); const b = performance.now(); model.check(X); tf.push(b - a); tm.push(performance.now() - b); } return [tf, tm]; };
run(); run();
const [tf, tm] = run();
const med = (a) => [...a].sort((x, y) => x - y)[a.length >> 1], p95 = (a) => [...a].sort((x, y) => x - y)[Math.floor(a.length * 0.95)];
console.log(JSON.stringify({ poses: L.length, runsInStore: model.N / 2, geometryAndFeaturesMs: { median: +med(tf).toFixed(3), p95: +p95(tf).toFixed(3) }, modelAndBoundMs: { median: +med(tm).toFixed(3), p95: +p95(tm).toFixed(3) }, totalMedianMs: +(med(tf) + med(tm)).toFixed(3), node: process.version }));
