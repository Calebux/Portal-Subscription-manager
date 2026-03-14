#!/usr/bin/env python3
"""
Hermes Token Tracker
Fetches real API usage from LLM providers and calculates token ROI vs subscription plans.

Usage:
  python3 ~/.hermes/token-tracker.py --openai-key sk-... --anthropic-key sk-ant-... --openrouter-key sk-or-...
  python3 ~/.hermes/token-tracker.py --openai-key sk-... --user-id 6710506545 --notify
"""

import json
import sys
import os
import argparse
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Optional

TELEGRAM_BOT_TOKEN = "8722561752:AAHrCn9n8jA599baGU_pTi_JKO5ApOmMc24"

# Break-even: tokens/month at which API cost == subscription cost
# e.g. Claude Pro = $20/mo. Haiku input = $0.80/M tokens → break-even = 25M tokens
SUBSCRIPTION_PLANS = {
    "openai": {
        "name": "ChatGPT Plus",
        "monthly_cost": 20.00,
        "cheapest_api_model": "gpt-4o-mini",
        "cheapest_api_cost_per_1m_input": 0.15,   # $ per 1M input tokens
        "cheapest_api_cost_per_1m_output": 0.60,
    },
    "anthropic": {
        "name": "Claude Pro",
        "monthly_cost": 20.00,
        "cheapest_api_model": "claude-haiku-3-5",
        "cheapest_api_cost_per_1m_input": 0.80,
        "cheapest_api_cost_per_1m_output": 4.00,
    },
    "openrouter": {
        "name": "OpenRouter (pay-as-you-go)",
        "monthly_cost": 0,
        "note": "No flat subscription — pure API usage",
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def http_get(url: str, headers: dict) -> Optional[dict]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} for {url}: {e.reason}")
        return None
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None


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


def breakeven_tokens(monthly_cost: float, cost_per_1m_input: float, cost_per_1m_output: float) -> int:
    """Tokens/month at which API spend equals subscription cost (assuming 70/30 input/output split)."""
    blended = (cost_per_1m_input * 0.7 + cost_per_1m_output * 0.3) / 1_000_000
    if blended <= 0:
        return 0
    return int(monthly_cost / blended)


# ── Provider Fetchers ──────────────────────────────────────────────────────────

def fetch_openai(api_key: str) -> dict:
    print("Fetching OpenAI usage...")
    today = date.today()
    start = today.replace(day=1).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")

    result = {
        "provider": "openai",
        "api_spend_usd": None,
        "tokens_input": None,
        "tokens_output": None,
        "tokens_total": None,
        "models_used": [],
        "error": None,
    }

    # Billing usage (dollar spend)
    billing_url = f"https://api.openai.com/v1/dashboard/billing/usage?start_date={start}&end_date={end}"
    headers = {"Authorization": f"Bearer {api_key}"}
    billing = http_get(billing_url, headers)
    if billing and "total_usage" in billing:
        result["api_spend_usd"] = round(billing["total_usage"] / 100, 4)  # cents → dollars

    # Token-level usage (newer orgs API)
    start_unix = int(datetime(today.year, today.month, 1, tzinfo=timezone.utc).timestamp())
    end_unix = int(datetime.now(timezone.utc).timestamp())
    usage_url = (
        f"https://api.openai.com/v1/organization/usage/completions"
        f"?start_time={start_unix}&end_time={end_unix}&group_by=model&limit=50"
    )
    usage = http_get(usage_url, headers)
    if usage and "data" in usage:
        total_input = 0
        total_output = 0
        models = set()
        for bucket in usage.get("data", []):
            for result_item in bucket.get("results", []):
                total_input += result_item.get("input_tokens", 0)
                total_output += result_item.get("output_tokens", 0)
                if result_item.get("model"):
                    models.add(result_item["model"])
        result["tokens_input"] = total_input
        result["tokens_output"] = total_output
        result["tokens_total"] = total_input + total_output
        result["models_used"] = sorted(models)

    if result["api_spend_usd"] is None and result["tokens_total"] is None:
        result["error"] = (
            "Could not fetch usage (403 Forbidden). "
            "Project keys (sk-proj-...) need Usage read permission. "
            "Fix: platform.openai.com/api-keys → Edit key → enable 'Read' under Usage. "
            "Or create a new org-level key with Usage permissions."
        )

    return result


def fetch_anthropic(api_key: str) -> dict:
    print("Fetching Anthropic usage...")
    result = {
        "provider": "anthropic",
        "api_spend_usd": None,
        "tokens_input": None,
        "tokens_output": None,
        "tokens_total": None,
        "models_used": [],
        "error": None,
    }

    today = date.today()
    start_unix = int(datetime(today.year, today.month, 1, tzinfo=timezone.utc).timestamp())
    end_unix = int(datetime.now(timezone.utc).timestamp())

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    # Try the usage endpoint
    usage_url = f"https://api.anthropic.com/v1/usage?start_time={start_unix}&end_time={end_unix}"
    usage = http_get(usage_url, headers)

    if usage and "data" in usage:
        total_input = 0
        total_output = 0
        models = set()
        for entry in usage.get("data", []):
            total_input += entry.get("input_tokens", 0)
            total_output += entry.get("output_tokens", 0)
            if entry.get("model"):
                models.add(entry["model"])
        result["tokens_input"] = total_input
        result["tokens_output"] = total_output
        result["tokens_total"] = total_input + total_output
        result["models_used"] = sorted(models)

        # Estimate cost (Sonnet pricing as proxy)
        cost = (total_input / 1_000_000 * 3.0) + (total_output / 1_000_000 * 15.0)
        result["api_spend_usd"] = round(cost, 4)
    else:
        result["error"] = "Usage API not accessible — may require workspace admin key"

    return result


def fetch_openrouter(api_key: str) -> dict:
    print("Fetching OpenRouter usage...")
    result = {
        "provider": "openrouter",
        "credits_used_usd": None,
        "credits_remaining_usd": None,
        "rate_limit": None,
        "models_used": [],
        "error": None,
    }

    headers = {"Authorization": f"Bearer {api_key}"}
    data = http_get("https://openrouter.ai/api/v1/auth/key", headers)

    if data and "data" in data:
        d = data["data"]
        usage_credits = d.get("usage", 0)      # in credits (1 credit = $0.000001)
        limit = d.get("limit")                  # None = unlimited

        result["credits_used_usd"] = round(usage_credits / 1_000_000, 4) if usage_credits else 0
        result["credits_remaining_usd"] = (
            round((limit - usage_credits) / 1_000_000, 4) if limit else None
        )
        result["rate_limit"] = d.get("rate_limit", {})
    else:
        result["error"] = "Could not fetch OpenRouter key info"

    return result


# ── Analysis ──────────────────────────────────────────────────────────────────

def build_insights(providers: dict) -> list[str]:
    insights = []

    # OpenAI
    if "openai" in providers:
        p = providers["openai"]
        plan = SUBSCRIPTION_PLANS["openai"]
        if p.get("api_spend_usd") is not None:
            spend = p["api_spend_usd"]
            sub_cost = plan["monthly_cost"]
            be = breakeven_tokens(sub_cost, plan["cheapest_api_cost_per_1m_input"], plan["cheapest_api_cost_per_1m_output"])
            tokens = p.get("tokens_total") or 0

            if spend < sub_cost * 0.5:
                insights.append(
                    f"OpenAI API spend this month: ${spend:.2f} — well below Plus plan (${sub_cost:.0f}/mo). "
                    f"Consider dropping ChatGPT Plus and going API-only."
                )
            elif tokens > 0 and tokens < be:
                insights.append(
                    f"OpenAI: you're at {tokens:,} tokens this month. "
                    f"Break-even vs Plus plan is {be:,} tokens — API is cheaper for you."
                )
            elif tokens >= be:
                insights.append(
                    f"OpenAI: {tokens:,} tokens used — above break-even ({be:,}). Plus plan is better value."
                )

    # Anthropic
    if "anthropic" in providers:
        p = providers["anthropic"]
        plan = SUBSCRIPTION_PLANS["anthropic"]
        if p.get("tokens_total") is not None:
            tokens = p["tokens_total"]
            be = breakeven_tokens(plan["monthly_cost"], plan["cheapest_api_cost_per_1m_input"], plan["cheapest_api_cost_per_1m_output"])
            if tokens > 0 and tokens < be:
                insights.append(
                    f"Anthropic API: {tokens:,} tokens this month (below Claude Pro break-even of {be:,}). "
                    f"API-only would be cheaper than Pro."
                )
            elif tokens >= be:
                insights.append(
                    f"Anthropic: {tokens:,} tokens — Claude Pro flat rate is better value than API at this usage."
                )

    # OpenRouter
    if "openrouter" in providers:
        p = providers["openrouter"]
        if p.get("credits_remaining_usd") is not None and p["credits_remaining_usd"] < 5:
            insights.append(
                f"⚠️ OpenRouter credits low: ${p['credits_remaining_usd']:.2f} remaining. Top up soon."
            )
        if p.get("credits_used_usd"):
            insights.append(f"OpenRouter spend this month: ${p['credits_used_usd']:.2f}")

    if not insights:
        insights.append("No significant optimization opportunities found this month.")

    return insights


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Hermes LLM Token Tracker")
    parser.add_argument("--openai-key", help="OpenAI API key")
    parser.add_argument("--anthropic-key", help="Anthropic API key")
    parser.add_argument("--openrouter-key", help="OpenRouter API key")
    parser.add_argument("--user-id", default="local", help="Telegram user ID")
    parser.add_argument("--notify", action="store_true", help="Send results to Telegram")
    args = parser.parse_args()

    if not any([args.openai_key, args.anthropic_key, args.openrouter_key]):
        print("Error: provide at least one API key (--openai-key, --anthropic-key, --openrouter-key)")
        sys.exit(1)

    chat_id = args.user_id if args.user_id != "local" else "6710506545"
    today = date.today()

    providers = {}

    if args.openai_key:
        providers["openai"] = fetch_openai(args.openai_key)
    if args.anthropic_key:
        providers["anthropic"] = fetch_anthropic(args.anthropic_key)
    if args.openrouter_key:
        providers["openrouter"] = fetch_openrouter(args.openrouter_key)

    insights = build_insights(providers)

    output = {
        "period": today.strftime("%Y-%m"),
        "generated_at": datetime.now().isoformat(),
        "providers": providers,
        "insights": insights,
    }

    # Save
    out_dir = Path.home() / ".hermes" / "user-data" / args.user_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "token-usage.json"
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n── Token Usage Report ({today.strftime('%B %Y')}) ──")
    for provider, data in providers.items():
        print(f"\n{provider.upper()}")
        if data.get("error"):
            print(f"  ⚠ {data['error']}")
        if data.get("api_spend_usd") is not None:
            print(f"  API spend:  ${data['api_spend_usd']:.4f}")
        if data.get("tokens_total") is not None:
            print(f"  Tokens:     {data['tokens_total']:,} ({data.get('tokens_input',0):,} in / {data.get('tokens_output',0):,} out)")
        if data.get("credits_used_usd") is not None:
            print(f"  Credits used:      ${data['credits_used_usd']:.4f}")
        if data.get("credits_remaining_usd") is not None:
            print(f"  Credits remaining: ${data['credits_remaining_usd']:.2f}")
        if data.get("models_used"):
            print(f"  Models: {', '.join(data['models_used'])}")

    print(f"\n── Insights ──")
    for ins in insights:
        print(f"  • {ins}")

    print(f"\nSaved to {out_file}")

    if args.notify:
        lines = [f"<b>🔢 Token Usage Report — {today.strftime('%B %Y')}</b>\n"]
        for provider, data in providers.items():
            plan = SUBSCRIPTION_PLANS.get(provider, {})
            lines.append(f"<b>{provider.upper()}</b>")
            if data.get("error"):
                lines.append(f"  ⚠ {data['error']}")
            else:
                if data.get("api_spend_usd") is not None:
                    lines.append(f"  API spend: ${data['api_spend_usd']:.2f}")
                if data.get("tokens_total") is not None:
                    lines.append(f"  Tokens: {data['tokens_total']:,}")
                if data.get("credits_used_usd") is not None:
                    lines.append(f"  Credits used: ${data['credits_used_usd']:.2f}")
                if data.get("credits_remaining_usd") is not None:
                    lines.append(f"  Credits left: ${data['credits_remaining_usd']:.2f}")
            lines.append("")

        lines.append("<b>💡 Insights</b>")
        for ins in insights:
            lines.append(f"• {ins}")

        send_telegram(chat_id, "\n".join(lines))


if __name__ == "__main__":
    main()
