# SubBot — AI Subscription Manager

> Built for the Nous Research Hermes Hackathon · Powered by Hermes-4-70B on Celo

## Try it now

**Web app → [portal-subscription-manager-production.up.railway.app](https://portal-subscription-manager-production.up.railway.app)**

**Telegram bot → [@SubmanagerAgentBot](https://t.me/SubmanagerAgentBot)**

---

## What it does

The average person wastes **$300+ per year** on forgotten or overlapping SaaS subscriptions. AI tools in particular — Claude Pro, ChatGPT Plus, Copilot, Cursor — stack up fast. Nobody audits them until the credit card statement hits.

SubBot fixes this. It scans your Gmail for billing emails, builds your full subscription list automatically, flags overlaps and forgotten services, alerts you before renewals, and helps you negotiate discounts — all through a natural Telegram conversation. A companion web dashboard syncs with your bot in real time.

---

## Quick demo (2 minutes)

**Option A — Web app only (no bot needed):**
1. Open [the web app](https://portal-subscription-manager-production.up.railway.app)
2. Tap **Get Started**
3. Tap **+** on the Subscriptions tab to add a subscription manually
4. Watch the Dashboard, Audit, and Alerts tabs update instantly

**Option B — Full flow with Telegram bot:**
1. Message [@SubmanagerAgentBot](https://t.me/SubmanagerAgentBot) on Telegram
2. Send `/myid` — the bot replies with your numeric Telegram ID
3. Open the web app, paste your ID → your bot data loads into the dashboard
4. Ask the bot: `"audit my subscriptions"` or `"what am I paying for"`

**Option C — Gmail scan (full power):**
1. Tell the bot you want to scan your Gmail
2. Get a Google App Password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Share your email + App Password with the bot
4. Bot scans your inbox, auto-detects all subscriptions, syncs to the web dashboard

---

## Features

| Feature | How it works |
|---------|-------------|
| **Gmail auto-scan** | IMAP scan across 50+ known services (Netflix, Spotify, Claude, GitHub, Disney+ etc.) |
| **Multi-currency** | Live FX rates — NGN, GBP, EUR all normalized to USD |
| **Overlap detection** | Flags duplicate-category services (e.g. two AI coding tools) |
| **Health scores** | 0–100 per subscription based on usage recency and value |
| **Renewal alerts** | Telegram message 3 days before any subscription charges |
| **Negotiation emails** | Drafts retention emails proven to trigger 20–50% discount offers |
| **CSV export** | Full report sent directly to your Telegram chat |
| **Budget tracking** | Set a monthly limit, track spend against it |
| **Pay-per-run** | Send cUSD on Celo → credits unlock bot actions |
| **Web dashboard** | Live sync with bot — Dashboard, Audit, Alerts, Credits tabs |

---

## Celo Integration

SubBot uses **Celo cUSD** for pay-per-run credits. Users send cUSD to the project wallet from MiniPay or Valora. The bot detects the deposit via on-chain balance delta and unlocks actions:

| Action | Cost |
|--------|------|
| Gmail Scan | 0.10 cUSD |
| AI Audit | 0.05 cUSD |
| Export CSV | 0.05 cUSD |
| Negotiation Email | 0.10 cUSD |
| View Dashboard | Free |

The web app shows a live QR code for the wallet address and syncs the credit balance automatically. Works with MiniPay natively — no wallet extension needed.

---

## Architecture

```
Telegram user
     │
     ▼
Hermes Gateway  (Python · Hermes-4-70B via Nous inference API)
     │
     ├── config.yaml             ← SubBot persona + tool instructions
     ├── gmail-scanner.py        ← IMAP scan, 50+ known services
     ├── subscription-alerts.py  ← Renewal daemon (runs daily)
     ├── export.py               ← CSV via Telegram sendDocument
     ├── currency.py             ← Live FX with 6hr cache
     └── sync-to-web.py          ← Pushes data to Railway after every update
          │
          ▼
     API Bridge  (Node.js · Railway)
          │
          ├── GET  /subs      ← Web app reads subscription data
          ├── POST /sync      ← Bot pushes full data after every change
          ├── POST /add-sub   ← Web app manual add
          ├── GET  /balance   ← Celo cUSD balance via Ankr RPC
          └── serves public/  ← Web dashboard (index.html)
               │
               ▼
          Web Dashboard  (Vanilla JS · Tailwind · Railway)
```

### How the bot persona works
The SubBot persona is injected via `system_prompt` in `config.yaml`. Combined with Hermes-4-70B's tool-use capabilities and a strict instruction set, the model behaves as a subscription specialist — reads disk files for authoritative data, calls Python scripts via the terminal tool, never leaks internal reasoning to users.

### How bot → web sync works
Every time the Hermes agent writes subscription data to disk, it runs `sync-to-web.py` which POSTs the full JSON to the Railway `/sync` endpoint. The web app reads from Railway on load and refreshes every 60 seconds.

### Multi-user
Every Telegram user gets isolated data at `~/.hermes/user-data/{telegram_user_id}/`. Any number of users can run the bot concurrently with their own subscription list, budget, and history.

---

## Running locally

### Prerequisites
- Python 3.9+
- Node.js 18+
- Telegram bot token ([@BotFather](https://t.me/BotFather))
- Nous Research API key

### 1. Clone and install

```bash
git clone https://github.com/Calebux/Portal-Subscription-manager
cd Portal-Subscription-manager
npm install
```

### 2. Install Hermes Agent

```bash
pip install hermes-agent
hermes setup
```

### 3. Configure environment

Create `~/.hermes/.env`:

```env
TELEGRAM_BOT_TOKEN=your_token
OPENAI_API_KEY=your_nous_api_key
OPENAI_BASE_URL=https://inference-api.nousresearch.com/v1
GATEWAY_ALLOW_ALL_USERS=true
```

### 4. Copy SubBot scripts

```bash
cp *.py *.sh ~/.hermes/
```

### 5. Start everything

```bash
# Terminal 1 — API bridge
node api-bridge.js

# Terminal 2 — Telegram gateway
hermes gateway run
```

### 6. Renewal alerts (optional cron)

```bash
# 9am daily
0 9 * * * python3 ~/.hermes/subscription-alerts.py
```

---

## File reference

| File | Description |
|------|-------------|
| `api-bridge.js` | Node.js REST bridge — connects web app to bot data |
| `public/` | Web dashboard served by Railway |
| `gmail-scanner.py` | IMAP scanner for 50+ subscription services |
| `subscription-alerts.py` | Renewal daemon — Telegram alert 3 days before charge |
| `export.py` | CSV generation and Telegram delivery |
| `currency.py` | Live FX rates, 6-hour cache |
| `sync-to-web.py` | Pushes local bot data to Railway after every update |
| `gateway-start.sh` | Clean startup wrapper for the Hermes gateway |

---

## What makes this different

Most subscription trackers are passive — connect a bank account, see a list. SubBot is **active**: it scans your Gmail, detects what you actually pay for, and takes action on your behalf. It runs as a persistent Telegram agent so it reaches you proactively — not just when you open an app.

The multi-currency support (NGN, GBP, EUR → USD) means it works for users that most Western SaaS tools ignore entirely.

The Celo pay-per-run model means anyone with a MiniPay wallet can use it without a credit card, subscription, or account — just send cUSD and the bot runs.

---

## License

MIT
