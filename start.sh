#!/bin/bash
# Opens the Wind Mirror on this Mac: starts the page server, connects to the solver on the GPU box if it can, opens the page.
# Usage: ./start.sh            (add a clip: ./start.sh "?video=private/fly_720.mp4")
cd "$(dirname "$0")"
if ! curl -s -m 2 -o /dev/null http://127.0.0.1:5310/; then (cd web && nohup node serve.mjs > /tmp/windmirror-page.log 2>&1 &); sleep 1; fi
if ! curl -s -m 3 http://127.0.0.1:5311/status > /dev/null; then
  echo "connecting to the solver on the box..."
  ssh -o ConnectTimeout=5 box 'tmux has-session -t wm-engine 2>/dev/null || tmux new -d -s wm-engine "cd ~/Dev/wind-mirror && .venv/bin/python agent/server.py out/state_b 5311 > out/state_b/server.log 2>&1"' </dev/null 2>/dev/null
  ssh -o ConnectTimeout=5 -f -N -o ExitOnForwardFailure=yes -L 5311:127.0.0.1:5311 box 2>/dev/null
  for i in 1 2 3 4 5 6 7 8 9 10; do curl -s -m 2 http://127.0.0.1:5311/status > /dev/null && break; sleep 1.5; done
fi
if curl -s -m 3 http://127.0.0.1:5311/status > /dev/null; then echo "solver connected: the page can ask it and learn"; else echo "solver not reachable: the page will answer and say when it is not sure, but cannot ask the solver"; fi
URL="http://127.0.0.1:5310/$1"
echo "opening $URL"
open "$URL"
