#!/usr/bin/env python3
"""
Hermes Bank/Card Statement Scanner
Detects recurring subscription charges from a CSV bank or card statement
export. Gmail receipts miss anything charged straight to a card with no
emailed receipt (many App Store / Play Store subscriptions, some SaaS) —
this fills that gap.

Usage:
  cat statement.csv | python3 statement-scanner.py --user-id 6710506545

CSV is read from stdin (the API bridge pipes the uploaded file content in),
so no file path or credentials ever touch argv.
"""

import csv
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import argparse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sub_store

# ── LLM Config (same as gmail-scanner.py) ────────────────────────────────────
LLM_API_KEY  = os.getenv("OPENROUTER_API_KEY", "")
LLM_BASE_URL = "https://openrouter.ai/api/v1"
LLM_MODEL    = "deepseek/deepseek-chat"

DATE_ALIASES   = ["date", "transaction date", "posted date", "trans date"]
DESC_ALIASES   = ["description", "merchant", "details", "payee", "name"]
AMOUNT_ALIASES = ["amount", "debit", "charge", "amount debited"]

RECURRING_MIN_OCCURRENCES = 2
RECURRING_AMOUNT_TOLERANCE = 0.05  # ±5%
MONTHLY_SPACING = (25, 35)
ANNUAL_SPACING  = (350, 380)


def find_column(headers: list[str], aliases: list[str]) -> Optional[int]:
    lower = [h.strip().lower() for h in headers]
    for alias in aliases:
        if alias in lower:
            return lower.index(alias)
    # fallback: partial match
    for i, h in enumerate(lower):
        if any(alias in h for alias in aliases):
            return i
    return None


