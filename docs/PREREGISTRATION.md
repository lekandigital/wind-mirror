# Fresh test of the doubt gate: rules written before the data was looked at

Written 2026-11-12, 07:58 US Eastern, by Claude Fable 5.2, and committed together with the frozen model file before any
dataset-v2 result was evaluated against any model.

## Why this exists

On the pitch night (2026-11-12, about 04:10 ET) the first gate rule let 3 of 5 side-on frames through as "sure" while they were
17-28% wrong. A stricter rule fixed those five, but it was written after seeing the failure, so it proved nothing.
This file fixes the model, the gate and the pass/fail criteria first, and tests them on runs made afterwards.

## What is frozen

`models/model_a.npz`, sha256 `95b14d3aadca79db6c14836032fd41c93b86716e09270e628dcc088629d2d52f`.

- Trained on the 351 pitch-night solver runs of random poses only (`out/pitch/poses_v1.jsonl`): one body shape, seven pose
  families (stand, tuck, wide, back, inverted, prone, side). None of the performer's clips. No dataset-v2 run.
- Inputs: 67 geometric "wind's-eye" features (`engine/windtunnel/geom.py`). Model: ridge regression, mirror-augmented
  (`engine/windtunnel/surrogate.py`). Outputs: drag, lift and side force areas, and per-part forces.
- Doubt: four signals (leverage, distance to the 5 nearest training bodies, disagreement between a global-features model
  and the full model, parts-must-add-up check) combined as sigma = exp(w . log signals + w0), and a conformal factor q,
  both fitted on leave-one-family-out scores of the same 351 runs. Bound = q x sigma. alpha = 0.10.
- Verdict: "sure" when the bound is at most 10% of the force (the tolerance); otherwise "ask the solver".
- Error measure: size of the force-vector error (drag, lift, side together) divided by the size of the solver's force vector.

## What it will be tested on

Solver runs it has never seen, made after the freeze with the same solver settings:

1. `out/v2/synth_a/runs.jsonl`: up to 3,600 new random poses in eleven families. Four are new kinds of pose (squat, stride,
   bend, twist), one is a new never-train family (supine), and "turn" covers every heading. About 55% of runs use a body
   shape the model has never seen (girth and limb proportions varied); the hips can turn against the shoulders, which no
   training run had.
2. Poses tracked from recorded webcam footage that took no part in training (to be queued).
3. Poses from the CMU motion-capture database (to be queued).

## What will be reported, whatever it shows

For every family and for the reference body and other body shapes separately:

- mean force error;
- share of answers labelled "sure";
- **false-sure**: the number of "sure" answers that were more than 10% wrong, and that number as a share of "sure" answers;
- **coverage**: how often the solver's force fell within the stated bound (nominal: 90%).

## Pass and fail, decided now

- The gate **passes** on a group if at most 10% of its "sure" answers are more than 10% wrong, and coverage is at least 80%.
- The gate **fails** on a group if more than 20% of its "sure" answers are more than 10% wrong, or coverage is below 70%.
- Anything between is reported as "marginal".
- A group with fewer than 20 "sure" answers gets no verdict on false-sure, only the counts.

## What I had already seen when this was written

- Study 1 and study 2 results on pitch-night data (in the repository log), including the performer's three clips, which
  therefore do not count as fresh.
- About ten lines of the dataset-v2 generator's progress log (pose family, frontal area and solver forces for single runs).
  No model was evaluated on them.

## What happens afterwards

The shipped model will be retrained on more data, and its gate re-calibrated, with the same procedure. Its numbers are
reported separately from this test and labelled as cross-validated, not fresh.
