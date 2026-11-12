#!/bin/bash
# Runs solver queues one after another from a plan file, so jobs can be appended while it runs.
# Each line of the plan: <queue.jsonl> <out_dir> [limit]. Lines are run in order; when the end is reached the file is
# re-read every 30 s for new lines. Stop it with: touch ~/Dev/wind-mirror/out/v2/STOP (it stops after the current queue).
cd ~/Dev/wind-mirror/engine/windtunnel
PLAN=../../out/v2/plan.txt
n=0
while true; do
  [ -e ../../out/v2/STOP ] && { echo "$(date +%T) STOP file found, exiting"; exit 0; }
  total=$(wc -l < "$PLAN")
  if [ "$n" -lt "$total" ]; then
    n=$((n + 1))
    line=$(sed -n "${n}p" "$PLAN")
    [ -z "$line" ] && continue
    set -- $line
    echo "$(date +%T) plan line $n: $line"
    if [ -n "$3" ]; then ../../.venv/bin/python gen2.py "$1" "$2" --fields --limit "$3"; else ../../.venv/bin/python gen2.py "$1" "$2" --fields; fi
  else
    sleep 30
  fi
done
