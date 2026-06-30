#!/usr/bin/env bash
# Sweep usd-core 25.11 (vulnerable) vs 26.5 (fixed), multithreaded.
# Each version gets its own throwaway venv. Run from the repo root.
set -u
RUNS="${RUNS:-8}"
export N="${N:-60}" COLLIDERS="${COLLIDERS:-40}" PYTHONFAULTHANDLER=1

sweep() {
  local ver="$1" venv
  venv="$(mktemp -d)/v"
  python3 -m venv "$venv" >/dev/null 2>&1
  "$venv/bin/pip" install --quiet "usd-core==$ver" >/dev/null 2>&1 || {
    echo "  (could not install usd-core==$ver)"; return; }
  local crash=0 clean=0
  for k in $(seq 1 "$RUNS"); do
    out="$("$venv/bin/python" repro.py 2>&1)"; ec=$?
    if echo "$out" | grep -qE 'Segmentation|double free|malloc|corrupt|tcache|Aborted' || [ $ec -ge 128 ]; then
      crash=$((crash+1))
    elif echo "$out" | grep -q COMPLETED; then
      clean=$((clean+1))
    fi
  done
  echo "usd-core $ver : crash=$crash clean=$clean / $RUNS  (N=$N COLLIDERS=$COLLIDERS)"
  rm -rf "$(dirname "$venv")"
}

echo "=== multithreaded ==="
sweep 25.11
sweep 26.5
echo "=== single-thread workaround on 25.11 ==="
venv="$(mktemp -d)/v"; python3 -m venv "$venv" >/dev/null 2>&1
"$venv/bin/pip" install --quiet 'usd-core==25.11' >/dev/null 2>&1
PXR_WORK_THREAD_LIMIT=1 "$venv/bin/python" repro.py
rm -rf "$(dirname "$venv")"
