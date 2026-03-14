#!/bin/bash
# Hermes gateway wrapper — clears stale locks/PIDs before starting
# Used by launchd to ensure clean startup every time

HERMES_HOME="$HOME/.hermes"
LOG="$HERMES_HOME/logs/gateway.log"

echo "[$(date)] gateway-start.sh: starting" >> "$LOG"

# Kill any stale hermes gateway processes
for pid in $(pgrep -f "hermes_cli.main gateway run" 2>/dev/null); do
    echo "[$(date)] Killing stale gateway PID $pid" >> "$LOG"
    kill -9 "$pid" 2>/dev/null
done

# Clear stale PID file
rm -f "$HERMES_HOME/gateway.pid"

# Small wait to ensure port/socket is released
sleep 1

# Start the gateway
exec "$HERMES_HOME/hermes-agent/venv/bin/python" \
    -m hermes_cli.main gateway run
