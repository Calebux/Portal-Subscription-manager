#!/usr/bin/env python3
"""
Hermes Subscription Export
Generates a CSV audit report and sends it as a file via Telegram.

Usage:
  python3 ~/.hermes/export.py --user-id 6710506545
  python3 ~/.hermes/export.py --user-id 6710506545 --notify
"""

import json
import csv
import sys
import os
import argparse
import urllib.request
import urllib.parse
from datetime import datetime, date
from pathlib import Path

TELEGRAM_BOT_TOKEN = "8722561752:AAHrCn9n8jA599baGU_pTi_JKO5ApOmMc24"
sys.path.insert(0, str(Path.home() / ".hermes"))

try:
    from currency import to_usd, format_amount
except ImportError:
    def to_usd(amount, currency):
        return amount
    def format_amount(amount, currency, show_usd=True):
        return f"{currency} {amount:.2f}"


def load_data(user_id: str) -> dict:
    data_file = Path.home() / ".hermes" / "user-data" / user_id / "scanned-subscriptions.json"
    if data_file.exists():
        with open(data_file) as f:
            return json.load(f)
    return {"subscriptions": [], "cancellation_history": [], "monthly_budget": None}


def send_telegram_file(chat_id: str, file_path: str, caption: str):
    """Send a file via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    with open(file_path, "rb") as f:
        file_data = f.read()

    import email.mime.multipart
    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="document"; filename="{Path(file_path).name}"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except Exception as e:
        print(f"Telegram file send failed: {e}")
        return False


def send_telegram_msg(chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10)
    except Exception:
        pass


def generate_csv(data: dict, out_path: str):
    active = [s for s in data.get("subscriptions", []) if s.get("status") == "active"]
    history = data.get("cancellation_history", [])
    budget = data.get("monthly_budget")
    today = date.today()

    total_usd = sum(to_usd(s.get("monthly_cost", 0), s.get("currency", "USD")) for s in active)

    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)

        # Header block
        w.writerow(["SUBSCRIPTION AUDIT REPORT"])
        w.writerow([f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"])
        w.writerow([f"Total monthly spend (USD): ${total_usd:.2f}"])
        w.writerow([f"Projected annual spend (USD): ${total_usd * 12:.2f}"])
        if budget:
            pct = (total_usd / budget * 100) if budget > 0 else 0
            w.writerow([f"Monthly budget: ${budget:.2f} — {pct:.0f}% used"])
        w.writerow([])

        # Active subscriptions
        w.writerow(["ACTIVE SUBSCRIPTIONS"])
        w.writerow(["Name", "Provider", "Category", "Monthly Cost", "Currency", "USD Equivalent", "Billing Cycle", "Next Renewal", "Health Score", "Last Used", "Use Case", "Source"])
        for s in sorted(active, key=lambda x: to_usd(x.get("monthly_cost", 0), x.get("currency", "USD")), reverse=True):
            cur = s.get("currency", "USD")
            cost = s.get("monthly_cost", 0)
            usd = to_usd(cost, cur)
            w.writerow([
                s.get("name", ""),
                s.get("provider", ""),
                s.get("category", ""),
                cost,
                cur,
                f"${usd:.2f}",
                s.get("billing_cycle", "monthly"),
                s.get("next_renewal", ""),
                s.get("health_score", ""),
                s.get("last_used", ""),
                s.get("use_case", ""),
                s.get("source", ""),
            ])

        w.writerow([])

        # Upcoming renewals
        w.writerow(["UPCOMING RENEWALS (next 30 days)"])
        w.writerow(["Name", "Cost", "Renewal Date", "Days Until"])
        for s in active:
            try:
                renewal = date.fromisoformat(s["next_renewal"])
                days = (renewal - today).days
                if 0 <= days <= 30:
                    cur = s.get("currency", "USD")
                    w.writerow([s["name"], format_amount(s.get("monthly_cost", 0), cur), s["next_renewal"], days])
            except Exception:
                pass

        w.writerow([])

        # Cancellation history
        if history:
            w.writerow(["CANCELLATION HISTORY"])
            w.writerow(["Name", "Cancelled On", "Reason", "Monthly Savings", "Negotiation Attempted", "Discount Offered", "Discount Accepted"])
            for h in history:
                w.writerow([
                    h.get("name", ""),
                    h.get("cancelled_on", ""),
                    h.get("reason", ""),
                    f"${h.get('monthly_savings', 0):.2f}",
                    h.get("negotiation_attempted", False),
                    h.get("discount_offered", ""),
                    h.get("discount_accepted", False),
                ])

    print(f"CSV saved to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Hermes Subscription Export")
    parser.add_argument("--user-id", default="local", help="Telegram user ID")
    parser.add_argument("--notify", action="store_true", help="Send CSV file to Telegram")
    args = parser.parse_args()

    chat_id = args.user_id if args.user_id != "local" else "6710506545"
    data = load_data(args.user_id)

    active = [s for s in data.get("subscriptions", []) if s.get("status") == "active"]
    total_usd = sum(to_usd(s.get("monthly_cost", 0), s.get("currency", "USD")) for s in active)

    # Generate CSV
    out_dir = Path.home() / ".hermes" / "user-data" / args.user_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = str(out_dir / f"subscription-report-{datetime.now().strftime('%Y-%m-%d')}.csv")
    generate_csv(data, out_path)

    print(f"\nSummary: {len(active)} active subscriptions — ${total_usd:.2f}/mo USD (${total_usd * 12:.2f}/yr)")

    if args.notify:
        caption = (
            f"📊 Subscription Report — {datetime.now().strftime('%B %Y')}\n"
            f"Active: {len(active)} subscriptions\n"
            f"Monthly: ${total_usd:.2f} USD\n"
            f"Annual: ${total_usd * 12:.2f} USD"
        )
        ok = send_telegram_file(chat_id, out_path, caption)
        if ok:
            print("File sent to Telegram ✓")
        else:
            print("File send failed — sending text summary instead")
            send_telegram_msg(chat_id, caption)


if __name__ == "__main__":
    main()
