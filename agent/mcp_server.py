#!/usr/bin/env python3
"""SoarLabs Wind Mirror as MCP tools (stdio). Standard library only. Forwards to the engine service (agent/server.py),
by default at http://127.0.0.1:5311 (set WM_ENGINE_URL to change).

Tools: check, search, solve, learn, status, render.
"""
import sys, os, json, urllib.request, subprocess, time, base64

URL = os.environ.get('WM_ENGINE_URL', 'http://127.0.0.1:5311')
HERE = os.path.dirname(os.path.abspath(__file__))

BODY_DOC = """A body is {"angles": {...}, "body": {...optional shape...}}. Angles are in degrees:
  lean       forward lean of the torso from upright (0 = standing straight, 90 = torso horizontal, head toward the wind)
  side_lean  sideways lean of the torso
  head_ext   how far the head is raised relative to the torso's lean (lean 80 with head_ext 50 looks ahead)
  yaw        heading: 0 faces the wind, 90 is side-on, 180 has the back to the wind
  twist      hips turned against the shoulders
  arms       [[left], [right]], each [abduction, flexion, elbow, swivel]: abduction 0 = arm down along the body, 90 = level, 180 = straight up;
             flexion sets which way the arm is raised (0 = out to the side, 90 = forward, negative = behind); elbow = bend; swivel = which way the forearm bends
  legs       [[left], [right]], each [hip, abduction, knee]: hip = thigh raised forward from straight down (90 = thigh level), abduction = thigh out to the side, knee = bend
Omitted angles take a relaxed standing value. The optional shape multiplies the reference body (1.75 m): g_torso, g_limb (girth), leg, arm, torso (lengths), sh, hip (widths), each roughly 0.85-1.3.
The body's lowest point always rests on the tunnel floor. The wind is 100 km/h; forces are given as areas in m^2 (force divided by the wind's dynamic pressure) and drag also as a push in kg."""

TOOLS = [
    dict(name='check', description='Fast learned answer for one or more bodies in the wind (about a millisecond each). Returns drag, lift and side force, an error bound in percent, and "sure" (true when the bound is at most 10%). An answer that is not sure should be treated as a guess: confirm it with solve. Also returns stance facts (feet on the floor, clearance of the rest of the body, whether the legs pass through the torso, centre of mass relative to the feet, head height) for design constraints. The ankles of the twin are rigid, so with tilted shins it stands on its toes.\n\n' + BODY_DOC,
         inputSchema=dict(type='object', properties=dict(bodies=dict(type='array', maxItems=64, items=dict(type='object'), description='bodies to check (at most 64 per call; use search for more)')), required=['bodies'])),
    dict(name='search', description='Screen thousands of body positions in one call. Samples n random positions from ranges of angles (or around a known position), checks them all with the learned model, applies constraints, and returns the best few by an objective: separately for answers the model is sure of and for answers it is not sure of. The unsure ones may be better or may be wrong; only solve can tell.\n\nspace example: {"lean": [40, 95], "head_ext": [0, 60], "arms": {"abduction": [0, 180], "flexion": [-40, 120], "elbow": [0, 140], "swivel": [-60, 120], "symmetric": true}, "legs": {"hip": [0, 110], "abduction": [0, 20], "knee": [0, 140], "symmetric": true}}. A single number fixes an angle. To refine near a position: {"around": {"angles": {...}, "sigma": 6}}.\nconstraints (all optional): feet_on_floor (bool), min_clearance_m (everything above the knees stays this far above the floor), max_legs_through_torso_m (how far thighs and shins may pass through the chest or head; a real body allows about 0.03), max_com_offset_m (centre of mass within this horizontal distance of the middle of the feet), min_head_height_m, min_head_dir_up (0-1; 1 = head upright).\nobjective: min_drag, max_drag, max_lift, min_lift, max_side, max_lift_to_drag.',
         inputSchema=dict(type='object', properties=dict(space=dict(type='object'), n=dict(type='integer', minimum=1, maximum=50000), objective=dict(type='string'), constraints=dict(type='object'),
                                                         top_k=dict(type='integer', minimum=1, maximum=20), seed=dict(type='integer')), required=['space'])),
    dict(name='solve', description='Run the real flow solver on one body (a 3D lattice-Boltzmann simulation with 3.67 million cells; several seconds on the GPU, longer if the GPU is shared). Returns the solver\'s forces, what the learned model had said and how wrong it was, and a run_id. Solver runs are the ground truth here and the scarce resource: spend them on answers that matter or that the model is not sure of.',
         inputSchema=dict(type='object', properties=dict(body=dict(type='object'), learn=dict(type='boolean', description='also teach the result to the model straight away (default false)')), required=['body'])),
    dict(name='learn', description='Teach solver runs to the model, by run_id. The model is refitted with those runs added and its error bound is re-calibrated; later check and search calls use the new model. Returns how the model now does on those runs.',
         inputSchema=dict(type='object', properties=dict(run_ids=dict(type='array', items=dict(type='string'))), required=['run_ids'])),
    dict(name='status', description='Model version, how many solver runs it has learned from, the tolerance and the calibration factor.', inputSchema=dict(type='object', properties={})),
    dict(name='render', description='Draw a body standing in the tunnel with the live air around it and save a PNG. Returns the file path. Use it to look at a design.',
         inputSchema=dict(type='object', properties=dict(body=dict(type='object'), name=dict(type='string', description='short file name, letters and digits')), required=['body'])),
]


