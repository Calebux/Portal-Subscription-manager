#!/usr/bin/env python3
"""
Hermes Gmail Scanner
Scans Gmail inbox for subscription receipts and populates Hermes memory.
Triggered by the subscription-manager skill when user says "scan my email".

Usage:
  python3 ~/.hermes/gmail-scanner.py --email you@gmail.com --password "xxxx xxxx xxxx xxxx"
  python3 ~/.hermes/gmail-scanner.py --email you@gmail.com --password "xxxx xxxx xxxx xxxx" --user-id 6710506545
"""

import imaplib
import email
import re
import json
import os
import sys
import time
import hashlib
import argparse
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────
LOOKBACK_DAYS = 120
HERMES_MEMORY_DIR = Path.home() / ".hermes" / "memory"
TELEGRAM_BOT_TOKEN = "8722561752:AAHrCn9n8jA599baGU_pTi_JKO5ApOmMc24"

SUBSCRIPTION_SIGNALS = [
    "subscription", "your plan", "membership",
    "billed monthly", "billed annually", "auto-renew", "auto renew",
    "renewal", "recurring", "billing cycle", "next billing", "next charge",
    "cancel anytime", "your invoice", "your receipt",
    "payment confirmation", "payment receipt", "charged for",
]

EXCLUSION_SIGNALS = [
    "test mode", "test payment", "% off", "save up to", "special offer",
    "has shipped", "shipping confirmation", "your order has", "order confirmation",
    "order #", "order number", "tracking number", "your package",
    "refund", "newsletter", "unsubscribe from our list",
    "charged $0.00", "charged ₦0.00", " $0.00 ",
    "one-time", "one time purchase", "single purchase",
    "gift card", "gift certificate",
    "hotel", "flight", "reservation", "booking confirmation",
    "uber", "lyft", "doordash", "instacart",
    # Failed/declined payments — not active subscriptions
    "payment failed", "payment unsuccessful", "was unsuccessful",
    "failed to process", "payment issue", "payment declined",
    "could not process", "unable to process",
]

CANCELLATION_SIGNALS = [
    "subscription cancelled", "subscription has been cancelled",
    "subscription has ended", "cancellation confirmed",
    "your cancellation", "cancelled your subscription",
    "we're sorry to see you go",
]

AMOUNT_PATTERNS = [
    r"\$\s?([\d,]+(?:\.\d{2})?)",
    r"USD\s?([\d,]+(?:\.\d{2})?)",
    r"([\d,]+(?:\.\d{2})?)\s?USD",
    r"£\s?([\d,]+(?:\.\d{2})?)",
    r"€\s?([\d,]+(?:\.\d{2})?)",
    r"NGN\s?([\d,]+(?:\.\d{2})?)",
    r"₦\s?([\d,]+(?:\.\d{2})?)",
    r"total[:\s]+\$?\s?([\d,]+(?:\.\d{2})?)",
    r"amount[:\s]+\$?\s?([\d,]+(?:\.\d{2})?)",
    r"charged[:\s]+\$?\s?([\d,]+(?:\.\d{2})?)",
    r"balance[:\s]+[A-Z]*\s?([\d,]+(?:\.\d{2})?)",
]

CURRENCY_PATTERNS = {
    r"NGN": "NGN",
    r"₦": "NGN",
    r"\$": "USD",
    r"USD": "USD",
    r"£": "GBP",
    r"€": "EUR",
}

