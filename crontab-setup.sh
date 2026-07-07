#!/bin/bash
# SubBot Cron Setup
# Run once to install all agent cron jobs:
#   chmod +x crontab-setup.sh && ./crontab-setup.sh

HERMES_HOME="$HOME/.hermes"
LOG_DIR="$HERMES_HOME/logs"
mkdir -p "$LOG_DIR"

# Copy scripts to hermes home (where crons expect them)
cp llm-analyze.py negotiate.py \
   gmail-scanner.py statement-scanner.py sub_store.py load_env.py currency.py cancel-urls.json \
   "$HERMES_HOME/"

# Install cron jobs
crontab -l 2>/dev/null | grep -v "hermes" | {
  cat
  # Every Monday 08:00 — deep LLM portfolio re-analysis for all users
  echo "0 8 * * 1 cd $HERMES_HOME && for uid in $HERMES_HOME/user-data/*/; do uid=\$(basename \$uid); python3 llm-analyze.py --user-id \$uid >> $LOG_DIR/analyze.log 2>&1; done"
} | crontab -

echo "✅ Cron jobs installed:"
crontab -l | grep hermes
