#!/usr/bin/env python3
"""
Hermes Subscription Renewal Alert Daemon
Runs daily, fires Telegram alerts 3 days + 1 day before each renewal.
Loads subscriptions dynamically from scanned JSON files for all users.
"""

import json
import time
import datetime
import urllib.request
import urllib.parse
import os
import sys
from pathlib import Path

BOT_TOKEN = "8722561752:AAHrCn9n8jA599baGU_pTi_JKO5ApOmMc24"
ALERT_DAYS_BEFORE = 3
USER_DATA_DIR = Path.home() / ".hermes" / "user-data"
SENT_LOG = Path.home() / ".hermes" / "alerts-sent.json"

CANCEL_URLS = {
    "chatgpt plus": "https://chat.openai.com/manage",
    "claude pro": "https://claude.ai/settings",
    "gemini advanced": "https://one.google.com/subscriptions",
    "github copilot": "https://github.com/settings/copilot",
    "cursor": "https://cursor.sh/settings/billing",
    "perplexity pro": "https://www.perplexity.ai/settings/account",
    "midjourney": "https://www.midjourney.com/account",
    "grammarly": "https://www.grammarly.com/subscription",
    "notion ai": "https://www.notion.so/profile/settings",
    "elevenlabs": "https://elevenlabs.io/subscription",
    "openrouter": "https://openrouter.ai/settings/credits",
    "adobe creative cloud": "https://account.adobe.com/plans",
    "replit": "https://replit.com/account",
    "figma": "https://www.figma.com/settings",
    "vercel": "https://vercel.com/account/billing",
    "netlify": "https://app.netlify.com/teams/billing",
    "starlink": "https://www.starlink.com/account",
    "canva": "https://www.canva.com/settings/billing",
    "dropbox": "https://www.dropbox.com/account/billing",
    "zoom": "https://zoom.us/billing",
    "slack": "https://slack.com/intl/billing",
    "spotify": "https://www.spotify.com/account/subscription",
    "netflix": "https://www.netflix.com/cancelplan",
    "discord nitro": "https://discord.com/settings/subscriptions",
    "linear": "https://linear.app/settings/account",
    "loom": "https://www.loom.com/settings",
}


def load_sent() -> dict:
    if SENT_LOG.exists():
        with open(SENT_LOG) as f:
            return json.load(f)
    return {}


def save_sent(sent: dict):
    with open(SENT_LOG, "w") as f:
        json.dump(sent, f, indent=2)


def send_telegram(chat_id: str, message: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def load_all_users() -> list[tuple[str, list[dict]]]:
    """Load subscriptions for all users. Returns [(user_id, subscriptions), ...]"""
    results = []
    if not USER_DATA_DIR.exists():
        return results
    for user_dir in USER_DATA_DIR.iterdir():
        if not user_dir.is_dir():
            continue
        sub_file = user_dir / "scanned-subscriptions.json"
        if not sub_file.exists():
            continue
        try:
            with open(sub_file) as f:
                data = json.load(f)
            active = [s for s in data.get("subscriptions", []) if s.get("status") == "active"]
            if active:
                results.append((user_dir.name, active))
        except Exception as e:
            print(f"Error loading {sub_file}: {e}")
    return results


def format_cost(sub: dict) -> str:
    cur = sub.get("currency", "USD")
    amount = sub.get("monthly_cost", 0)
    symbols = {"USD": "$", "NGN": "₦", "GBP": "£", "EUR": "€"}
    sym = symbols.get(cur, cur + " ")

    # Try to show USD equivalent for non-USD
    if cur != "USD":
        try:
            sys.path.insert(0, str(Path.home() / ".hermes"))
            from currency import to_usd
            usd = to_usd(amount, cur)
            return f"{sym}{amount:,.0f} (~${usd:.0f} USD)"
        except Exception:
            pass
    return f"{sym}{amount:.2f}"


def get_cancel_url(name: str) -> str:
    return CANCEL_URLS.get(name.lower(), "Check provider website")


def check_and_alert(test_mode: bool = False):
    today = datetime.date.today()
    sent = load_sent()
    alerted_count = 0

    users = load_all_users()
    if not users:
        print(f"[{today}] No user subscription data found.")
        return

    for user_id, subscriptions in users:
        for sub in subscriptions:
            renewal_str = sub.get("next_renewal")
            if not renewal_str:
                continue

            try:
                renewal = datetime.date.fromisoformat(renewal_str)
            except ValueError:
                continue

            days_left = (renewal - today).days
            name = sub.get("name", "Unknown")
            cost_str = format_cost(sub)
            cancel_url = get_cancel_url(name)
            alert_key = f"{user_id}-{name}-{renewal_str}"

            if test_mode:
                msg = (
                    f"⚠️ <b>RENEWAL ALERT</b>\n\n"
                    f"📦 <b>{name}</b>\n"
                    f"💰 {cost_str}/month\n"
                    f"📅 Renews in {days_left} days ({renewal_str})\n\n"
                    f"🔗 Cancel: {cancel_url}"
                )
                try:
                    result = send_telegram(user_id, msg)
                    status = "✓" if result.get("ok") else "✗"
                    print(f"  {status} [{user_id}] {name}")
                    alerted_count += 1
                except Exception as e:
                    print(f"  ✗ [{user_id}] {name}: {e}")

            elif days_left == ALERT_DAYS_BEFORE and alert_key not in sent:
                msg = (
                    f"⚠️ <b>RENEWAL IN 3 DAYS</b>\n\n"
                    f"📦 <b>{name}</b>\n"
                    f"💰 {cost_str}/month\n"
                    f"📅 Renews: {renewal_str}\n\n"
                    f"🔗 Cancel: {cancel_url}\n\n"
                    f"Reply /audit to review all subscriptions."
                )
                try:
                    result = send_telegram(user_id, msg)
                    if result.get("ok"):
                        sent[alert_key] = str(today)
                        save_sent(sent)
                        print(f"[{today}] Alert sent → [{user_id}] {name}")
                        alerted_count += 1
                except Exception as e:
                    print(f"[{today}] Failed to alert [{user_id}] {name}: {e}")

            elif days_left == 1 and f"{alert_key}-final" not in sent:
                msg = (
                    f"🚨 <b>FINAL WARNING — CHARGES TOMORROW</b>\n\n"
                    f"📦 <b>{name}</b> charges <b>{cost_str}</b> tomorrow.\n"
                    f"🔗 Cancel NOW: {cancel_url}"
                )
                try:
                    result = send_telegram(user_id, msg)
                    if result.get("ok"):
                        sent[f"{alert_key}-final"] = str(today)
                        save_sent(sent)
                        print(f"[{today}] Final alert sent → [{user_id}] {name}")
                        alerted_count += 1
                except Exception as e:
                    print(f"[{today}] Failed final alert [{user_id}] {name}: {e}")

    if not test_mode and alerted_count == 0:
        print(f"[{today}] No alerts due today.")


def run_daemon():
    print("Hermes Subscription Alert Daemon started.")
    print(f"Monitoring all users in {USER_DATA_DIR}")
    print(f"Alerting {ALERT_DAYS_BEFORE} days before renewal, daily at 09:00.")

    while True:
        now = datetime.datetime.now()
        if now.hour == 9 and now.minute == 0:
            check_and_alert()
            time.sleep(60)
        else:
            time.sleep(30)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("TEST MODE: firing all alerts now...")
        check_and_alert(test_mode=True)
    else:
        run_daemon()