def parse_date(raw: str) -> Optional[datetime]:
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%b %d, %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def parse_amount(raw: str) -> Optional[float]:
    cleaned = re.sub(r"[^\d.\-]", "", raw.replace(",", ""))
    if not cleaned or cleaned in ("-", "."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_merchant(desc: str) -> str:
    """Strip trailing store numbers / transaction codes so the same
    merchant groups together across statement rows."""
    name = desc.strip().upper()
    name = re.sub(r"\s+\d{3,}$", "", name)          # trailing store/ref codes
    name = re.sub(r"\s+#\d+$", "", name)             # "#1234"
    name = re.sub(r"\s+(REF|AUTH|POS)\s*\S*$", "", name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name


def parse_statement(csv_text: str) -> list[dict]:
    """Returns raw transaction rows: [{merchant, amount, date}]"""
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    if not rows:
        return []

    headers = rows[0]
    date_i   = find_column(headers, DATE_ALIASES)
    desc_i   = find_column(headers, DESC_ALIASES)
    amount_i = find_column(headers, AMOUNT_ALIASES)

    if date_i is None or desc_i is None or amount_i is None:
        print(f"Could not detect columns from header: {headers}", file=sys.stderr)
        return []

    transactions = []
    for row in rows[1:]:
        if len(row) <= max(date_i, desc_i, amount_i):
            continue
        date_obj = parse_date(row[date_i])
        amount = parse_amount(row[amount_i])
        if not date_obj or amount is None:
            continue
        # Only interested in money going out (debits). Bank exports vary —
        # some show debits as negative, some as positive in a "debit" column.
        amount = abs(amount)
        if amount < 0.50:
            continue
        transactions.append({
            "merchant": normalize_merchant(row[desc_i]),
            "raw_description": row[desc_i].strip(),
            "amount": amount,
            "date": date_obj,
        })
    return transactions


def detect_recurring(transactions: list[dict]) -> list[dict]:
    """Group by normalized merchant and flag ones that recur on a roughly
    monthly or annual cadence with a stable amount."""
    by_merchant: dict[str, list[dict]] = {}
    for t in transactions:
        by_merchant.setdefault(t["merchant"], []).append(t)

    candidates = []
    for merchant, txns in by_merchant.items():
        if len(txns) < RECURRING_MIN_OCCURRENCES:
            continue
        txns.sort(key=lambda t: t["date"])

        gaps = [(txns[i + 1]["date"] - txns[i]["date"]).days for i in range(len(txns) - 1)]
        is_monthly = any(MONTHLY_SPACING[0] <= g <= MONTHLY_SPACING[1] for g in gaps)
        is_annual  = any(ANNUAL_SPACING[0] <= g <= ANNUAL_SPACING[1] for g in gaps)

        # Amount stability is checked against the most recent occurrences only,
        # not the full history — a price hike partway through should still
        # register as recurring (at the new price) so it can be flagged as a
        # price change, rather than getting rejected as "unstable".
        recent = txns[-2:]
        recent_amounts = [t["amount"] for t in recent]
        recent_avg = sum(recent_amounts) / len(recent_amounts)
        amount_stable = all(abs(a - recent_avg) <= recent_avg * RECURRING_AMOUNT_TOLERANCE for a in recent_amounts)

        if amount_stable and (is_monthly or is_annual):
            latest = txns[-1]
            candidates.append({
                "merchant": merchant,
                "raw_description": latest["raw_description"],
                "amount": round(recent_avg, 2),
                "date": latest["date"].strftime("%Y-%m-%d"),
                "cycle": "annual" if is_annual and not is_monthly else "monthly",
                "occurrences": len(txns),
            })
    return candidates


def refine_with_llm(candidates: list[dict]) -> list[dict]:
    """Same-style LLM pass as gmail-scanner.py: clean names, categorize,
    and drop anything that doesn't read like a real subscription."""
    if not candidates or not LLM_API_KEY:
        for c in candidates:
            c["llm_category"] = "other"
        return candidates

    items = [
        f"{i}. merchant=\"{c['raw_description']}\" amount={c['amount']} date={c['date']} occurrences={c['occurrences']}"
        for i, c in enumerate(candidates)
    ]
    prompt = f"""These are recurring charges detected in a bank statement. For each, tell me:
1. Is this actually a subscription/recurring service? (not a loan payment, utility bill, rent, or transfer)
2. The clean, recognizable service name
3. Category (one of: ai, streaming, productivity, cloud, gaming, finance, education, health, communication, other)

Items:
{chr(10).join(items)}

Reply ONLY with a JSON array. Each element: {{"i": index, "keep": true/false, "name": "Clean Name", "category": "cat"}}
No explanation, just the JSON array."""

    try:
        payload = json.dumps({
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": "You are a subscription detection assistant. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 1500,
        }).encode()
        req = urllib.request.Request(
            f"{LLM_BASE_URL}/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read())["choices"][0]["message"]["content"]

        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        refinements = {r["i"]: r for r in json.loads(raw)}

        refined = []
        for i, c in enumerate(candidates):
            ref = refinements.get(i)
            if ref and not ref.get("keep", True):
                print(f"  LLM filtered out: {c['merchant']}")
                continue
            if ref and ref.get("name"):
                c["merchant"] = ref["name"]
            c["llm_category"] = ref.get("category", "other") if ref else "other"
            refined.append(c)
        print(f"LLM refinement: {len(candidates)} -> {len(refined)} recurring charges")
        return refined
    except Exception as e:
        print(f"LLM refinement failed ({e}), using detected candidates as-is")
        for c in candidates:
            c["llm_category"] = "other"
        return candidates


def to_hermes_subscription(candidate: dict) -> dict:
    cycle = candidate.get("cycle", "monthly")
    renewal_days = 365 if cycle == "annual" else 30
    last_date = datetime.strptime(candidate["date"], "%Y-%m-%d").date()
    next_renewal = last_date + timedelta(days=renewal_days)

    merchant = candidate["merchant"]
    slug = re.sub(r"[^a-z0-9]", "-", merchant.lower()).strip("-")

    raw_amount = candidate.get("amount") or 0
    amount = round(raw_amount / 12, 2) if cycle == "annual" else raw_amount

    try:
        sys.path.insert(0, str(Path.home() / ".hermes"))
        from currency import to_usd
        monthly_cost_usd = round(to_usd(amount, "USD"), 2)
    except Exception:
        monthly_cost_usd = amount

    return {
        "id": slug,
        "name": merchant,
        "provider": merchant,
        "category": candidate.get("llm_category", "other"),
        "monthly_cost": amount,
        "monthly_cost_usd": monthly_cost_usd,
        "currency": "USD",
        "billing_cycle": cycle,
        "next_renewal": str(next_renewal),
        "status": "active",
        "use_case": "",
        "last_used": candidate["date"],
        "health_score": 70,
        "notes": f"Detected from statement: {candidate['occurrences']} matching charges",
        "source": "csv-import",
        "is_trial": False,
        "trial_ends": None,
    }


def main():
    parser = argparse.ArgumentParser(description="Hermes Bank/Card Statement Scanner")
    parser.add_argument("--user-id", default="default")
    args = parser.parse_args()

    csv_text = sys.stdin.read()
    transactions = parse_statement(csv_text)
    print(f"Parsed {len(transactions)} transactions from statement")

    candidates = detect_recurring(transactions)
    print(f"Detected {len(candidates)} recurring charge patterns")

    candidates = refine_with_llm(candidates)
    hermes_subs = [to_hermes_subscription(c) for c in candidates]

    db = sub_store.merge_all(args.user_id, hermes_subs)

    print(f"\nSaved {len(hermes_subs)} subscriptions from statement import")
    for s in hermes_subs:
        print(f"  {s['name']}: ${s['monthly_cost']}/mo ({s['billing_cycle']})")

    print(json.dumps({"subscriptions": hermes_subs}))


if __name__ == "__main__":
    main()
