# Wind Mirror

A person stands in front of a webcam. A simple twin of their body stands in a simulated wind tunnel, and a small learned
model says how hard a 100 km/h wind would push on it, about half a millisecond after it has the pose. Every answer comes
with an error bound. When the bound is over 10% the model says it is not sure, the body goes to a real 3D flow solver, and
the model learns the answer. The same engine is offered to an AI agent as tools: check, search, solve, learn.

It is a demonstration of one idea, the SoarLabs idea: a fast physics answer that is honest about when it is guessing, with
a solver behind it. It is not a measurement of anyone's drag (see "What it is not").

Status on 2026-11-12: private, nothing deployed. Built by Claude Fable 5.2 in Claude Code for Lekan Adeyeri.

## Run it in a few minutes

You need Node 18 or newer and a recent Chrome or Safari. Nothing to install: the body tracker is vendored.

```
cd web
node serve.mjs            # serves http://127.0.0.1:5310/ on this machine only
```

- `http://127.0.0.1:5310/` : the page. "Use my camera" opens the camera after that click and never before; "Just watch"
  plays recorded motion-capture poses.
- `http://127.0.0.1:5310/?video=<path under web/>` : drive it with a recorded clip instead of a camera.
- `http://127.0.0.1:5310/thousand.html` : a thousand random positions checked in the tab.
- `http://127.0.0.1:5310/agent.html` : replay of a real agent session.

In this mode the page answers and says when it is not sure. To let it ask the solver and learn, start the engine:

```
# on a machine with an NVIDIA GPU (about 6 s per solver run on an RTX 3090 Ti):
python3 -m venv .venv && .venv/bin/pip install numpy taichi==1.7.4
.venv/bin/python agent/server.py out/state_b 5311        # needs out/state_b/store.npz = models/model_b_store.npz

# or on an Apple Silicon Mac (the solver runs on Metal, about a minute a run):
WM_ARCH=metal .venv/bin/python agent/server.py out/state_b 5311
```

The page looks for the engine at `http://127.0.0.1:5311`. If the engine is on another machine, forward the port:
`ssh -f -N -L 5311:127.0.0.1:5311 <host>`. The engine binds to loopback only.

## The agent half, in one command

```
agent/run_demo.sh
```

This starts Claude Fable 5.2 in the Claude Code CLI with only the Wind Mirror tools and the task in `agent/TASK.md`
(design the lowest-drag position a downhill skier could hold, with a budget of 12 solver runs, and prove it). Everything
is saved in `agent/runs/<time>/`: the exact prompt, the raw and readable transcripts, every tool call with its result,
the agent's report, a summary with time, tokens and cost, and its render of the final position. It needs the engine
running (above) and Claude Code 2.1.290 or newer; the script picks the newest binary it can find.

To use the tools from your own agent, point any MCP client at `python3 agent/mcp_server.py` (standard library only).

| Tool | What it does | Cost |
|---|---|---|
| `check` | forces, error bound and "sure" for up to 64 bodies, plus stance facts for constraints | about a millisecond each |
| `search` | samples up to 50,000 positions from angle ranges, applies constraints, returns the best few (sure and not sure separately) | about a second per thousand |
| `solve` | the real flow solver on one body; returns its forces, what the model had said, and a run id | 6 s on the GPU box |
| `learn` | teaches solver runs to the model by id and re-calibrates its bound | about 4 s |
| `status`, `render` | model version and size; a picture of a body in the tunnel | |

## What is where

```
web/                the page: tracker, twin, model, live air (WebGL2), no build step
  src/body.js geom.js model_b.js    twin, wind's-eye features and the model, ported from Python (tests/parity*.mjs)
  src/flow.js render.js             a coarse 3D lattice-Boltzmann flow and its drawing
engine/windtunnel/  the solver (lbm.py), the twin (bodies.py), features (geom.py), model B (model_b.py, krige.py,
                    surrogate.py), the engine (engine.py), dataset tools, studies and fresh tests
engine/mocap/       CMU motion-capture conversion
agent/              engine service (server.py), MCP tools (mcp_server.py), runner, saved runs
models/             frozen models and their checksums
docs/               the two pre-registrations (rules written before the test data was evaluated)
evidence/           build.py -> EVIDENCE.html, and the result files behind every number
video/              the rough-cut pipeline (takes are recorded from the real pages)
```

## How it works, briefly

- **Twin.** 19 capsules posed from the tracker's 33 points (12 bone directions) and seven body-shape multipliers.
- **Solver.** A 3D lattice-Boltzmann flow solver written for this project (D3Q19, regularised collision, Smagorinsky
  sub-grid model, half-way bounce-back walls, forces by momentum exchange): 224 x 128 x 128 cells, 8,400 steps.
- **Model.** 67 numbers describing what the wind sees of the body (frontal area, which way the windward surface faces,
  each part's exposed area, thickness along the wind, and so on), a linear trend on them, and a local Gaussian-process
  correction from the 40 nearest solver runs. Adding a solver run is appending a point.
- **Doubt.** Six signals (how far the body is from the data in three senses, whether two sub-models agree, whether the
  per-part forces add up to the whole, and how wrong the model was on its nearest training runs) are combined into an
  error bound, calibrated on whole pose families the model was not trained on. "Sure" means the bound is at most 10%.
- **Loop.** Not sure -> solve -> learn -> re-calibrate. The page does this by itself for a held pose; an agent does it
  through the tools.

## What is measured

See `evidence/EVIDENCE.html` (rebuild with `python3 evidence/build.py`). In short, on solver runs the frozen model was
never trained on: within 3.3% of the solver's force on 424 tracked poses and 5.6% on 500 motion-capture poses; on the
motion-capture poses 3.4% of its "sure" answers were more than 10% wrong against 17% of its "not sure" answers, and on
614 random poses solved after the model was frozen, 1 of 454 against 68 of 160. The model answers in 0.5 ms (0.7 ms inside
the running page) where the solver takes 5.8 s.

## What it is not, and what is not built

- Not a measurement of a person. The twin is capsules; the solver was checked against textbook shapes, not against a
  wind tunnel with a person in it.
- The solver itself is not grid-converged: grids with 3.4 and 8 times as many cells give 4-14% less drag. The model's
  error is its distance from that solver.
- The stated error bound is too narrow on some footage (it held 84-85% of the time against a nominal 90%, and 57-63% on
  two clips). The sure / not sure label held on every group.
- The air on screen is a real but coarse simulation, there to be looked at. The force never comes from it.
- No hosted solver. The public page, as it stands, would answer and flag doubt but could not solve or learn unless the
  viewer runs the engine. A queue in front of a GPU, or a solver in the tab, is the next piece.
- One body-tracking model, one camera. Depth is guessed; legs out of view are replaced by straight legs, and the page
  says so.
- Learning is local: a solver run teaches the model that pose and its near neighbours, not a whole kind of movement.

## Development rules that matter

- The camera is never opened by code that runs on page load; tests drive the page with recorded clips
  (`web/tests/*.mjs`).
- `private/`, `web/private/`, `out/` and `video/work|out/` are not in git: they hold footage-derived files and results.
- Nothing here has been published or deployed.
