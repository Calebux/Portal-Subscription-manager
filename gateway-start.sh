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

# Start the SubBot API bridge (browser extension backend) in background
BRIDGE_DIR="$HOME/Portal-Subscription-manager"
if [ -f "$BRIDGE_DIR/api-bridge.js" ]; then
    # Kill any stale bridge
    pkill -f "api-bridge.js" 2>/dev/null
    sleep 0.5
    cd "$BRIDGE_DIR" && node api-bridge.js >> "$HERMES_HOME/logs/bridge.log" 2>&1 &
    echo "[$(date)] api-bridge.js started (PID $!)" >> "$LOG"
fi

# Start the gateway
exec "$HERMES_HOME/hermes-agent/venv/bin/python" \
    -m hermes_cli.main gateway run
