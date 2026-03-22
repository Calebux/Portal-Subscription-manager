#!/usr/bin/env python3
"""
SubBot Autonomous Daily Digest Agent

Runs once per day via cron. For each user, the LLM reviews their subscription
data and generates a personalized briefing — only if something genuinely worth
acting on is found. No message is sent if nothing is urgent today.

This is the core "agent acts without being asked" behavior.

Usage:
  python3 agent-digest.py                   # all users
  python3 agent-digest.py --user-id 123456  # specific user
  python3 agent-digest.py --dry-run         # print without sending

Cron (9:05 AM daily, runs after renewal alerts):
  5 9 * * * cd ~/.hermes && python3 agent-digest.py >> ~/.hermes/digest.log 2>&1
"""

import json
import os
import sys
import argparse
import urllib.request
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "8722561752:AAHrCn9n8jA599baGU_pTi_JKO5ApOmMc24")
API_KEY       = os.getenv("OPENAI_API_KEY", "")
API_BASE      = os.getenv("OPENAI_BASE_URL", "https://inference-api.nousresearch.com/v1")
MODEL         = os.getenv("LLM_MODEL", "NousResearch/Hermes-3-Llama-3.1-70B")
USER_DATA_DIR = Path.home() / ".hermes" / "user-data"
DIGEST_LOG    = Path.home() / ".hermes" / "digest-sent.json"
BRIDGE_URL    = os.getenv("BRIDGE_URL", "http://localhost:3747")


# ── State ──────────────────────────────────────────────────────────────────

def load_sent_log() -> dict:
    if DIGEST_LOG.exists():
        with open(DIGEST_LOG) as f:
            return json.load(f)
    return {}


def save_sent_log(log: dict):
    with open(DIGEST_LOG, "w") as f:
        json.dump(log, f, indent=2)


# ── Data Loading ───────────────────────────────────────────────────────────

def get_all_user_ids() -> list[str]:
    if not USER_DATA_DIR.exists():
        return []
    return [
        d.name
        for d in USER_DATA_DIR.iterdir()
        if d.is_dir() and (d / "scanned-subscriptions.json").exists()
    ]


def load_user_context(user_id: str) -> dict | None:
    sub_file = USER_DATA_DIR / user_id / "scanned-subscriptions.json"
    if not sub_file.exists():
        return None
    with open(sub_file) as f:
        data = json.load(f)

    # Attach last LLM analysis if fresh (< 7 days old)
    analysis_file = USER_DATA_DIR / user_id / "llm-analysis.json"
    if analysis_file.exists():
        with open(analysis_file) as f:
            analysis = json.load(f)
        generated = analysis.get("generated_at", "")
        if generated:
            try:
                age_days = (datetime.now() - datetime.fromisoformat(generated)).days
                if age_days < 7:
                    data["last_analysis"] = {
                        "quick_wins":    analysis.get("quick_wins", []),
                        "overlaps_count": len(analysis.get("overlaps", [])),
                        "high_priority_actions": [
                            a for a in analysis.get("action_items", [])
                            if a.get("priority") == "high"
                        ],
                        "overall_health": analysis.get("overall_health"),
                    }
            except ValueError:
                pass

    return data


# ── LLM ────────────────────────────────────────────────────────────────────

def call_llm(prompt: str, system: str) -> str:
    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 350,
    }).encode()

    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type":  "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"]


