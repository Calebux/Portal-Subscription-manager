#!/usr/bin/env python3
"""
LLM-Powered Subscription Portfolio Analyzer

Replaces hardcoded health-score formulas with genuine LLM reasoning.
The model sees the full subscription context and reasons about ROI,
overlaps, and negotiation opportunities — not fixed thresholds.

Usage:
  python3 llm-analyze.py --user-id 6710506545 [--notify] [--output-json]

Cron (weekly re-analysis):
  0 8 * * 1 python3 ~/.hermes/llm-analyze.py --user-id 6710506545 --notify >> ~/.hermes/analyze.log 2>&1
"""

import json
import os
import sys
import argparse
import urllib.request
import urllib.parse
import urllib.error
from datetime import date, datetime
from pathlib import Path

BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "8722561752:AAHrCn9n8jA599baGU_pTi_JKO5ApOmMc24")
API_KEY     = os.getenv("OPENAI_API_KEY", "")
API_BASE    = os.getenv("OPENAI_BASE_URL", "https://inference-api.nousresearch.com/v1")
MODEL       = os.getenv("LLM_MODEL", "NousResearch/Hermes-3-Llama-3.1-70B")
USER_DATA_DIR = Path.home() / ".hermes" / "user-data"
BRIDGE_URL  = os.getenv("BRIDGE_URL", "http://localhost:3747")


def load_subscriptions(user_id: str) -> dict:
    sub_file = USER_DATA_DIR / user_id / "scanned-subscriptions.json"
    if sub_file.exists():
        with open(sub_file) as f:
            return json.load(f)
    return {"subscriptions": [], "monthly_budget": None}


def load_token_usage(user_id: str) -> dict | None:
    usage_file = USER_DATA_DIR / user_id / "token-usage.json"
    if usage_file.exists():
        with open(usage_file) as f:
            return json.load(f)
    return None


def call_llm(prompt: str, system: str) -> str:
    if not API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set — add it to ~/.hermes/.env")

    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 2000,
    }).encode()

    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"]


def log_decision_onchain(user_id: str, action: str, amount_saved_usd: float):
    """Fire-and-forget: POST to api-bridge /log-decision for on-chain audit trail."""
    try:
        payload = json.dumps({
            "userId": user_id,
            "action": action,
            "amountSavedUSD": amount_saved_usd,
        }).encode()
        req = urllib.request.Request(
            f"{BRIDGE_URL}/log-decision",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # non-critical — don't fail the analysis


def send_telegram(chat_id: str, message: str):
    url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id":    chat_id,
        "text":       message,
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(url, data=data)
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Telegram send failed: {e}")


def analyze(user_id: str) -> dict:
    today = date.today()
    data  = load_subscriptions(user_id)
    active = [s for s in data.get("subscriptions", []) if s.get("status") == "active"]

    if not active:
        return {"error": "No active subscriptions found"}

    budget      = data.get("monthly_budget")
    token_usage = load_token_usage(user_id)

    usage_context = ""
    if token_usage and token_usage.get("insights"):
        usage_context = (
            f"\n\nAPI token usage data (from provider dashboards):\n"
            f"{json.dumps(token_usage['insights'], indent=2)}"
        )

    budget_context = (
        f"\nMonthly budget set by user: ${budget}/month"
        if budget else "\nUser has not set a monthly budget."
    )

    system = (
        "You are a world-class subscription finance analyst specializing in AI/SaaS costs. "
        "You reason carefully about actual ROI for each service given this specific user's situation. "
        "You give specific, honest, actionable advice — not generic templates. "
        "You reference exact service names, costs, renewal dates, and health scores in your reasoning. "
        "Output ONLY valid JSON. No markdown fences, no explanation outside the JSON."
    )

    prompt = f"""Today is {today}. Analyze this user's full subscription portfolio.

Active subscriptions:
{json.dumps(active, indent=2)}
{budget_context}
{usage_context}

Return a JSON object with EXACTLY these fields:

{{
  "overall_health": "good|warning|critical",
  "summary": "2-3 sentences describing their situation honestly — total spend, biggest risks, one key opportunity",
  "total_monthly_usd": <number>,
  "annual_usd": <number>,
  "budget_status": "under|over|unset",
  "budget_gap_usd": <number or null — positive means over, negative means under>,
  "action_items": [
    {{
      "priority": "high|medium|low",
      "action": "cancel|negotiate|consolidate|keep|upgrade",
      "service": "<exact service name>",
      "reasoning": "<specific reasoning — reference health score, overlap, tenure, renewal date>",
      "monthly_saving_usd": <number or null>
    }}
  ],
  "overlaps": [
    {{
      "services": ["<name>", "<name>"],
      "overlap_type": "<why they overlap — same use case, same capability, redundant value>",
      "recommendation": "<which to keep and exactly why — be specific about relative value>",
      "monthly_saving_usd": <number>
    }}
  ],
  "negotiation_candidates": [
    {{
      "service": "<name>",
      "reason": "<why this service is ripe — low health score, competition exists, tenure, price increase>",
      "strategy": "<exact angle — e.g. cite Cursor as cheaper alternative, request annual plan discount>",
      "expected_discount_pct": <number>
    }}
  ],
  "forgotten_services": [
    {{
      "service": "<name>",
      "evidence": "<why it looks unused — low health score, category overlap with active tools, no activity>",
      "monthly_cost_usd": <number>
    }}
  ],
  "quick_wins": [
    "<actionable sentence with exact service, amount, and deadline — e.g. Cancel X before March 28 to avoid another $20 charge>",
    "<second quick win>"
  ]
}}

Be specific. If two services overlap, explain the actual use-case collision. If health score is low,
say what that implies about real usage. Reference renewal dates when they create urgency."""

    raw = call_llm(prompt, system).strip()

    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0]

    result = json.loads(raw)
    result["generated_at"] = datetime.now().isoformat()
    result["user_id"]      = user_id
    return result


