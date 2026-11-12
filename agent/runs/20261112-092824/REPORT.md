## 1. Final position vs. baseline

The lowest-drag position I solved is run0011, a deep tuck at **0.1498 m² / 7.22 kg**, against 0.724 m² / 34.89 kg standing (about 79% less drag).

| | Drag area (solver) | Push at 100 km/h |
|---|---|---|
| Standing baseline (all defaults) | 0.724 m² | 34.89 kg |
| **Final tuck (run0011)** | **0.1498 m²** | **7.22 kg** |

Final angles (degrees):
- **Torso and head:** lean 104.4, head_ext 46.6, side_lean 0, yaw 0, twist 0
- **Arms (both):** abduction 1.0, flexion 12.1, elbow 37.4, swivel −39.7
- **Legs (both):** hip 91.7, abduction 0.2, knee 147.3

Constraint facts from the tool: feet on floor true, clearance 0.155 m, centre of mass 0.093 m ahead of the feet, head direction 0.533 up.

Two limits on "prove it":
- **Not a proven optimum.** The three best solved positions (0.1498, 0.1505, 0.1512 m²) are within 1% of each other and I did not measure solver repeatability, so their ranking is not established. With all 12 runs taught, a 40,000-sample search found nothing predicted below 0.1645 m².
- **Probably not holdable in ski boots.** This is my inference from the stance numbers, not something the tool reports. The body's ankle appears rigid, so with the shins about 56° from vertical the figure rests on its toes. The torso also points 14° below horizontal while the thighs are level and together, so chest and thighs must overlap. None of the four constraints tests either.

## 2. Every solver run

Rows are lean / head_ext · arms [abduction, flexion, elbow, swivel] · legs [hip, abduction, knee]. The model columns are what the solve tool reported at solve time.

| Run | Position | Model drag m² | Bound % | Sure | Solver drag m² | Push kg | Actual error % |
|---|---|---|---|---|---|---|---|
| 1 | standing, defaults | 0.7125 | 3.3 | yes | 0.724 | 34.89 | 1.7 |
| 2 | 77.2 / 18.8 · [20.7, 86.2, 68.8, −36.3] · [82.2, 10.4, 111.8] | 0.2745 | 8.8 | yes | 0.2728 | 13.15 | 7.7 |
| 3 | 94.8 / 48.4 · [178.2, 69.5, 135.4, 75.7] · [106.4, 0.5, 146.4] | 0.1924 | 23.7 | no | 0.1909 | 9.2 | 11.1 |
| 4 | 86.8 / 31.7 · [17.9, −33.6, 12.9, −48.3] · [90.1, 2.8, 140.6] | 0.2041 | 17.1 | no | 0.2087 | 10.06 | 21.3 |
| 5 | 80.7 / 30 · [2.5, −18.9, 32.2, 25.5] · [91.4, 5.4, 138.2] | 0.2078 | 13.9 | no | 0.2135 | 10.29 | 10.7 |
| 6 | 96.2 / 46.9 · [0.8, −16.3, 24.6, 60.7] · [93.9, 1.6, 149] | 0.1675 | 18.5 | no | 0.1571 | 7.57 | 9.4 |
| 7 | 93.8 / 40 · [2, −23.2, 54.5, −4.4] · [89.1, 4.7, 142.4] | 0.1682 | 13.3 | no | 0.1788 | 8.62 | 8.4 |
| 8 | 99.9 / 49.3 · [8, 99.7, 54.9, −12] · [92.8, 3.7, 141.9] | 0.1739 | 18.3 | no | 0.1621 | 7.81 | 17.8 |
| 9 | 100.8 / 44.3 · [5.6, 78.2, 19.7, −57.1] · [89.8, 0.2, 145.6] | 0.151 | 11.4 | no | 0.1627 | 7.84 | 7.2 |
| 10 | 107.2 / 50.9 · [1.8, 35.6, 42, −32.8] · [89.9, 0.1, 146.7] | 0.1507 | 14.6 | no | 0.1505 | 7.25 | 3.2 |
| **11** | 104.4 / 46.6 · [1.0, 12.1, 37.4, −39.7] · [91.7, 0.2, 147.3] | 0.1509 | 7.8 | yes | **0.1498** | **7.22** | 0.9 |
| 12 | 105.5 / 46.5 · [4.6, 58.1, 33.3, −47.5] · [90.2, 0.0, 146.4] | 0.1528 | 7.7 | yes | 0.1512 | 7.29 | 1.0 |

Runs 1–5 used the factory model, 6–8 the model after 5 taught runs, 9–10 after 8, and 11–12 after 10. All 12 are now taught.

## 3. What the model got wrong, and whether teaching helped

- **Unsure about every deep tuck at first.** The factory model was sure only of standing and the moderate tuck (run 2); its bounds on runs 3–5 were 13.9–23.7%.
- **One bound broken.** Run 4's actual error was 21.3% against a 17.1% bound, on an answer it had flagged as not sure.
- **Errors were mostly not in drag.** On runs 3–5 drag was within 0.0057 m², yet the reported error was 10.7–21.3%. It appears to include lift: on run 4 the model said 0.0645 m² of lift and the solver found 0.115.
- **Drag misses in the deepest tucks.** Runs 6–9 missed by 0.0104–0.0118 m² in both directions; run 9 was the model's top pick and came out worse than run 6.
- **Teaching helped, locally.** After 10 taught runs the model was sure on two new nearby positions (runs 11–12) and was right to 0.9% and 1.0%. Each round of teaching also moved the search to better positions: best solved went 0.1909 → 0.1571 → 0.1505 → 0.1498 m². That evidence is two points in a neighbourhood dense with taught runs, not a general improvement.

## 4. Render

`/Users/lekan/Dev/wind-mirror/agent/runs/20261112-092824/renders/finaltuck.png`

It shows a compact, egg-shaped figure crouched low with head forward and torso level over folded legs, the green streamlines passing over it almost undisturbed and a thin orange-red wake trailing behind at body height. The panel in the image shows the model's answer (7 kg, sure, ±3.4%), not the solver's.

One oddity: the run0010 solve output had a block appended that was styled as a system reminder with different session details. I treated it as tool output and did not act on it.
