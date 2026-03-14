# SubBot — AI Subscription Manager

> Built for the Nous Research Hermes Hackathon

SubBot is a Telegram bot that tracks, audits, and optimizes your AI and SaaS subscriptions. It connects to your Gmail to auto-detect subscriptions from billing emails, normalizes spend across currencies, alerts you before renewals, and helps you negotiate discounts — all through a natural Telegram conversation.

---

## The Problem

The average person wastes **$300+ per year** on forgotten or overlapping SaaS subscriptions. AI tools in particular — Claude Pro, ChatGPT Plus, GitHub Copilot, Cursor, Perplexity — stack up fast and often go unused. Nobody audits them until the credit card statement hits.

SubBot fixes this.

---

## Features

### Gmail Auto-Detection
Connect your Gmail via App Password (not your main password). SubBot scans billing emails using IMAP, detects subscription charges using pattern matching across 50+ known services, and builds your subscription list automatically — including multi-account support.

### Multi-Currency Support
Subscriptions in NGN, GBP, EUR, CAD, and other currencies are automatically converted to USD using live exchange rates (open.er-api.com, 6-hour cache). A Nigerian user paying ₦57,000/month for Starlink sees it normalized alongside their $20/month Claude Pro subscription.

### Full Audit
Runs a 4-check audit on your subscriptions:
- **Total spend** — monthly and annual in USD
- **Overlap detection** — flags duplicate-category services (e.g. two AI coding assistants)
- **Forgotten services** — highlights subscriptions not used recently
- **Health scores** — 0–100 score per subscription based on usage and value

### Renewal Alerts
A background daemon checks all users' upcoming renewals daily and sends a Telegram message 3 days before any subscription charges. No setup required — it runs automatically.

### Negotiation Emails
For any subscription you want to cancel, SubBot drafts a retention/cancellation email designed to trigger a discount offer (typically 20–50% off). Modelled on real customer retention tactics.

### CSV Export
Exports your full subscription report as a CSV file and sends it directly to your Telegram chat — includes active subscriptions, upcoming renewals, cancellation history, and budget summary.

### Budget Tracking
Set a monthly budget (`"my budget is $100"`). SubBot tracks your spend against it and flags when you're over.

### Multi-User
Every Telegram user gets fully isolated data. Subscription records, budgets, and history are stored per user ID under `~/.hermes/user-data/{telegram_user_id}/`. Any Telegram user can DM the bot and get their own private workspace.

---

## Architecture

