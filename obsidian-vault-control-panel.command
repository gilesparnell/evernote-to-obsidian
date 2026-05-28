#!/usr/bin/env bash
# Double-click this in Finder (or run it) to start the Obsidian Vault Control
# Panel and open it in your browser. Closing the window (or Ctrl-C) stops the
# server — nothing keeps running in the background.
set -euo pipefail

PORT=8770
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

PY="scripts/classify/venv/bin/python"
SCRIPT="scripts/classify/control_panel.py"

if [[ ! -x "$PY" ]]; then
  echo "venv python not found at $PY — run the project setup first." >&2
  exit 1
fi

echo "starting Obsidian Vault Control Panel on http://127.0.0.1:$PORT ..."
"$PY" "$SCRIPT" --port "$PORT" &
PANEL_PID=$!

# Stop the server when this launcher exits (window closed / Ctrl-C).
trap 'kill "$PANEL_PID" 2>/dev/null || true' EXIT INT TERM

# Wait for the server to bind before opening the browser (max ~6s).
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

echo "opening browser — close this window or press Ctrl-C to stop the panel."
open "http://127.0.0.1:$PORT"

wait "$PANEL_PID"
