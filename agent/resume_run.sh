#!/bin/bash
# Continue an interrupted agent session in place (same conversation, same tools, same engine state).
# Usage: agent/resume_run.sh <run_dir> "<message>"
set -e
cd "$(dirname "$0")/.."
ROOT=$PWD; OUT=$(cd "$1" && pwd); MSG=$2
SID=$(python3 -c "
import json,sys
for l in open('$OUT/transcript.jsonl'):
    r=json.loads(l)
    if r.get('type')=='system' and r.get('subtype')=='init': print(r['session_id']); break")
CLAUDE=$(ls -d "$HOME"/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude 2>/dev/null | sort -V | tail -1)
[ -x "$CLAUDE" ] || CLAUDE=$(command -v claude)
N=$(ls "$OUT"/transcript_resume*.jsonl 2>/dev/null | wc -l | tr -d ' '); N=$((N + 1))
printf '%s\n' "$MSG" > "$OUT/RESUME_PROMPT_$N.md"; date +%s > "$OUT/resumed_$N"
echo "resuming session $SID (part $((N + 1))) with $("$CLAUDE" --version)"
( cd "$OUT" && "$CLAUDE" -p "$MSG" --resume "$SID" --model "${WM_AGENT_MODEL:-claude-fable-5-2}" --mcp-config "$OUT/mcp.json" --strict-mcp-config --tools Read \
    --allowedTools mcp__windmirror__check mcp__windmirror__search mcp__windmirror__solve mcp__windmirror__learn mcp__windmirror__status mcp__windmirror__render Read \
    --output-format stream-json --verbose > "$OUT/transcript_resume$N.jsonl" 2>> "$OUT/stderr.log" ) || echo "claude exited with an error"
curl -s -m 5 http://127.0.0.1:5311/status > "$OUT/status_after.json" || true
python3 "$ROOT/agent/render_transcript.py" "$OUT"
