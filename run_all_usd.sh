#!/usr/bin/env bash
#
# Run the OpenUSD PR #4002 regression tests against several USD runtimes and
# print a summary table. Each pip runtime gets its own throwaway venv.
#
# Runtimes covered:
#   - usd-core wheels at multiple versions (pip)
#   - usd-exchange wheel (pip; bundles its own USD)
#   - Isaac Sim Kit's omni.usd.libs, if a Kit/Isaac python is provided via
#     KIT_PYTHON=/path/to/python that can `from pxr import ...`
#
# Each runtime is run RUNS times (multithreaded). A runtime "passes" only if
# every run completes the tests with OK; any crash (SIGSEGV / malloc corruption
# / abort) counts as a failure for that run.
#
# Usage:
#   ./run_all_usd.sh
#   RUNS=8 USD_CORE_VERSIONS="25.5 25.11 26.3 26.5" ./run_all_usd.sh
#   KIT_PYTHON=/path/to/isaac/python ./run_all_usd.sh
#
set -u

RUNS="${RUNS:-6}"
USD_CORE_VERSIONS="${USD_CORE_VERSIONS:-25.5 25.8 25.11 26.3 26.5}"
USDEX_VERSIONS="${USDEX_VERSIONS:-2.3.0}"
TEST="${TEST:-test_usd_4002}"
HERE="$(cd "$(dirname "$0")" && pwd)"

results=()

# crashy_run PYBIN -> echoes "crash" | "pass" | "error"
crashy_run() {
    local py="$1" out ec
    out="$("$py" -m unittest "$TEST" 2>&1)"; ec=$?
    if echo "$out" | grep -qE 'Segmentation|double free|malloc|tcache|Aborted|corrupt|core dumped' || [ "$ec" -ge 128 ]; then
        echo crash
    elif echo "$out" | grep -qE '^OK'; then
        echo pass
    else
        echo error
    fi
}

# sweep LABEL PYBIN
sweep_python() {
    local label="$1" py="$2"
    local ver crash=0 pass=0 err=0 r
    ver="$("$py" -c 'from pxr import Usd; print("%d.%d" % Usd.GetVersion()[1:3])' 2>/dev/null || echo "?")"
    for r in $(seq 1 "$RUNS"); do
        case "$(crashy_run "$py")" in
            crash) crash=$((crash+1)) ;;
            pass)  pass=$((pass+1)) ;;
            *)     err=$((err+1)) ;;
        esac
    done
    local verdict
    if [ "$crash" -gt 0 ]; then verdict="VULNERABLE"; elif [ "$pass" -eq "$RUNS" ]; then verdict="OK (fixed)"; else verdict="INCONCLUSIVE"; fi
    printf '%-26s USD %-7s  pass=%d crash=%d err=%d /%d  -> %s\n' \
        "$label" "$ver" "$pass" "$crash" "$err" "$RUNS" "$verdict"
    results+=("$(printf '%-26s USD %-7s  pass=%d crash=%d err=%d /%d  -> %s' "$label" "$ver" "$pass" "$crash" "$err" "$RUNS" "$verdict")")
}

# sweep a pip-installable spec (e.g. usd-core==26.5, usd-exchange==2.3.0)
sweep_pip() {
    local label="$1" spec="$2" venv
    venv="$(mktemp -d)/v"
    if ! python3 -m venv "$venv" >/dev/null 2>&1; then echo "$label: venv failed"; return; fi
    if ! "$venv/bin/pip" install --quiet "$spec" >/dev/null 2>&1; then
        printf '%-26s (pip install %s FAILED \xe2\x80\x94 skipped)\n' "$label" "$spec"
        rm -rf "$(dirname "$venv")"; return
    fi
    # run from the repo dir so `unittest` discovers the test module
    local oldpwd; oldpwd="$(pwd)"; cd "$HERE"
    sweep_python "$label" "$venv/bin/python"
    cd "$oldpwd"
    rm -rf "$(dirname "$venv")"
}

echo "=== OpenUSD PR #4002 multithreaded-parse sweep (RUNS=$RUNS, test=$TEST) ==="
echo

cd "$HERE"

for v in $USD_CORE_VERSIONS; do
    sweep_pip "usd-core==$v" "usd-core==$v"
done

for v in $USDEX_VERSIONS; do
    sweep_pip "usd-exchange==$v" "usd-exchange==$v"
done

if [ -n "${KIT_PYTHON:-}" ] && [ -x "$KIT_PYTHON" ]; then
    sweep_python "kit omni.usd.libs" "$KIT_PYTHON"
else
    echo "(set KIT_PYTHON=/path/to/isaac-or-kit/python to also test Kit's omni.usd.libs)"
fi

echo
echo "=== summary ==="
printf '%s\n' "${results[@]}"
