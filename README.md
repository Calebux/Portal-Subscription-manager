# SubBot — Autonomous AI Subscription Agent on Celo

> An AI agent that watches your subscriptions 24/7, reasons about your finances, acts without being asked, and funds itself from yield — your principal never touched.

**Live now →**
- Web app: [portal-subscription-manager-production.up.railway.app](https://portal-subscription-manager-production.up.railway.app)
- Telegram: [@SubmanagerAgentBot](https://t.me/SubmanagerAgentBot)
- SubBotVault: [0x48720eeDdCc1Cf3B2C613Dc093869a2332841e62](https://celoscan.io/address/0x48720eeDdCc1Cf3B2C613Dc093869a2332841e62)
- SubBotLog: [0x5bc06976e5b46fd624195EFdD0bFC45a73569003](https://celoscan.io/address/0x5bc06976e5b46fd624195EFdD0bFC45a73569003)

---

## The problem

The average person wastes **$300+ per year** on forgotten or overlapping SaaS subscriptions. AI tools especially — Claude Pro, ChatGPT Plus, Copilot, Cursor — stack up fast. Nobody audits them until the credit card statement arrives.

Every existing solution is passive: connect a bank account, see a list. You still have to figure out what to do.

SubBot is different. It figures out what to do for you — and tells you before you even think to ask.

---

## What makes this a real agent

Most "AI agents" are chatbots with a tool belt. You ask, they answer. The intelligence is reactive.

SubBot runs on a different model. Here's what it actually does:

### 1. It acts without being asked

Every morning at 9:05am, SubBot's digest agent wakes up independently. It loads every user's subscription portfolio, feeds it to the LLM, and asks: *is there anything worth telling this person today?*

If a subscription renews in 4 days, the agent sends a message. If the user just crossed their budget limit, the agent sends a message. If nothing is actionable, it stays silent — no noise, no check-ins. **The agent decides.**

```python
# agent-digest.py — runs daily via launchd, no user prompt required
for user_id in get_all_user_ids():
    briefing = generate_briefing(user_id, user_data)  # LLM decides: send or null
    if briefing:
        send_telegram(user_id, briefing)
```

### 2. The LLM does the reasoning — not Python formulas

Old approach: `if health_score < 50: verdict = "cancel"`. Hardcoded thresholds. Same output for every user.

New approach: the full subscription portfolio — costs, renewal dates, overlaps, usage health, budget — goes directly to the LLM. It reasons contextually:

> *"You have Claude Pro ($20), ChatGPT Plus ($20), and GitHub Copilot ($10). All three are AI tools. If you're a developer, Copilot has the highest ROI of the three. Cancel ChatGPT Plus before March 28 to avoid another charge — that's $240/year back."*

That's not a formula. That's judgment.

### 3. Every decision is logged on the Celo blockchain

When SubBot makes a recommendation — cancel, negotiate, audit complete — it doesn't just send a Telegram message. It writes an immutable record to a smart contract on Celo mainnet:

```solidity
// SubBotLog.sol — deployed at 0x5bc06976e5b46fd624195EFdD0bFC45a73569003
event DecisionLogged(
    address indexed agent,
    bytes32 indexed userHash,   // privacy-preserving
    string  action,             // "recommend_cancel", "audit_complete", etc.
    uint256 amountSavedUSD,     // estimated saving in cents
    uint256 timestamp
);
```

Every agent action creates a transaction. The agent's track record — what it recommended, when, how much it identified in savings — lives on-chain permanently. You can verify it. No one can change it.

### 4. It funds itself from real DeFi yield — your principal is untouchable

This is the economic model that makes SubBot a genuine real-world agent.

**Old model:** pay-per-run. Every action costs cUSD from your wallet. You top up manually. The agent is a service you pay for.

**New model:** deposit once into `SubBotVault`. The vault immediately supplies your cUSD to **Aave v3 on Celo**. Real borrowers pay real interest. The agent harvests that yield and spends it on operations — never your principal.

```
User deposits 5 cUSD
         │
         ▼
   SubBotVault.sol  →  Aave v3 Pool (Celo mainnet)
         │
         ├── principal: 5.000 cUSD  ← IN AAVE. Agent can NEVER touch this.
         │
         └── real yield from Aave borrowers (~5% APY market rate)
               ├── ~0.021 cUSD/month generated
               └── ~0.021 cUSD/month covers scans, audits, exports
                             ↑
                   self-sustaining at just $5. forever.
```

The yield is not simulated. It comes from open-market lending on Aave v3 — the same protocol managing billions in deposits globally. The vault tracks yield using Aave's cumulative interest index: zero rounding error, no oracle, no trust required. `spendCredits()` reverts if credits are zero. There is no code path that touches `principal`.

```solidity
// deposit → straight into Aave, earning real yield immediately
AAVE.supply(address(CUSD), amount, address(this), 0);

// yield uses Aave's own index — pure on-chain math, no oracle
uint256 yield = principal * (currentIndex - lastIndex) / lastIndex;
```

| Action | Cost (from yield) |
|--------|------|
| Daily digest | **Free** |
| Renewal alerts | **Free** |
| Gmail scan | 0.002 cUSD |
| LLM portfolio audit | 0.002 cUSD |
| CSV export | 0.001 cUSD |

At just 5 cUSD deposited: Aave yield covers ~10 scans + ~10 audits + unlimited digests per month. The agent pays for itself.

**No wallet? No problem.** Users who don't want to deposit can still use SubBot pay-per-run. The agent checks which mode you're in and handles it automatically:

| Mode | How it works |
|------|-------------|
| **Vault** | Deposit 5 cUSD once → Aave earns yield → agent spends from yield. Zero prompts, runs forever. |
| **Pay-per-run** | No deposit needed. Bot sends you the cost before each operation, you confirm and pay. |

Every pay-per-run prompt includes a one-tap option to switch to vault mode — users naturally upgrade when they see the value.

Works natively with **MiniPay** — no wallet extension needed. Multi-currency support (NGN, GBP, EUR → USD) means it works for users most Western fintech tools ignore.

---

## What the agent does in practice

### Morning (9:00am daily — no user interaction)
- Renewal alert daemon scans all users for subscriptions due in 3 days or 1 day
- Digest agent runs at 9:05am: LLM reviews each user's portfolio, sends a personalized briefing only if something actionable is found
- Every alert and digest that triggers a recommendation is logged on-chain

### Weekly (Monday 8:00am — no user interaction)
- Full LLM portfolio re-analysis for all users
- Overlaps, forgotten services, quick wins, negotiation candidates — all reasoned by the model, not calculated by formulas
- Results pushed to user via Telegram and synced to the web dashboard

### On demand (user triggers)
- Gmail IMAP scan — auto-detects subscriptions across 50+ known billing patterns
- `/audit` — runs `llm-analyze.py`, LLM produces a full personalized report
- `/negotiate [service]` — LLM generates a personalized retention email using the user's real leverage (tenure, competitor services, health score, expected discount)
- CSV export — full report delivered to Telegram

---

## Architecture

```
                    ┌─────────────────────────────────┐
                    │   AUTONOMOUS AGENT LAYER         │
                    │                                  │
  9:00am daily ───► │  subscription-alerts.py          │
  9:05am daily ───► │  agent-digest.py    (LLM loop)   │
  Mon 8:00am  ───► │  llm-analyze.py     (LLM audit)  │
                    └──────────────┬──────────────────┘
                                   │ decisions + vault ops
                                   ▼
                    ┌─────────────────────────────────┐
                    │   CELO MAINNET                   │
                    │                                  │
                    │   SubBotVault.sol                │
                    │   0xA36C58...8726                │
                    │   — user principal (locked)      │
                    │   — 10% APY yield accrual        │
                    │   — agent spends from yield only │
                    │                                  │
                    │   SubBotLog.sol                  │
                    │   0x5bc069...3003                │
                    │   — immutable decision log       │
                    │   — savings tracker              │
                    └─────────────────────────────────┘

Telegram user
      │
      ▼
Hermes Gateway  (Hermes-4-70B · Nous inference API)
      │
      ├── llm-analyze.py      ← LLM portfolio reasoning
      ├── negotiate.py        ← LLM negotiation strategy
      ├── gmail-scanner.py    ← IMAP scan, 50+ services
      ├── export.py           ← CSV → Telegram
      ├── currency.py         ← Live FX, 6hr cache
      └── sync-to-web.py      ← Push to Railway
           │
           ▼
      API Bridge  (Node.js · Railway)
           │
           ├── POST /log-decision  ← writes to Celo contract
           ├── POST /audit         ← triggers llm-analyze.py
           ├── GET  /analysis      ← returns LLM results
           ├── POST /negotiate     ← triggers negotiate.py
           ├── GET  /balance       ← cUSD balance via RPC
           └── serves public/      ← web dashboard
                │
                ▼
           Web Dashboard  (Vanilla JS · Tailwind · Railway)


Celo Blockchain
      ├── cUSD payments     ← pay-per-run credits
      └── SubBotLog.sol     ← agent decision audit trail
```

---

## On-chain proof

**SubBotVault** — [`0x48720eeDdCc1Cf3B2C613Dc093869a2332841e62`](https://celoscan.io/address/0x48720eeDdCc1Cf3B2C613Dc093869a2332841e62)

The yield vault. User deposits are immediately supplied to Aave v3 on Celo, earning real market-rate yield from borrowers. The agent calls `spendCredits()` for every operation — if yield is insufficient, the call reverts. Principal is locked in Aave; no code path can spend it. At 5 cUSD deposited, yield covers all agent operations indefinitely.

**SubBotLog** — [`0x5bc06976e5b46fd624195EFdD0bFC45a73569003`](https://celoscan.io/address/0x5bc06976e5b46fd624195EFdD0bFC45a73569003)

The decision audit trail. Every LLM recommendation — cancel, negotiate, audit complete — creates a transaction with a privacy-preserving user hash, action type, and estimated savings. Running total of savings identified across all users is publicly readable.

This isn't a demo. Both contracts are deployed, the agent is running, and activity is accumulating on-chain.

---

## Quick demo (3 paths)

**Option A — Web app (2 minutes, no setup):**
1. Open [the web app](https://portal-subscription-manager-production.up.railway.app)
2. Tap **Get Started**
3. Add a subscription manually with **+**
4. Watch Dashboard, Audit, and Alerts update in real time

**Option B — Full Telegram flow:**
1. Message [@SubmanagerAgentBot](https://t.me/SubmanagerAgentBot)
2. Send `/myid` → bot replies with your Telegram ID
3. Open the web app, enter your ID → your data loads into the dashboard
4. Ask: `"audit my subscriptions"` or `"what am I paying for"`

**Option C — Gmail scan (full power):**
1. Tell the bot you want to scan your Gmail
2. Get a Google App Password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Share your email + App Password with the bot
4. Agent scans 120 days of email, auto-detects all subscriptions, syncs to web dashboard

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
pip install hermes-agent && hermes setup
```

### 2. Configure environment

Create `~/.hermes/.env`:

```env
TELEGRAM_BOT_TOKEN=your_token
OPENAI_API_KEY=your_nous_api_key
OPENAI_BASE_URL=https://inference-api.nousresearch.com/v1
GATEWAY_ALLOW_ALL_USERS=true
```

Create `.env` in project root (for API bridge + on-chain logging):

```env
AGENT_PRIVATE_KEY=0x...          # wallet with CELO for gas
LOG_CONTRACT_ADDRESS=0x5bc06976e5b46fd624195EFdD0bFC45a73569003
```

### 3. Deploy your own contract (optional — or use the existing one)

```bash
node compile-contract.js         # compiles SubBotLog.sol
node deploy-contract.js          # deploys to Celo mainnet
```

### 4. Copy agent scripts and start

```bash
cp *.py ~/.hermes/

# Terminal 1 — API bridge (enables on-chain logging)
node api-bridge.js

# Terminal 2 — Telegram agent
hermes gateway run
```

### 5. Install autonomous agents (macOS)

```bash
# Registers daily digest, renewal alerts, and weekly analysis
launchctl load ~/Library/LaunchAgents/com.subbot.alerts.plist
launchctl load ~/Library/LaunchAgents/com.subbot.digest.plist
launchctl load ~/Library/LaunchAgents/com.subbot.analyze.plist
```

---

## File reference

| File | What it does |
|------|-------------|
| `agent-digest.py` | **Autonomous daily agent** — LLM reviews all users, sends briefings without being asked |
| `llm-analyze.py` | **LLM portfolio reasoning** — replaces hardcoded formulas with contextual judgment |
| `negotiate.py` | **LLM negotiation strategy** — personalized retention emails using real user leverage |
| `contracts/SubBotLog.sol` | **On-chain decision log** — immutable audit trail on Celo mainnet |
| `subscription-alerts.py` | Renewal daemon — Telegram alert 3 and 1 day before charges |
| `gmail-scanner.py` | IMAP scanner — detects subscriptions across 50+ billing patterns |
| `api-bridge.js` | Node.js bridge — `/log-decision` writes to Celo, `/audit` delegates to LLM |
| `export.py` | CSV generation + Telegram delivery |
| `currency.py` | Live FX rates (NGN, GBP, EUR → USD), 6-hour cache |
| `public/` | Web dashboard — Material Design 3, real-time sync via Railway |

---

## License

MIT
