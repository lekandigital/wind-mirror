# Fresh test of model B: rules written before the sealed data was evaluated

Written 2026-11-12, 12:10 US Eastern, by Claude Fable 5.2, and committed with the frozen model before any sealed run was
evaluated against any model.

## What is frozen

`models/model_b_store.npz`, sha256 `22622ce2aa575f0089aab6eae0460a619205252485e1e5a1e108a95f3ad898eb`
(built by `engine/windtunnel/build_b.py`; its printed calibration table is in `models/model_b_info.json` and the build log).

- Model: linear trend on the 67 wind's-eye features plus a local Gaussian-process correction from the 40 nearest solver
  runs (length scale 5, noise 0.3), mirror-augmented. Six doubt signals; bound = q x sqrt(sigma^2 + floor^2), q = 1.631,
  floor = 0.015; "sure" when the bound is at most 10% of the force. alpha = 0.10.
- Factory training set: 1,969 solver runs = pitch-night random poses, 817 dataset-v2 random poses, 715 CMU motion-capture
  poses chosen for diversity, and poses tracked from five recorded clips (DEV: fly, puppet, fx_crouch_stand, fx_lean_lr,
  fx_arms_tpose). Never trained on: lying and upside-down bodies (prone, supine, inverted, CMU low and inverted poses) and
  the single-move windows of the DEV clips.
- Calibration: leave-one-family-out, five-fold, "a new family after 2/5/10 solver runs", and the DEV single moves.

## Sealed test sets (none has been evaluated against any model)

1. `out/v2/cmu_rand/runs.jsonl`: 500 poses drawn uniformly at random from the CMU motion-capture database (disjoint from
   the diversity sample), each with a random heading and, half the time, a random body shape. Solver runs finished
   at 11:57 ET today.
2. Tracked poses from recorded clips that took no part in anything (SEALED: row, fx_fullbody, fx_lean_fb, fx_seated,
   fx_rowing_slow, fx_arms, fx_torso): about 60 evenly spaced poses per clip (`queue_trk_sealed_uniform.jsonl`, 424 poses).
   Their solver runs have not been made yet. Six of the seven clips show a different person from the DEV clips' performer.
3. Two single moves from sealed clips, 8 poses a second (`queue_trk_sealed_dense.jsonl`, 74 poses: leaning forward and
   back; a seated stretch), for the learn test.
4. The rest of the dataset-v2 random queue (seeds after the first 817), when its solver runs exist.

## What will be reported, whatever it shows

Per test set and per group (pose category, posture, clip, reference body or other body shape): mean force error; share
labelled "sure"; false-sure count and share of sure answers; coverage of the stated bound (nominal 90%).

Learn test: for each sealed single move, the factory model is taught k = 2 and k = 5 solver runs spread over the move and
re-calibrated exactly as the engine does it (`Engine.learn`); error, sure count, false-sure and coverage are reported on
the remaining poses of that move for k = 0, 2, 5.

## Pass and fail, decided now

- **Pass** on a group: at most 10% of its "sure" answers are more than 10% wrong, and coverage is at least 80%.
- **Fail**: more than 20% of "sure" answers more than 10% wrong, or coverage below 70%. Anything between is "marginal".
- Groups with fewer than 20 "sure" answers get counts only.
- Learn test passes if, at k = 5, the error on the rest of the move is not higher than at k = 0 and at most 10% of
  "sure" answers are more than 10% wrong.

## Known before the test

- Model A's interim fresh test (first 772 dataset-v2 runs) failed on lying head-first poses; model B's two extra doubt
  signals were added because of that. Those 772 runs are now in model B's training data, so they are not fresh for B.
- On development data the bound under-covers for upside-down bodies (62%) and for one DEV clip (45%) while labelling no
  wrong answer "sure" there. I expect similar under-coverage on some sealed groups.
- One of 2,935 solver runs made today returned non-finite forces (the solver diverged) and is excluded from all sets.

## Erratum, added after the test (2026-11-12, 14:12 ET)

The line above that says six of the seven sealed clips "show a different person from the DEV clips' performer" is true
but misleading. Both people appear on both sides: the DEV clips are two of the performer's and three of the second
person's; the SEALED clips are one of the performer's and six of the second person's. The sealed tracked set therefore
tests movements the model has not seen, not people it has not seen. Nothing else in this file was changed.
