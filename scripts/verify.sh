#!/usr/bin/env bash
# One verification run, in a browser of its own.
#
# Two rules this script exists to enforce:
#
#  1. api/static/ is served from disk. A CSS/HTML/JS edit needs no service
#     restart and no cache bust -- reloading the page is enough.
#  2. Verification never touches the operator's Chrome. The suites drive a
#     throwaway headless instance on :9333 with its own profile, so no visible
#     tab ever reloads mid-task.
#
# Run it once per batch of edits. If it fails, read the failing check and fix
# the cause -- do not re-run in the hope of a different answer.
set -uo pipefail
cd "$(dirname "$0")/.."

PORT=${VERIFY_PORT:-9333}
PROFILE=${VERIFY_PROFILE:-/tmp/harken-verify-profile}
CHROME=${CHROME_BIN:-"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"}

if [ ! -x "$CHROME" ]; then
  echo "verify: Chrome not found at $CHROME (set CHROME_BIN)" >&2
  exit 2
fi

STARTED=""
if ! curl -sf -o /dev/null "http://127.0.0.1:$PORT/json/version"; then
  echo "verify: starting an isolated Chrome on :$PORT"
  "$CHROME" --headless=new --remote-debugging-port="$PORT" \
    --user-data-dir="$PROFILE" --no-first-run --no-default-browser-check \
    --disable-gpu --hide-scrollbars about:blank >/tmp/harken-verify-chrome.log 2>&1 &
  STARTED=$!
  for _ in $(seq 1 60); do
    curl -sf -o /dev/null "http://127.0.0.1:$PORT/json/version" && break
    sleep 0.25
  done
else
  echo "verify: reusing the isolated Chrome already on :$PORT"
fi

cleanup() {
  if [ -n "$STARTED" ]; then
    kill "$STARTED" 2>/dev/null
    wait "$STARTED" 2>/dev/null
  fi
}
trap cleanup EXIT

suites=(verify_type verify_v3 verify_v4 verify_v5 verify_ui)
total_pass=0; total_fail=0; failed=()
for s in "${suites[@]}"; do
  out=$(/usr/bin/python3 "tests/$s.py" 2>&1)
  line=$(printf '%s\n' "$out" | grep -E '^[0-9]+ passed' | tail -1)
  [ -z "$line" ] && line="did not finish"
  printf '  %-14s %s\n' "$s" "$line"
  p=$(printf '%s' "$line" | sed -n 's/^\([0-9]*\) passed.*/\1/p')
  f=$(printf '%s' "$line" | sed -n 's/.*, \([0-9]*\) failed.*/\1/p')
  total_pass=$((total_pass + ${p:-0})); total_fail=$((total_fail + ${f:-0}))
  if [ -n "${f:-}" ] && [ "${f:-0}" -gt 0 ]; then failed+=("$s"); fi
done

echo "  ----------------------------------------"
printf '  TOTAL %d passed, %d failed\n' "$total_pass" "$total_fail"
if [ "$total_fail" -gt 0 ]; then
  echo "  failing: ${failed[*]}"
  echo "  Read the failing check, fix the cause, run once more."
  exit 1
fi
