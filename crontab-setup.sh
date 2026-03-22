#!/bin/bash
# SubBot Cron Setup
# Run once to install all agent cron jobs:
#   chmod +x crontab-setup.sh && ./crontab-setup.sh

HERMES_HOME="$HOME/.hermes"
LOG_DIR="$HERMES_HOME/logs"
mkdir -p "$LOG_DIR"

# Copy scripts to hermes home (where crons expect them)
cp llm-analyze.py agent-digest.py negotiate.py subscription-alerts.py "$HERMES_HOME/"

# Install cron jobs
crontab -l 2>/dev/null | grep -v "hermes" | {
  cat
  # 09:00 — renewal alerts (3 days / 1 day warnings)
  echo "0 9 * * * cd $HERMES_HOME && python3 subscription-alerts.py >> $LOG_DIR/alerts.log 2>&1"
  # 09:05 — autonomous digest (LLM reviews every user, sends only if actionable)
  echo "5 9 * * * cd $HERMES_HOME && python3 agent-digest.py >> $LOG_DIR/digest.log 2>&1"
  # Every Monday 08:00 — deep LLM portfolio re-analysis for all users
  echo "0 8 * * 1 cd $HERMES_HOME && for uid in $HERMES_HOME/user-data/*/; do uid=\$(basename \$uid); python3 llm-analyze.py --user-id \$uid --notify >> $LOG_DIR/analyze.log 2>&1; done"
} | crontab -

echo "✅ Cron jobs installed:"
crontab -l | grep hermes
