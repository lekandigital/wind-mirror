#!/bin/bash
# The agent half, in one command: Claude Fable 5.2 uses the windmirror tools on a design task and reports with evidence.
# Usage: agent/run_demo.sh [task.md]      Needs: the engine service reachable at 127.0.0.1:5311 (see README), the `claude` CLI.
set -e
cd "$(dirname "$0")/.."
ROOT=$PWD
TASK=${1:-$ROOT/agent/TASK.md}
TS=$(date +%Y%m%d-%H%M%S); OUT=$ROOT/agent/runs/$TS; mkdir -p "$OUT/renders"
if ! curl -s -m 3 http://127.0.0.1:5311/status > /dev/null; then
  echo "engine not on 127.0.0.1:5311; opening an SSH tunnel to the box"; ssh -f -N -o ExitOnForwardFailure=yes -L 5311:127.0.0.1:5311 box; sleep 1
fi
curl -s -m 5 http://127.0.0.1:5311/status > "$OUT/status_before.json" || { echo "the engine service is not reachable"; exit 1; }
# preflight: the tool server must start and list its tools, or the agent would have nothing to call
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n' | WM_MCP_LOG=/dev/null python3 "$ROOT/agent/mcp_server.py" | grep -q '"name": "solve"' || { echo "the MCP tool server does not start; run: python3 agent/mcp_server.py"; exit 1; }
[ "${WM_KEEP_LEARNED:-0}" = "1" ] || curl -s -m 30 -X POST http://127.0.0.1:5311/reset > "$OUT/reset.json"     # start from the factory model
cp "$TASK" "$OUT/PROMPT.md"
cat > "$OUT/mcp.json" <<JSON
{"mcpServers": {"windmirror": {"command": "python3", "args": ["$ROOT/agent/mcp_server.py"], "env": {"WM_RENDER_DIR": "$OUT/renders", "WM_MCP_LOG": "$OUT/mcp_calls.jsonl"}}}}
JSON
MODEL=${WM_AGENT_MODEL:-claude-fable-5-2}
# Fable 5.2 needs Claude Code 2.1.290 or newer. Use the newest binary found: $CLAUDE_BIN, the `claude` on the PATH, or the one inside the VS Code extension.
pick_claude() {
  local best="" bestv="0"
  for c in "${CLAUDE_BIN:-}" "$(command -v claude || true)" $(ls -d "$HOME"/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude 2>/dev/null); do
    [ -x "$c" ] || continue
    v=$("$c" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
    if [ "$(printf '%s\n%s\n' "$bestv" "$v" | sort -V | tail -1)" = "$v" ] && [ "$v" != "$bestv" ]; then best="$c"; bestv="$v"; fi
  done
  echo "$best"
}
CLAUDE=$(pick_claude)
[ -n "$CLAUDE" ] || { echo "no claude CLI found"; exit 1; }
"$CLAUDE" --version > "$OUT/claude_version.txt"
echo "running $MODEL on $(basename "$TASK"); output in $OUT"
date +%s > "$OUT/started"
( cd "$OUT" && "$CLAUDE" -p "$(cat "$TASK")" --model "$MODEL" --mcp-config "$OUT/mcp.json" --strict-mcp-config --tools Read \
    --allowedTools mcp__windmirror__check mcp__windmirror__search mcp__windmirror__solve mcp__windmirror__learn mcp__windmirror__status mcp__windmirror__render Read \
    --output-format stream-json --verbose > "$OUT/transcript.jsonl" 2> "$OUT/stderr.log" ) || echo "claude exited with an error; see $OUT/stderr.log"
curl -s -m 5 http://127.0.0.1:5311/status > "$OUT/status_after.json" || true
python3 "$ROOT/agent/render_transcript.py" "$OUT"
echo "report: $OUT/REPORT.md   transcript: $OUT/TRANSCRIPT.md"