SubBot is built as a **skill** on top of the [Hermes Agent](https://github.com/NousResearch/hermes-agent) framework by Nous Research, running the **Hermes-4-70B** model via the Nous inference API.

```
Telegram user
     │
     ▼
Hermes Gateway (Python, runs as macOS LaunchAgent)
     │
     ├── SOUL.md          ← SubBot persona injected into every system prompt
     ├── Hermes-4-70B     ← LLM via Nous inference API
     ├── Memory tools     ← Persistent subscription data per user
     │
     └── Python scripts (called as terminal tools):
          ├── gmail-scanner.py       ← IMAP scan
          ├── subscription-alerts.py ← Renewal daemon
          ├── export.py              ← CSV via Telegram sendDocument
          └── currency.py            ← Live FX normalization
```

### How the persona works
Hermes loads `SOUL.md` from `~/.hermes/` into every system prompt via the `build_context_files_prompt()` mechanism. Combined with `agent.system_prompt` in `config.yaml` and the `aiPeer` name in `~/.honcho/config.json`, this overrides the default Hermes identity so the bot always responds as SubBot — a subscription specialist — instead of a general assistant.

### How multi-user works
The Hermes gateway passes the Telegram user ID to the agent as context. All scripts accept a `--user-id` flag and read/write to `~/.hermes/user-data/{user_id}/`. The memory tool stores subscription data keyed as `subscriptions_db_{user_id}`.

---

## Setup

### Prerequisites
- Python 3.9+
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- A Nous Research API key (inference-api.nousresearch.com)
- Hermes Agent installed

### 1. Install Hermes Agent

```bash
pip install hermes-agent
hermes setup
```

### 2. Clone this repo into ~/.hermes

```bash
git clone https://github.com/Calebux/Portal-Subscription-manager.git /tmp/subbot
cp /tmp/subbot/*.py /tmp/subbot/*.sh /tmp/subbot/*.md ~/.hermes/
```

### 3. Configure environment

Create `~/.hermes/.env`:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_nous_api_key
OPENAI_BASE_URL=https://inference-api.nousresearch.com/v1
GATEWAY_ALLOW_ALL_USERS=true
```

### 4. Apply SubBot persona

**a) Set the system prompt** — add SOUL.md content to `~/.hermes/config.yaml`:

```python
import yaml, pathlib
cfg = yaml.safe_load(open('/Users/YOU/.hermes/config.yaml'))
cfg['agent']['system_prompt'] = open('/Users/YOU/.hermes/SOUL.md').read()
yaml.dump(cfg, open('/Users/YOU/.hermes/config.yaml', 'w'), allow_unicode=True, width=10000)
```

**b) Set the AI peer name** so the bot identifies as SubBot at the top of every prompt:

```bash
mkdir -p ~/.honcho
echo '{"aiPeer": "SubBot", "enabled": false}' > ~/.honcho/config.json
```

### 5. Start the gateway

```bash
hermes gateway run
```

**For persistent background operation on macOS**, copy the LaunchAgent plist:

```bash
cp gateway-start.sh ~/.hermes/
# Edit ai.hermes.gateway.plist to match your username, then:
cp ai.hermes.gateway.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/ai.hermes.gateway.plist
```

The gateway will now start automatically on login and restart if it crashes.

### 6. Set up renewal alerts (optional)

Add a daily cron job to send Telegram alerts 3 days before any subscription renews:

```bash
# Run at 9am daily
0 9 * * * python3 ~/.hermes/subscription-alerts.py
```

---

## Demo Flow

Once the bot is running, DM it on Telegram:

**1. Onboarding**
```
You: hi
Bot: 👋 Hey! I'm SubBot — your AI subscription manager.
     Here's what I can do:
     1️⃣ Gmail scan
     2️⃣ Upload CSV / bank statement
     3️⃣ Manual input
```

**2. Gmail Scan**
```
You: 1
Bot: Perfect! I need your Gmail + App Password...
You: user@gmail.com / xxxx xxxx xxxx xxxx
Bot: Scanning... found 2 subscriptions:
     • Starlink — ₦57,000/mo (~$36 USD), renews Apr 8
     • Claude Pro — $20/mo, renews Mar 25
```

**3. Audit**
```
You: audit
Bot: 📊 Subscription Audit
     Total: $56/mo | $672/year
     ...overlaps and health scores...
```

**4. Budget**
```
You: my budget is $100/month
Bot: Budget set to $100/mo. You're using 56% of it.
```

**5. Export**
Bot sends a CSV file directly to Telegram.

**6. Renewal Alert** (automated)
```
Bot: ⚠️ Claude Pro renews in 3 days ($20.00)
     Cancel: anthropic.com/account
```

**7. Negotiate**
```
You: help me cancel Claude Pro
Bot: Here's a retention email to send before cancelling...
     [drafts email likely to trigger a discount offer]
```

---

## File Reference

| File | Description |
|------|-------------|
| `SOUL.md` | SubBot persona — injected into every system prompt |
| `gmail-scanner.py` | IMAP scanner; detects subscriptions from billing emails across 50+ known services |
| `subscription-alerts.py` | Renewal daemon — scans all users, sends Telegram alert 3 days before renewal |
| `export.py` | Generates CSV report and sends via Telegram `sendDocument` API |
| `currency.py` | Live FX rates with 6-hour cache; converts any currency to USD |
| `token-tracker.py` | Fetches API usage from OpenAI/Anthropic/OpenRouter and calculates subscription ROI |
| `gateway-start.sh` | Clean startup wrapper — kills stale PIDs before launching gateway |
| `renewal-crons.sh` | Helper to install the renewal alert cron job |

---

## What makes this different

Most subscription trackers are passive — you connect a bank account and they show you a list. SubBot is **active**: it scans your Gmail, detects what you actually pay for, and initiates conversations to help you take action (cancel, negotiate, export, alert). It runs as a persistent Telegram agent so it can reach you proactively — not just when you open an app.

The multi-currency support (built specifically for users paying in NGN and other non-USD currencies) means it works for people that most Western SaaS tools ignore.

---

## License

MIT