def format_telegram_report(analysis: dict) -> str:
    health_emoji = {"good": "✅", "warning": "⚠️", "critical": "🚨"}.get(
        analysis.get("overall_health", ""), "📊"
    )
    lines = [
        f"{health_emoji} <b>Subscription Analysis</b>\n",
        f"{analysis['summary']}\n",
        f"💰 Monthly: <b>${analysis.get('total_monthly_usd', 0):.2f}</b>"
        f"  |  Annual: ${analysis.get('annual_usd', 0):.0f}",
    ]

    budget_status = analysis.get("budget_status")
    gap           = analysis.get("budget_gap_usd")
    if budget_status == "over" and gap:
        lines.append(f"⚠️ Over budget by <b>${gap:.2f}</b>")
    elif budget_status == "under" and gap is not None:
        lines.append(f"✅ Under budget by ${abs(gap):.2f}")

    overlaps = analysis.get("overlaps", [])
    if overlaps:
        lines.append(f"\n<b>🔁 Overlaps ({len(overlaps)} found)</b>")
        for o in overlaps[:3]:
            services = " + ".join(o["services"])
            saving   = o.get("monthly_saving_usd", 0)
            lines.append(f"• {services} → save ${saving:.0f}/mo")
            lines.append(f"  <i>{o['recommendation']}</i>")

    forgotten = analysis.get("forgotten_services", [])
    if forgotten:
        lines.append(f"\n<b>🕳 Likely forgotten ({len(forgotten)})</b>")
        for f in forgotten[:3]:
            lines.append(f"• {f['service']} — ${f.get('monthly_cost_usd', 0):.0f}/mo")
            lines.append(f"  <i>{f['evidence']}</i>")

    quick_wins = analysis.get("quick_wins", [])
    if quick_wins:
        lines.append(f"\n<b>⚡ Quick wins</b>")
        for qw in quick_wins[:3]:
            lines.append(f"• {qw}")

    actions = analysis.get("action_items", [])
    high    = [a for a in actions if a.get("priority") == "high"]
    if high:
        lines.append(f"\n<b>🎯 Priority actions</b>")
        for a in high[:3]:
            saving     = a.get("monthly_saving_usd")
            saving_str = f" (save ${saving:.0f}/mo)" if saving else ""
            lines.append(f"• {a['action'].title()} <b>{a['service']}</b>{saving_str}")
            lines.append(f"  <i>{a['reasoning']}</i>")

    lines.append("\nReply <b>/negotiate</b> to draft discount emails for top candidates.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="LLM-powered subscription portfolio analyzer")
    parser.add_argument("--user-id",    required=True, help="Telegram user ID")
    parser.add_argument("--notify",     action="store_true", help="Send results via Telegram")
    parser.add_argument("--output-json", action="store_true", help="Print full JSON to stdout")
    args = parser.parse_args()

    print(f"Analyzing portfolio for user {args.user_id}...")
    analysis = analyze(args.user_id)

    if "error" in analysis:
        print(f"Error: {analysis['error']}")
        sys.exit(1)

    # Save result
    out_dir  = USER_DATA_DIR / args.user_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "llm-analysis.json"
    with open(out_file, "w") as f:
        json.dump(analysis, f, indent=2)
    print(f"Saved → {out_file}")

    # Log high-priority cancellations on-chain
    total_saving = sum(
        a.get("monthly_saving_usd", 0) or 0
        for a in analysis.get("action_items", [])
        if a.get("priority") == "high"
    )
    if total_saving > 0:
        log_decision_onchain(args.user_id, "audit_complete", total_saving)

    if args.output_json:
        print(json.dumps(analysis, indent=2))
    else:
        print(f"Health:      {analysis.get('overall_health')}")
        print(f"Monthly:     ${analysis.get('total_monthly_usd', 0):.2f}")
        print(f"Actions:     {len(analysis.get('action_items', []))}")
        print(f"Overlaps:    {len(analysis.get('overlaps', []))}")
        print(f"Quick wins:  {len(analysis.get('quick_wins', []))}")

    if args.notify:
        report = format_telegram_report(analysis)
        send_telegram(args.user_id, report)
        print("Telegram notification sent.")


if __name__ == "__main__":
    main()
