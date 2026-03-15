#!/usr/bin/env python3
"""
SubBot Usage ROI Calculator
Calculates cost-per-hour for each subscription based on:
  - API token data (for API users)
  - Manually reported weekly hours (for flat subscription web users)

Usage:
  python3 ~/.hermes/usage-roi.py --user-id 6710506545 --notify
  python3 ~/.hermes/usage-roi.py --user-id 6710506545 --set-hours "Claude Pro=10,ChatGPT Plus=3"
"""

import json
import argparse
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime
from typing import Optional

TELEGRAM_BOT_TOKEN = "8722561752:AAHrCn9n8jA599baGU_pTi_JKO5ApOmMc24"

# Tokens per hour of active use (rough heuristic)
# ~500 tokens/minute average interaction (reading + typing + model output)
TOKENS_PER_HOUR = 30_000

# Verdict thresholds (cost per hour in USD)
VERDICT_KEEP        = 0.10   # under $0.10/hr = great value
VERDICT_RECONSIDER  = 0.30   # $0.10–0.30/hr = reconsider
# above $0.30/hr = cancel


def send_telegram(chat_id: str, message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }).encode()
    try:
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Telegram send failed: {e}")


def load_subscriptions(user_id: str) -> dict:
    path = Path.home() / ".hermes" / "user-data" / user_id / "scanned-subscriptions.json"
    if not path.exists():
        return {"subscriptions": []}
    return json.loads(path.read_text())


def save_subscriptions(user_id: str, data: dict):
    path = Path.home() / ".hermes" / "user-data" / user_id / "scanned-subscriptions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def load_token_usage(user_id: str) -> Optional[dict]:
    path = Path.home() / ".hermes" / "user-data" / user_id / "token-usage.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def estimate_hours_from_tokens(tokens: int) -> float:
    """Estimate active hours from token count."""
    return round(tokens / TOKENS_PER_HOUR, 1)


def cost_per_hour(monthly_cost: float, weekly_hours: float) -> Optional[float]:
    if weekly_hours <= 0:
        return None
    monthly_hours = weekly_hours * 4.33
    return round(monthly_cost / monthly_hours, 3)


def verdict(cph: Optional[float]) -> str:
    if cph is None:
        return "❓ No usage data"
    if cph <= VERDICT_KEEP:
        return "✅ Keep"
    if cph <= VERDICT_RECONSIDER:
        return "⚠️ Reconsider"
    return "❌ Cancel"


def build_roi_report(user_id: str) -> dict:
    subs_data = load_subscriptions(user_id)
    token_data = load_token_usage(user_id)

    rows = []

    # Map provider token data to subscription names
    token_map = {}
    if token_data:
        providers = token_data.get("providers", {})
        if "openai" in providers and not providers["openai"].get("error"):
            tokens = providers["openai"].get("tokens_total") or 0
            token_map["chatgpt"] = estimate_hours_from_tokens(tokens)
        if "anthropic" in providers and not providers["anthropic"].get("error"):
            tokens = providers["anthropic"].get("tokens_total") or 0
            token_map["claude"] = estimate_hours_from_tokens(tokens)
        if "openrouter" in providers and not providers["openrouter"].get("error"):
            credits = providers["openrouter"].get("credits_used_usd") or 0
            # estimate from spend: $0.001/1k tokens average across models
            est_tokens = credits * 1_000_000
            token_map["openrouter"] = estimate_hours_from_tokens(int(est_tokens))

    for sub in subs_data.get("subscriptions", []):
        if sub.get("status") != "active":
            continue

        name = sub.get("name", "")
        monthly_cost = sub.get("monthly_cost", 0)
        currency = sub.get("currency", "USD")

        # Normalize to USD if needed
        if currency != "USD":
            try:
                from currency import to_usd
                monthly_cost = to_usd(monthly_cost, currency)
            except Exception:
                pass

        # Try to get weekly hours: manual entry wins, then token estimate
        weekly_hours = sub.get("weekly_hours")

        if weekly_hours is None:
            # Try to infer from token data
            name_lower = name.lower()
            if "claude" in name_lower:
                weekly_hours = token_map.get("claude")
            elif "chatgpt" in name_lower or "openai" in name_lower:
                weekly_hours = token_map.get("chatgpt")
            elif "openrouter" in name_lower:
                weekly_hours = token_map.get("openrouter")

        cph = cost_per_hour(monthly_cost, weekly_hours or 0) if weekly_hours else None

        rows.append({
            "name": name,
            "monthly_cost_usd": round(monthly_cost, 2),
            "weekly_hours": weekly_hours,
            "cost_per_hour": cph,
            "verdict": verdict(cph),
        })

    output = {
        "generated_at": datetime.now().isoformat(),
        "rows": rows,
        "missing_hours": [r["name"] for r in rows if r["weekly_hours"] is None],
    }

    # Save
    out_dir = Path.home() / ".hermes" / "user-data" / user_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "usage-roi.json").write_text(json.dumps(output, indent=2))

    return output


def format_table(report: dict) -> str:
    rows = report["rows"]
    if not rows:
        return "No active subscriptions found."

    lines = ["<b>💡 Subscription Usage ROI</b>\n"]
    lines.append(f"{'Service':<18} {'$/mo':>6}  {'hrs/wk':>7}  {'$/hr':>6}  Verdict")
    lines.append("─" * 58)

    for r in rows:
        name = r["name"][:17]
        cost = f"${r['monthly_cost_usd']:.0f}"
        hrs = f"{r['weekly_hours']:.1f}h" if r["weekly_hours"] is not None else "  ?"
        cph = f"${r['cost_per_hour']:.2f}" if r["cost_per_hour"] is not None else "  ?"
        v = r["verdict"]
        lines.append(f"{name:<18} {cost:>6}  {hrs:>7}  {cph:>6}  {v}")

    missing = report.get("missing_hours", [])
    if missing:
        lines.append(f"\n⚠️ Missing usage hours for: {', '.join(missing)}")
        lines.append('Tell me: "I use Claude Pro 8 hours a week" to fill these in.')

    return "\n".join(lines)


def set_weekly_hours(user_id: str, hours_str: str):
    """Parse 'Claude Pro=10,ChatGPT Plus=3' and save to subscriptions."""
    subs_data = load_subscriptions(user_id)
    updates = {}
    for pair in hours_str.split(","):
        if "=" in pair:
            name, hrs = pair.strip().split("=", 1)
            updates[name.strip().lower()] = float(hrs.strip())

    changed = 0
    for sub in subs_data.get("subscriptions", []):
        name_lower = sub.get("name", "").lower()
        if name_lower in updates:
            sub["weekly_hours"] = updates[name_lower]
            changed += 1

    if changed:
        save_subscriptions(user_id, subs_data)
        print(f"Updated weekly_hours for {changed} subscription(s).")
    else:
        print("No matching subscriptions found. Check the names match exactly.")


def main():
    parser = argparse.ArgumentParser(description="SubBot Usage ROI Calculator")
    parser.add_argument("--user-id", default="local")
    parser.add_argument("--notify", action="store_true", help="Send report to Telegram")
    parser.add_argument("--set-hours", help="Set weekly hours: 'Claude Pro=10,ChatGPT Plus=3'")
    args = parser.parse_args()

    if args.set_hours:
        set_weekly_hours(args.user_id, args.set_hours)
        return

    report = build_roi_report(args.user_id)
    table = format_table(report)

    print(table)

    if args.notify:
        chat_id = args.user_id if args.user_id != "local" else "6710506545"
        send_telegram(chat_id, table)


if __name__ == "__main__":
    main()