def generate_briefing(user_id: str, user_data: dict) -> str | None:
    """
    Returns a Telegram-ready 2-3 sentence briefing, or None if nothing actionable today.
    The LLM decides — not code — whether something is worth sending.
    """
    today  = date.today()
    active = [s for s in user_data.get("subscriptions", []) if s.get("status") == "active"]
    if not active:
        return None

    budget    = user_data.get("monthly_budget")
    total_usd = sum(
        s.get("monthly_cost_usd") or s.get("monthly_cost", 0)
        for s in active
    )

    # Pre-compute upcoming renewals for the LLM's context
    upcoming = []
    for s in active:
        rd = s.get("next_renewal")
        if rd:
            try:
                renewal   = date.fromisoformat(rd)
                days_left = (renewal - today).days
                if 0 <= days_left <= 7:
                    upcoming.append({
                        "name":        s["name"],
                        "cost_usd":    s.get("monthly_cost_usd") or s.get("monthly_cost", 0),
                        "days_left":   days_left,
                        "renewal_date": rd,
                    })
            except ValueError:
                pass

    context = {
        "today":                str(today),
        "active_subscription_count": len(active),
        "total_monthly_usd":    round(total_usd, 2),
        "monthly_budget":       budget,
        "renewals_in_7_days":   upcoming,
        "subscriptions":        active,
    }

    # Include pending actions from last LLM analysis
    last = user_data.get("last_analysis", {})
    if last:
        context["pending_high_priority_actions"] = last.get("high_priority_actions", [])
        context["known_overlaps_count"]           = last.get("overlaps_count", 0)
        context["portfolio_health"]               = last.get("overall_health", "unknown")

    system = (
        "You are SubBot, an autonomous AI subscription manager. "
        "You proactively look after users' finances and contact them only when "
        "something genuinely needs their attention today. "
        "You do NOT send messages just to stay top-of-mind. "
        "Every message you send must have a specific, time-sensitive reason.\n\n"
        "Rules:\n"
        "- If nothing is actionable TODAY, return exactly: null\n"
        "- If something is worth noting, write 2-3 sentences max — specific, not generic\n"
        "- Always reference exact service names, dollar amounts, and dates\n"
        "- Do NOT start with 'Hi' or 'Good morning' — get straight to the point\n"
        "- End with one clear next step the user can take right now\n"
        "- Format for Telegram: use <b>bold</b> for key numbers and service names\n"
        "- Never repeat information the user already knows"
    )

    prompt = f"""Here is today's subscription context for this user:

{json.dumps(context, indent=2)}

Is there something worth messaging this user about TODAY?

Worth sending: upcoming charges in 1-7 days, budget overruns, a high-value cancellation opportunity, a forgotten service about to charge again.
Not worth sending: general advice, things you already told them, routine status updates.

If yes → write the 2-3 sentence briefing (Telegram HTML).
If no  → return exactly: null"""

    response = call_llm(prompt, system).strip()

    if response.lower() in ("null", ""):
        return None
    # Strip quotes if model adds them
    if response.startswith('"') and response.endswith('"'):
        response = response[1:-1]

    return response


# ── Notification ───────────────────────────────────────────────────────────

def send_telegram(chat_id: str, message: str):
    url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id":    chat_id,
        "text":       message,
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(url, data=data)
    urllib.request.urlopen(req, timeout=10)


def log_digest_onchain(user_id: str):
    """Record that the autonomous agent ran for this user today."""
    try:
        payload = json.dumps({
            "userId": user_id,
            "action": "daily_digest",
            "amountSavedUSD": 0,
        }).encode()
        req = urllib.request.Request(
            f"{BRIDGE_URL}/log-decision",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # non-critical


# ── Main ───────────────────────────────────────────────────────────────────

def run_digest(user_ids: list[str], dry_run: bool = False):
    today     = str(date.today())
    sent_log  = load_sent_log()
    sent_count    = 0
    skipped_count = 0

    for user_id in user_ids:
        # One digest per user per day
        if sent_log.get(user_id) == today and not dry_run:
            print(f"[{user_id}] Already sent today — skipping")
            continue

        user_data = load_user_context(user_id)
        if not user_data:
            print(f"[{user_id}] No data — skipping")
            continue

        print(f"[{user_id}] Generating briefing...")
        try:
            briefing = generate_briefing(user_id, user_data)
        except Exception as e:
            print(f"[{user_id}] LLM error: {e}")
            continue

        if briefing is None:
            print(f"[{user_id}] Nothing actionable today")
            skipped_count += 1
            continue

        print(f"[{user_id}] Briefing: {briefing[:100]}...")

        if dry_run:
            print(f"\n{'─'*60}\n[DRY RUN → {user_id}]\n{briefing}\n{'─'*60}\n")
        else:
            try:
                send_telegram(user_id, briefing)
                sent_log[user_id] = today
                save_sent_log(sent_log)
                log_digest_onchain(user_id)
                print(f"[{user_id}] ✓ Sent")
                sent_count += 1
            except Exception as e:
                print(f"[{user_id}] Send failed: {e}")

    print(f"\n── Digest complete ──")
    print(f"Sent: {sent_count}  |  Nothing actionable: {skipped_count}")


def main():
    parser = argparse.ArgumentParser(description="Autonomous daily subscription digest agent")
    parser.add_argument("--user-id", help="Run for specific user only (default: all users)")
    parser.add_argument("--dry-run", action="store_true", help="Print briefings without sending")
    args = parser.parse_args()

    if not API_KEY:
        print("Error: OPENAI_API_KEY not set — add it to ~/.hermes/.env")
        sys.exit(1)

    user_ids = [args.user_id] if args.user_id else get_all_user_ids()
    if not user_ids:
        print("No users with subscription data found.")
        sys.exit(0)

    print(f"SubBot Digest Agent — {date.today()} — {len(user_ids)} user(s)")
    run_digest(user_ids, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