# Known AI/SaaS subscription senders → clean name mapping
KNOWN_SERVICES = {
    "anthropic": "Claude Pro",
    "openai": "ChatGPT Plus",
    "github": "GitHub Copilot",
    "cursor": "Cursor",
    "perplexity": "Perplexity Pro",
    "midjourney": "Midjourney",
    "notion": "Notion AI",
    "grammarly": "Grammarly",
    "adobe": "Adobe Creative Cloud",
    "figma": "Figma",
    "linear": "Linear",
    "vercel": "Vercel",
    "netlify": "Netlify",
    "elevenlabs": "ElevenLabs",
    "openrouter": "OpenRouter",
    "replit": "Replit",
    "codeium": "Codeium / Windsurf",
    "jasper": "Jasper AI",
    "copy.ai": "Copy.ai",
    "runway": "Runway ML",
    "pika": "Pika Labs",
    "amazon": "AWS / Amazon",
    "google": "Google One / Workspace",
    "microsoft": "Microsoft 365",
    "dropbox": "Dropbox",
    "spotify": "Spotify",
    "netflix": "Netflix",
    "discord": "Discord Nitro",
    "slack": "Slack",
    "zoom": "Zoom",
    "loom": "Loom",
    "superhuman": "Superhuman",
    "starlink": "Starlink",
    "spacex": "Starlink",
    "canva": "Canva",
    "namecheap": "Namecheap",
}

# Services confirmed as NOT subscriptions (one-time charges, travel eSIM, etc.)
SKIP_MERCHANTS = {"roamless", "canva"}


# ── Helpers ───────────────────────────────────────────────────────────────────
def decode_mime_words(s: str) -> str:
    parts = decode_header(s)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def extract_body(msg) -> str:
    snippet = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                payload = part.get_payload(decode=True)
                if payload:
                    snippet = payload.decode(errors="replace")
                    break
        if not snippet:
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        raw = payload.decode(errors="replace")
                        snippet = re.sub(r"<[^>]+>", " ", raw)
                        snippet = re.sub(r"\s+", " ", snippet).strip()
                        break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            snippet = payload.decode(errors="replace")
    return snippet[:3000].strip()


def extract_amount(text: str) -> Optional[float]:
    for pattern in AMOUNT_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw = match.group(1).replace(",", "")
            try:
                val = float(raw)
                if 0.50 <= val <= 9_999_999:
                    return round(val, 2)
            except ValueError:
                continue
    return None


def extract_currency(text: str) -> str:
    for symbol, code in CURRENCY_PATTERNS.items():
        if re.search(symbol, text):
            return code
    return "USD"


def extract_merchant(from_header: str) -> str:
    # Check known services first
    from_lower = from_header.lower()
    for key, name in KNOWN_SERVICES.items():
        if key in from_lower:
            return name

    # Try display name
    display_match = re.match(r'^"?([^"<]+)"?\s*<', from_header)
    if display_match:
        name = display_match.group(1).strip().strip('"')
        if name and not re.fullmatch(r"[a-z0-9._%+\-]+", name, re.IGNORECASE):
            return name

    # Fall back to domain
    domain_match = re.search(r"@([\w.\-]+)>?", from_header)
    if domain_match:
        domain = domain_match.group(1).lower()
        parts = domain.split(".")
        if len(parts) >= 2:
            return parts[-2].capitalize()
    return from_header[:40]


def to_hermes_subscription(record: dict) -> dict:
    """Convert a scanner record to subscription-manager schema."""
    import calendar
    from datetime import date

    # Estimate next renewal (30 days from last charge)
    try:
        last_date = datetime.strptime(record["date"], "%Y-%m-%d").date()
        next_renewal = last_date + timedelta(days=30)
    except Exception:
        next_renewal = (datetime.now() + timedelta(days=30)).date()

    merchant = record["merchant"]
    slug = re.sub(r"[^a-z0-9]", "-", merchant.lower()).strip("-")

    amount = record.get("amount") or 0
    currency = record.get("currency", "USD")

    # Pre-calculate USD equivalent so the agent always has it
    try:
        sys.path.insert(0, str(Path.home() / ".hermes"))
        from currency import to_usd
        monthly_cost_usd = round(to_usd(amount, currency), 2)
    except Exception:
        monthly_cost_usd = amount if currency == "USD" else 0

    return {
        "id": slug,
        "name": merchant,
        "provider": merchant,
        "category": "other",  # agent will refine this
        "monthly_cost": amount,
        "monthly_cost_usd": monthly_cost_usd,
        "currency": currency,
        "billing_cycle": "monthly",
        "next_renewal": str(next_renewal),
        "status": record.get("status", "active"),
        "use_case": "",
        "last_used": record["date"],
        "health_score": 70,
        "notes": f"Auto-detected from email: {record.get('subject', '')[:80]}",
        "source": "gmail-scan",
    }