def call(path, payload=None, timeout=900):
    req = urllib.request.Request(URL + path, data=None if payload is None else json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b'{"error": "engine error"}')
    except Exception as e:                                         # noqa
        return dict(error=f'cannot reach the engine at {URL}: {e!r}')


def slim_check(out):
    for r in out.get('results', []):
        r.pop('signals', None)
        r['part_drag_m2'] = {k: v for k, v in r['part_drag_m2'].items()}
    return out


def tool(name, a):
    if name == 'check':
        return slim_check(call('/check', dict(bodies=a['bodies'][:64])))
    if name == 'search':
        return call('/search', dict(space=a['space'], n=a.get('n', 2000), objective=a.get('objective', 'min_drag'), constraints=a.get('constraints'), top_k=a.get('top_k', 6), seed=a.get('seed', 0)))
    if name == 'solve':
        return call('/solve', dict(body=a['body'], learn=bool(a.get('learn', False))))
    if name == 'learn':
        return call('/learn', dict(run_ids=a['run_ids']))
    if name == 'status':
        return call('/status')
    if name == 'render':
        p = call('/pose', dict(body=a['body']))
        if 'error' in p:
            return p
        nm = ''.join(c for c in a.get('name', 'body') if c.isalnum() or c in '-_')[:40] or 'body'
        out_dir = os.environ.get('WM_RENDER_DIR', os.path.join(HERE, 'renders')); os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f'{nm}.png')
        q = base64.urlsafe_b64encode(json.dumps(dict(pose=p['pose'], body=p.get('body'))).encode()).decode()
        r = subprocess.run(['node', os.path.join(HERE, '..', 'web', 'tests', 'render_pose.mjs'), path, q], capture_output=True, text=True, timeout=120)
        return dict(image=path) if r.returncode == 0 else dict(error='render failed: ' + (r.stderr or r.stdout)[-400:])
    return dict(error='unknown tool ' + name)


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            m = json.loads(line)
        except Exception:
            continue
        mid, method, params = m.get('id'), m.get('method'), m.get('params') or {}
        if method == 'initialize':
            res = dict(protocolVersion=params.get('protocolVersion', '2025-06-18'), capabilities=dict(tools={}), serverInfo=dict(name='soarlabs-windmirror', version='0.2.0'),
                       instructions='A physics check for a human body in a 100 km/h wind: a fast learned answer with an error bound (check, search), the real flow solver (solve), and a way to teach the model what the solver found (learn).')
        elif method == 'tools/list':
            res = dict(tools=TOOLS)
        elif method == 'tools/call':
            t0 = time.time()
            try:
                out = tool(params.get('name'), params.get('arguments') or {})
            except Exception as e:                                 # noqa
                out = dict(error=repr(e))
            res = dict(content=[dict(type='text', text=json.dumps(out))], isError='error' in out)
            with open(os.environ.get('WM_MCP_LOG', os.path.join(HERE, 'mcp_calls.jsonl')), 'a') as f:
                f.write(json.dumps(dict(t=round(t0, 2), tool=params.get('name'), seconds=round(time.time() - t0, 3), args=params.get('arguments'), result=out)) + '\n')
        elif method == 'ping':
            res = {}
        elif mid is None:
            continue                                               # a notification
        else:
            sys.stdout.write(json.dumps(dict(jsonrpc='2.0', id=mid, error=dict(code=-32601, message='method not found'))) + '\n'); sys.stdout.flush(); continue
        if mid is not None:
            sys.stdout.write(json.dumps(dict(jsonrpc='2.0', id=mid, result=res)) + '\n'); sys.stdout.flush()


if __name__ == '__main__':
    main()
