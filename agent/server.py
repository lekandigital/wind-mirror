"""The engine as a local web service (loopback only). The page and the MCP server both talk to this.

  GET  /status
  POST /check   {"bodies": [spec, ...]}
  POST /search  {"space": {...}, "n": 5000, "objective": "min_drag", "constraints": {...}, "top_k": 8, "seed": 0}
  POST /solve   {"body": spec, "learn": true}
  POST /learn   {"runs": [run, ...]}
  POST /reset
Usage: python agent/server.py <state_dir> [port]        (state_dir holds store.npz; solver runs learned are appended to learned.jsonl)
"""
import sys, os, json, time, threading, queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'engine', 'windtunnel')); sys.path.insert(0, HERE)
os.chdir(os.path.join(HERE, '..', 'engine', 'windtunnel'))
from engine import Engine
import search as SR

def main():
    global E, jobs, LOG, PENDING, state
    state = os.path.abspath(os.path.join(HERE, '..', sys.argv[1])) if not os.path.isabs(sys.argv[1]) else sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5311
    E = Engine(state)
    jobs = queue.Queue()
    PENDING = {}                                                    # solver runs not yet taught to the model, by id
    LOG = open(os.path.join(state, 'calls.jsonl'), 'a')


    def solver_loop():
        while True:
            spec, box, done = jobs.get()
            try:
                os.makedirs(os.path.join(state, 'fields'), exist_ok=True)
                run = E.solve(spec, fields_path=os.path.join(state, 'fields', f'{int(time.time() * 1000)}.npy'))
                box.append(run)
            except Exception as ex:                                   # noqa
                box.append(dict(error=repr(ex)))
            done.set()


    threading.Thread(target=solver_loop, daemon=True).start()


    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj, code=200):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b)))
            self.send_header('Access-Control-Allow-Origin', '*'); self.send_header('Access-Control-Allow-Headers', 'content-type')
            self.end_headers(); self.wfile.write(b)

        def do_OPTIONS(self):
            self._send({})

        def do_GET(self):
            if self.path.startswith('/status'):
                return self._send(dict(E.status(), solver_queue=jobs.qsize()))
            if self.path.startswith('/model'):
                from export_b import export
                with E.lock:
                    return self._send(export(E))
            self._send(dict(error='unknown path'), 404)

        def do_POST(self):
            t0 = time.time()
            try:
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0)) or 0) or b'{}')
                if self.path == '/check':
                    out = E.check(body['bodies'])
                elif self.path == '/search':
                    out = SR.search(E, body.get('space', {}), body.get('n', 2000), body.get('objective', 'min_drag'), body.get('constraints'), body.get('top_k', 8), body.get('seed', 0))
                elif self.path == '/solve':
                    box, done = [], threading.Event()
                    jobs.put((body['body'], box, done)); done.wait()
                    run = box[0]
                    out = dict(run=run)
                    if 'error' not in run:
                        out = dict(solver=dict(drag_area_m2=round(run['force'][0], 4), lift_area_m2=round(run['force'][1], 4), side_area_m2=round(run['force'][2], 4),
                                               push_kg_at_100kmh=round(run['force'][0] * 48.19, 2), seconds=run['seconds']),
                                   model_before=dict(drag_area_m2=round(run['model_before']['force'][0], 4), lift_area_m2=round(run['model_before']['force'][1], 4),
                                                     side_area_m2=round(run['model_before']['force'][2], 4), error_bound_pct=run['model_before']['error_bound_pct'],
                                                     sure=run['model_before']['sure'], actual_error_pct=run['model_before']['error_pct']), run=run)
                        rid = f'run{len(PENDING) + len(E.learned) + 1:04d}'
                        PENDING[rid] = run; out['run_id'] = rid
                        if body.get('learn', False):
                            out['learned'] = E.learn([PENDING.pop(rid)])
                        if not body.get('return_run', False):
                            out.pop('run')
                elif self.path == '/learn':
                    runs = list(body.get('runs', [])) + [PENDING.pop(i) for i in body.get('run_ids', []) if i in PENDING]
                    out = E.learn(runs) if runs else dict(error='no such runs (already learned, or unknown ids)')
                elif self.path == '/pose':
                    import bodies as B_, geom as G_
                    from engine import spec_pose
                    pose = spec_pose(body['body'])
                    out = dict(pose=B_.pose_to_list(pose), body=body['body'].get('body'))
                elif self.path == '/reset':
                    out = E.reset()
                else:
                    return self._send(dict(error='unknown path'), 404)
                out['seconds_total'] = round(time.time() - t0, 3)
                LOG.write(json.dumps(dict(t=round(t0, 2), path=self.path, seconds=out['seconds_total'], n=len(body.get('bodies', [])) or body.get('n'))) + '\n'); LOG.flush()
                self._send(out)
            except Exception as ex:                                   # noqa
                import traceback
                self._send(dict(error=repr(ex), trace=traceback.format_exc()[-1500:]), 500)


    print(f'engine ready: {E.status()}  on http://127.0.0.1:{port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()


if __name__ == '__main__':
    main()