# ── Scanner ───────────────────────────────────────────────────────────────────
def scan_gmail(email_addr: str, app_password: str, progress_fn=None) -> list[dict]:
    print(f"Connecting to Gmail as {email_addr}...")
    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    mail.login(email_addr, app_password)

    since_gmail = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y/%m/%d")
    since_imap  = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")

    all_uids = []
    try:
        mail.select('"[Gmail]/All Mail"')
        _, data = mail.search(None, "X-GM-RAW", f'"category:subscriptions after:{since_gmail}"')
        all_uids = data[0].split() if data[0] else []
        print(f"Gmail Subscriptions category: {len(all_uids)} emails")
    except Exception:
        pass

    if not all_uids:
        for folder in ['"[Gmail]/All Mail"', "INBOX"]:
            try:
                mail.select(folder)
            except Exception:
                continue
            seen = set()
            for kw in ["receipt", "invoice", "subscription", "billing", "renewal", "payment", "statement", "starlink", "charged"]:
                try:
                    _, data = mail.search(None, f'(SINCE "{since_imap}" SUBJECT "{kw}")')
                    if data[0]:
                        for uid in data[0].split():
                            seen.add(uid)
                except Exception:
                    pass
            if seen:
                all_uids = list(seen)
                print(f"Folder {folder} keyword search: {len(all_uids)} emails")
                break
        print(f"INBOX keyword search: {len(all_uids)} emails")

    records = []
    seen_merchants = {}

    for i, uid in enumerate(all_uids):
        try:
            _, msg_data = mail.fetch(uid, "(RFC822)")
            if not msg_data or msg_data[0] is None:
                continue
            raw_bytes = msg_data[0][1] if isinstance(msg_data[0], tuple) else None
            if not raw_bytes:
                continue

            msg = email.message_from_bytes(raw_bytes)
            subject = decode_mime_words(msg.get("Subject", ""))
            from_header = msg.get("From", "")
            date_header = msg.get("Date", "")

            try:
                date_obj = parsedate_to_datetime(date_header)
                date_str = date_obj.strftime("%Y-%m-%d")
            except Exception:
                date_str = datetime.now().strftime("%Y-%m-%d")

            body = extract_body(msg)
            combined = f"{subject} {body}".lower()

            # Filter
            is_cancelled = any(s in combined for s in CANCELLATION_SIGNALS)
            amount = extract_amount(f"{subject} {body}")
            merchant = extract_merchant(from_header)
            is_known = any(k in from_header.lower() for k in KNOWN_SERVICES)

            if not is_cancelled:
                if not amount or amount <= 0:
                    continue
                # Known services skip the signal check — we already know they're subscriptions
                if not is_known and not any(s in combined for s in SUBSCRIPTION_SIGNALS):
                    continue
                if any(s in combined for s in EXCLUSION_SIGNALS):
                    continue
            status = "cancelled" if is_cancelled else "active"

            # Skip merchants confirmed as non-subscriptions
            if merchant.lower() in SKIP_MERCHANTS:
                continue

            # Deduplicate: keep latest record per merchant
            currency = extract_currency(f"{subject} {body}")
            if merchant not in seen_merchants or date_str > seen_merchants[merchant]["date"]:
                seen_merchants[merchant] = {
                    "merchant": merchant,
                    "amount": amount,
                    "currency": currency,
                    "date": date_str,
                    "subject": subject[:200],
                    "status": status,
                }

            if progress_fn:
                progress_fn(i + 1, len(all_uids), merchant)

        except Exception as e:
            continue

    mail.logout()
    records = list(seen_merchants.values())
    print(f"Found {len(records)} unique subscriptions.")
    return records


