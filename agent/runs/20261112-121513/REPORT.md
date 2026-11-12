The lowest-drag position I could solver-verify is a forward-reaching tuck at **0.2482 m² (11.96 kg)**, against **0.724 m² (34.89 kg)** standing, about 66% less drag. It is the best of the 12 solved runs, not a proven global minimum: the five best solved positions span 0.2482–0.2564 m², and I had no run left to repeat a solve and measure solver noise.

## 1. Final position (run0009) and baseline

| | Final tuck | Standing (all defaults) |
|---|---|---|
| Solver drag area | 0.2482 m² | 0.724 m² |
| Solver push at 100 km/h | 11.96 kg | 34.89 kg |

Angles: lean 65.9, side_lean 0, head_ext 125.3, yaw 0, twist 0; arms (both) [127.3, 133.0, 61.5, -13.1]; legs (both) [69.0, 0.8, 119.3].

It meets every constraint, three of them narrowly:
- **Feet and clearance:** feet on the floor, rest of body 0.383 m clear.
- **Balance:** centre of mass 0.093 m ahead of the feet, 0.0 m to the side (limit 0.10).
- **Head:** head direction 0.509 up (limit 0.5).
- **Legs through torso:** 0.027 m (limit 0.03).

## 2. Every solver run

All positions have yaw, side_lean and twist at 0 and are left-right symmetric. Arms are [abduction, flexion, elbow, swivel]; legs are [hip, abduction, knee].

| Run | Position: lean / head_ext / arms / legs | Model m² | Bound | Sure | Solver m² (kg) | Actual error |
|---|---|---|---|---|---|---|
| run0001 | standing, defaults | 0.7141 | 4.0% | yes | 0.724 (34.89) | 1.4% |
| run0002 | 45.7 / 101.4 / [147.5, 119.7, 39.8, 4.6] / [88.1, 0, 147.1] | 0.2894 | 16.8% | no | 0.2948 (14.21) | 3.3% |
| run0003 | 68.4 / 12.4 / [0, -76.7, 144.8, 37] / [65.6, 0, 114.8] | 0.3137 | 8.5% | yes | 0.3473 (16.74) | 14.9% |
| run0004 | 76.0 / 23.8 / [110.8, 114.6, 4.9, 1.0] / [57.5, 1.0, 96.2] | 0.3169 | 12.1% | no | 0.313 (15.08) | 5.0% |
| run0005 | 54.0 / 113.6 / [128.1, 129.3, 32.2, 11.2] / [80.1, 1.1, 137.6] | 0.2801 | 9.0% | yes | 0.251 (12.1) | 11.9% |
| run0006 | 46.3 / 105.1 / [139.1, 105.2, 24.6, 9.0] / [88.9, 1.4, 146.9] | 0.2808 | 7.5% | yes | 0.2946 (14.2) | 8.0% |
| run0007 | 49.5 / 100.7 / [120.8, 128.0, 6.0, -4.6] / [83.9, 0.1, 144.4] | 0.281 | 9.2% | yes | 0.276 (13.3) | 1.8% |
| run0008 | 56.0 / 115.7 / [118.2, 135.9, 31.1, 3.7] / [80.0, 0.9, 137.2] | 0.2542 | 7.4% | yes | 0.2564 (12.36) | 7.0% |
| **run0009** | 65.9 / 125.3 / [127.3, 133.0, 61.5, -13.1] / [69.0, 0.8, 119.3] | 0.2552 | 11.2% | no | **0.2482 (11.96)** | 3.4% |
| run0010 | 54.7 / 113.4 / [109.7, 133.8, 53.2, -0.8] / [80.8, 2.0, 137.1] | 0.2576 | 8.3% | yes | 0.2557 (12.32) | 0.9% |
| run0011 | 67.4 / 126.0 / [123.9, 129.7, 48.9, -11.1] / [68.3, 0.6, 117.4] | 0.2441 | 6.0% | yes | 0.2541 (12.24) | 4.4% |
| run0012 | 73.4 / 132.8 / [113.3, 130.0, 55.1, -22.2] / [62.4, 0.6, 105.3] | 0.25 | 11.1% | no | 0.2557 (12.32) | 2.7% |

The "actual error" column is the tool's figure. It is larger than the drag-only difference in several rows (run0004: 0.3169 vs 0.313, reported 5.0%), so it seems to include lift as well.

## 3. What the model got wrong, and whether teaching helped

- **"Sure" was not reliable in the tuck region.** Three of the eight sure answers missed their own bound: run0003 (8.5% bound, 14.9% actual), run0005 (9.0%, 11.9%) and run0006 (7.5%, 8.0%).
- **"Unsure" was over-cautious.** All four unsure answers (bounds 11.1–16.8%) were within 2.7–5.0%.
- **The factory model's best sure answer was the wrong family.** It ranked an arms-behind tuck first among sure answers at 0.3137 m²; the solver gave 0.3473 m², worse than the unsure arms-forward crouches.
- **Teaching helped find the region.** Before teaching, none of 4,005 valid arms-forward crouches was sure. After teaching runs 2–4, that family became sure, and the next search led to run0005 at 0.251 m².
- **Teaching tightened later predictions.** After seven taught runs, the five remaining predictions were all inside their bounds (7.0, 3.4, 0.9, 4.4, 2.7%).
- **Teaching did not help rank the last few percent.** The model predicted run0011 better than run0009 (0.2441 m²) and the solver found it worse (0.2541 m²). With all 12 runs taught, it gives the final position as 0.2531 m² ±4.0%, sure, against the solver's 0.2482 m².

## 4. Render

`/Users/lekan/Dev/wind-mirror/agent/runs/20261112-121513/renders/finaltuck.png`

It shows a low crouch on the toes with the torso pitched forward, arms reaching ahead and down in front of the knees and the head lifted, with smooth streamlines over the back and a compact red turbulent wake behind the hips. The 12 kg on its panel is the model's answer, not the solver's.

One unrelated thing: a search result mid-run carried an appended block claiming the session context had changed to a different user email. It came from tool output, not from you, so I ignored it.
