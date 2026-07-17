#!/bin/bash
set -e

cd "$(dirname "$0")"

PID_FILE=".venv/.tracesignal.pid"
PORT_FILE=".venv/.tracesignal.port"

if [ -f "$PID_FILE" ] && [ -f "$PORT_FILE" ]; then
  EXISTING_PID="$(/bin/cat "$PID_FILE")"
  EXISTING_PORT="$(/bin/cat "$PORT_FILE")"
  EXISTING_URL="http://127.0.0.1:${EXISTING_PORT}"
  if /bin/kill -0 "$EXISTING_PID" 2>/dev/null && /usr/bin/curl -fsS "${EXISTING_URL}/_stcore/health" >/dev/null 2>&1; then
    echo "TraceSignal is already running. Opening it now."
    if [ "${TRACESIGNAL_NO_BROWSER:-0}" != "1" ]; then
      /usr/bin/open "$EXISTING_URL"
    fi
    exit 0
  fi
  /bin/rm -f "$PID_FILE" "$PORT_FILE"
fi

if ! /usr/bin/env python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  echo "TraceSignal needs Python 3.10 or newer."
  echo "Install it from https://www.python.org/downloads/ and try again."
  read -r -p "Press Return to close..."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Creating TraceSignal's private Python environment..."
  /usr/bin/env python3 -m venv .venv
fi

source .venv/bin/activate
export ARROW_DEFAULT_MEMORY_POOL="${ARROW_DEFAULT_MEMORY_POOL:-system}"

REQUIREMENTS_HASH="$(/usr/bin/shasum -a 256 requirements.txt | /usr/bin/awk '{print $1}')"
READY_FILE=".venv/.tracesignal-requirements-${REQUIREMENTS_HASH}"
if [ ! -f "$READY_FILE" ]; then
  echo "First launch: downloading TraceSignal's packages. Later launches will be faster."
  python -m pip --disable-pip-version-check install --prefer-binary -r requirements.txt
  /bin/rm -f .venv/.tracesignal-requirements-* .venv/.tracesignal-ready
  /usr/bin/touch "$READY_FILE"
else
  echo "Using the existing TraceSignal environment."
fi

if [ -n "${TRACESIGNAL_PORT:-}" ]; then
  PORT="$TRACESIGNAL_PORT"
else
  PORT="$(python - <<'PY'
import socket

for candidate in [8585, *range(8501, 8600)]:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", candidate))
    except OSError:
        continue
    finally:
        sock.close()
    print(candidate)
    break
else:
    raise SystemExit("No free local port was found between 8501 and 8599.")
PY
)"
fi

URL="http://127.0.0.1:${PORT}"
MAX_UPLOAD_MB="${TRACESIGNAL_MAX_UPLOAD_MB:-50}"

echo "Starting TraceSignal at ${URL}..."
python -m streamlit run app.py \
  --server.headless=true \
  --server.address=127.0.0.1 \
  --server.port="$PORT" \
  --server.maxUploadSize="$MAX_UPLOAD_MB" \
  --server.fileWatcherType=none \
  --browser.gatherUsageStats=false &
APP_PID=$!

echo "$APP_PID" > "$PID_FILE"
echo "$PORT" > "$PORT_FILE"

cleanup() {
  /bin/rm -f "$PID_FILE" "$PORT_FILE"
  if /bin/kill -0 "$APP_PID" 2>/dev/null; then
    /bin/kill "$APP_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

ATTEMPT=1
while [ "$ATTEMPT" -le 120 ]; do
  if /usr/bin/curl -fsS "${URL}/_stcore/health" >/dev/null 2>&1; then
    echo "TraceSignal is ready. Opening your browser..."
    if [ "${TRACESIGNAL_NO_BROWSER:-0}" != "1" ]; then
      /usr/bin/open "$URL"
    fi
    wait "$APP_PID"
    exit $?
  fi
  if ! /bin/kill -0 "$APP_PID" 2>/dev/null; then
    echo "TraceSignal stopped before it became ready. Review the message above."
    wait "$APP_PID"
    exit $?
  fi
  ATTEMPT=$((ATTEMPT + 1))
  /bin/sleep 0.25
done

echo "TraceSignal took too long to start. Review the message above, then try again."
exit 1
