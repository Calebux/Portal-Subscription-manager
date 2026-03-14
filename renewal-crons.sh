#!/bin/bash
# Hermes Subscription Renewal Alert Script
# Run this to send a Telegram alert for a renewal

SUBSCRIPTION="$1"
AMOUNT="$2"
DATE="$3"
URL="$4"

curl -s -X POST "https://api.telegram.org/bot8722561752:AAHrCn9n8jA599baGU_pTi_JKO5ApOmMc24/sendMessage" \
  -d chat_id="6710506545" \
  -d text="⚠️ RENEWAL IN 3 DAYS

Service: $SUBSCRIPTION
Amount: $$AMOUNT
Renews: $DATE
Action needed: Cancel at $URL

Reply to this message or run: hermes chat -q 'cancel $SUBSCRIPTION'"