def send_telegram(chat_id: str, message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode()
    try:
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Telegram send failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Hermes Gmail Subscription Scanner")
    parser.add_argument("--email", action="append", required=True, help="Gmail address (repeat for multiple accounts)")
    parser.add_argument("--password", action="append", required=True, help="Gmail App Password (repeat for multiple accounts)")
    parser.add_argument("--user-id", default=None, help="Telegram user ID for namespacing")
    parser.add_argument("--notify", action="store_true", help="Send results to Telegram")
    args = parser.parse_args()

    if len(args.email) != len(args.password):
        print("Error: number of --email and --password arguments must match")
        sys.exit(1)

    accounts = list(zip(args.email, args.password))
    user_id = args.user_id or "default"
    chat_id = args.user_id or "6710506545"

    if args.notify:
        acct_word = "account" if len(accounts) == 1 else f"{len(accounts)} accounts"
        send_telegram(chat_id, f"Scanning {acct_word} for subscriptions... this takes ~30 seconds each.")

    # Scan all accounts and merge by merchant (latest record wins)
    merged: dict[str, dict] = {}
    scanned_emails = []
    all_cancelled = []

    for email_addr, app_password in accounts:
        print(f"\n── Scanning {email_addr} ──")
        records = scan_gmail(email_addr, app_password)
        scanned_emails.append(email_addr)
        for r in records:
            merchant = r["merchant"]
            if merchant not in merged or r["date"] > merged[merchant]["date"]:
                merged[merchant] = r
            if r["status"] == "cancelled":
                all_cancelled.append(r)

    all_records = list(merged.values())
    hermes_subs = [to_hermes_subscription(r) for r in all_records]

    # Save to per-user file for the skill to load
    out_dir = Path.home() / ".hermes" / "user-data" / user_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "scanned-subscriptions.json"

    db = {
        "subscriptions": hermes_subs,
        "cancellation_history": [to_hermes_subscription(r) for r in all_cancelled],
        "last_audit": datetime.now().strftime("%Y-%m-%d"),
        "scanned_from": scanned_emails,
        "monthly_budget": None,
    }

    with open(out_file, "w") as f:
        json.dump(db, f, indent=2)

    print(f"\nSaved {len(hermes_subs)} subscriptions to {out_file}")

    # Print summary
    active = [s for s in hermes_subs if s["status"] == "active"]
    usd_subs = [s for s in active if s.get("currency", "USD") == "USD"]
    total_usd = sum(s["monthly_cost"] for s in usd_subs if s["monthly_cost"])
    print(f"\nSUMMARY:")
    print(f"  Active subscriptions: {len(active)}")
    print(f"  Monthly spend (USD): ${total_usd:.2f}")
    for s in sorted(active, key=lambda x: x["monthly_cost"] or 0, reverse=True):
        cur = s.get("currency", "USD")
        sym = "₦" if cur == "NGN" else ("£" if cur == "GBP" else ("€" if cur == "EUR" else "$"))
        print(f"  {s['name']:30} {sym}{s['monthly_cost']:.2f}/mo  [{cur}]  (renews {s['next_renewal']})")

    if args.notify and chat_id:
        msg_lines = [
            f"Gmail scan complete! Found {len(active)} active subscriptions.\n",
            f"USD subscriptions: ${total_usd:.2f}/month\n\n",
            "Subscriptions found:",
        ]
        for s in sorted(active, key=lambda x: x["monthly_cost"] or 0, reverse=True)[:8]:
            cur = s.get("currency", "USD")
            sym = "₦" if cur == "NGN" else ("£" if cur == "GBP" else ("€" if cur == "EUR" else "$"))
            msg_lines.append(f"  {s['name']} - {sym}{s['monthly_cost']:.2f}/mo")
        msg_lines.append("\nSay 'audit my subscriptions' for overlap analysis.")
        send_telegram(chat_id, "\n".join(msg_lines))


if __name__ == "__main__":
    main()
