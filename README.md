# SubBot — Autonomous AI Subscription Agent powered by GoodDollar

> An AI agent that watches your subscriptions 24/7, reasons about your finances, acts without being asked — and pays for itself using your daily **G$ UBI earnings**. Your principal stays untouched.

**Live now →**
- Web app: [portal-subscription-manager-production.up.railway.app](https://portal-subscription-manager-production.up.railway.app)
- Telegram: [@SubmanagerAgentBot](https://t.me/SubmanagerAgentBot)
- SubBotVault: [0x48720eeDdCc1Cf3B2C613Dc093869a2332841e62](https://celoscan.io/address/0x48720eeDdCc1Cf3B2C613Dc093869a2332841e62)
- SubBotLog: [0x5bc06976e5b46fd624195EFdD0bFC45a73569003](https://celoscan.io/address/0x5bc06976e5b46fd624195EFdD0bFC45a73569003)

---

## Why GoodDollar + SubBot

[GoodDollar](https://gooddollar.org) distributes free **G$** to verified members every day — a universal basic income on Celo. Most people collect it and don't know what to do with it.

SubBot gives G$ a job: **pay for your AI subscription manager with UBI you earned for free.**

Every scan, audit, and negotiation email the agent runs costs a tiny fraction of G$. If you claim your daily G$ and never touch it, SubBot can run indefinitely — entirely self-funded from income you would have ignored.

This is what financial inclusion looks like in practice. Not a crypto wallet you have to top up. An agent that earns its own keep from your daily UBI, while saving you hundreds of dollars a year on forgotten subscriptions.

---

## The problem

The average person wastes **$300+ per year** on forgotten or overlapping SaaS subscriptions. AI tools especially — Claude Pro, ChatGPT Plus, Copilot, Cursor — stack up fast. Nobody audits them until the credit card statement arrives.

Every existing solution is passive: connect a bank account, see a list. You still have to figure out what to do.

SubBot is different. It figures out what to do for you — and tells you before you even think to ask.

---

## What makes this a real agent

Most "AI agents" are chatbots with a tool belt. You ask, they answer. The intelligence is reactive.

SubBot runs on a different model:

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

### 3. Every decision is logged on Celo

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

Every agent action creates a transaction. The agent's track record lives on-chain permanently. You can verify it. No one can change it.

### 4. It pays for itself — from your G$ UBI

This is the model that makes SubBot genuinely useful for GoodDollar users.

**Old model:** pay-per-run in cUSD. You top up manually. The agent is a service you pay for.

**New model:** your daily G$ UBI claims accumulate in `SubBotVault`. The agent spends from that balance — never from your principal. You collect G$ for free every day; the agent converts the micro-amounts into real AI work.

```
GoodDollar daily claim  →  G$ arrives in your wallet
         │
         ▼
   SubBotVault.sol  →  G$ balance accrues
         │
         ├── principal: your G$ ← Agent can NEVER touch this.
         │
         └── daily UBI yield covers all operations:
               ├── scans, audits, exports
               └── self-sustaining indefinitely from free UBI
```

Alternatively, users who want maximum yield can deposit cUSD into the vault, which is immediately supplied to **Aave v3 on Celo**, earning real market-rate interest from borrowers. The agent harvests that yield for operations — your deposit stays locked in Aave.

```solidity
// deposit → straight into Aave, earning real yield immediately
AAVE.supply(address(CUSD), amount, address(this), 0);

// yield tracked using Aave's own interest index — no oracle, no trust
uint256 yield = principal * (currentIndex - lastIndex) / lastIndex;
```

| Action | Cost |
|--------|------|
| Daily digest | **Free** |
| Renewal alerts | **Free** |
| Gmail scan | ~0.002 G$ / cUSD |
| LLM portfolio audit | ~0.002 G$ / cUSD |
| CSV export | ~0.001 G$ / cUSD |

**One week of daily G$ claims covers a month of full operation.** No wallet top-ups. No card on file. Just UBI doing its job.

**No G$? No problem.** SubBot also runs pay-per-run — the bot tells you the cost before each operation and you confirm. Or deposit any amount of cUSD to activate Aave yield mode.

| Mode | How it works |
|------|-------------|
| **G$ UBI** | Claim daily G$ → agent spends micro-amounts → runs forever from free income |
| **Vault (cUSD)** | Deposit once → Aave earns yield → agent spends from yield. Zero prompts. |
| **Pay-per-run** | No deposit. Bot sends cost before each operation, you confirm. |

Works natively with **MiniPay** — the GoodDollar wallet built into Opera Mini. No browser extension needed. Multi-currency support (NGN, GBP, EUR → USD) means it works for users most Western fintech tools ignore — exactly the GoodDollar demographic.

---

## Login with Web3Auth

SubBot now supports **Web3Auth** authentication — no Telegram ID required, no seed phrase, no wallet setup.

Sign in with Google, Twitter, Discord, or email. One click. Web3Auth issues a verified JWT; SubBot validates it against the Web3Auth JWKS endpoint and creates an isolated user account automatically.

This means GoodDollar users who already have a GoodDollar identity can sign into SubBot with the same social login — no extra accounts, no friction.

**Login flow:**
1. Click **Login with Web3Auth** in the extension or web app
2. Pick your provider (Google / Twitter / Discord / email magic link)
3. Web3Auth handles OAuth — no keys, no custody
4. SubBot verifies your identity token via `https://api-auth.web3auth.io/.well-known/jwks.json`
5. Your subscription data is isolated to your verified identity

---

## What the agent does in practice

### Morning (9:00am daily — no user interaction)
- Renewal alert daemon scans all users for subscriptions due in 3 or 1 day
- Digest agent at 9:05am: LLM reviews each user's portfolio, sends a personalized briefing only if something actionable is found
- Every alert and digest that triggers a recommendation is logged on Celo

### Weekly (Monday 8:00am — no user interaction)
- Full LLM portfolio re-analysis for all users
- Overlaps, forgotten services, quick wins, negotiation candidates — all reasoned by the model, not calculated by formulas
- Results pushed to user via Telegram and synced to the web dashboard

### On demand (user triggers)
- Gmail IMAP scan — auto-detects subscriptions across 50+ known billing patterns
- `/audit` — LLM produces a full personalized report
- `/negotiate [service]` — LLM generates a personalized retention email using the user's real leverage (tenure, competitor services, health score, expected discount)
- CSV export — full report delivered to Telegram

---

## Architecture

```
                    ┌─────────────────────────────────┐
                    │   AUTONOMOUS AGENT LAYER          │
                    │                                   │
  9:00am daily ───► │  subscription-alerts.py           │
  9:05am daily ───► │  agent-digest.py    (LLM loop)    │
  Mon 8:00am  ───► │  llm-analyze.py     (LLM audit)   │
                    └──────────────┬───────────────────┘
                                   │ decisions + vault ops
                                   ▼
                    ┌─────────────────────────────────┐
                    │   CELO MAINNET                    │
                    │                                   │
                    │   SubBotVault.sol                 │
                    │   — G$ UBI balance (daily claims) │
                    │   — cUSD → Aave v3 yield (alt)    │
                    │   — agent spends from yield only  │
                    │                                   │
                    │   SubBotLog.sol                   │
                    │   — immutable decision log        │
                    │   — savings tracker               │
                    │                                   │
                    │   GoodDollar G$ Token             │
                    │   — daily UBI distribution        │
                    │   — micro-payment for operations  │
                    └─────────────────────────────────┘

GoodDollar / Telegram user
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
           ├── POST /auth/verify-web3auth  ← JWKS JWT verification
           ├── POST /log-decision          ← writes to Celo contract
           ├── POST /audit                 ← triggers llm-analyze.py
           ├── GET  /analysis              ← returns LLM results
           ├── POST /negotiate             ← triggers negotiate.py
           ├── GET  /balance               ← G$ / cUSD balance via RPC
           └── serves public/              ← web dashboard
                │
                ▼
           Web Dashboard + Chrome Extension
           (Vanilla JS · Tailwind · Railway · MiniPay-ready)
```

---

## On-chain proof

**SubBotVault** — [`0x48720eeDdCc1Cf3B2C613Dc093869a2332841e62`](https://celoscan.io/address/0x48720eeDdCc1Cf3B2C613Dc093869a2332841e62)

The yield vault. cUSD deposits are immediately supplied to Aave v3 on Celo. G$ UBI deposits accrue as a spendable balance. The agent calls `spendCredits()` for every operation — if the balance is insufficient, the call reverts. Principal is locked; no code path can spend it.

- **Aave v3 Pool (Celo)** — [`0x3E59A31363E2ad014dcbc521c4a0d5757d9f3402`](https://celoscan.io/address/0x3E59A31363E2ad014dcbc521c4a0d5757d9f3402)
- **cUSD** — [`0x765DE816845861e75A25fCA122bb6898B8B1282a`](https://celoscan.io/address/0x765DE816845861e75A25fCA122bb6898B8B1282a)
- **G$ (GoodDollar)** — [`0x62B8B11039FcfE5aB0C56E502b1C372A3d2a9c14`](https://celoscan.io/address/0x62B8B11039FcfE5aB0C56E502b1C372A3d2a9c14)
- **aUSDm (Aave receipt token)** — [`0xBba98352628B0B0c4b40583F593fFCb630935a45`](https://celoscan.io/address/0xBba98352628B0B0c4b40583F593fFCb630935a45)
- **First deposit tx** — [`0xabfe727070c4b54bb58077dd41f0c7a3836ae5e444dca57141882d8810568086`](https://celoscan.io/tx/0xabfe727070c4b54bb58077dd41f0c7a3836ae5e444dca57141882d8810568086)

**SubBotLog** — [`0x5bc06976e5b46fd624195EFdD0bFC45a73569003`](https://celoscan.io/address/0x5bc06976e5b46fd624195EFdD0bFC45a73569003)

Immutable decision audit trail. Every LLM recommendation creates a transaction with a privacy-preserving user hash, action type, and estimated savings. Running total of savings identified is publicly readable on-chain.

---

## Quick demo (3 paths)

**Option A — Web app (2 minutes, no setup):**
1. Open [the web app](https://portal-subscription-manager-production.up.railway.app)
2. Click **Login with Web3Auth** — sign in with Google or email
3. Add a subscription manually with **+**
4. Watch Dashboard, Audit, and Alerts update in real time

**Option B — GoodDollar + Telegram flow:**
1. Claim your daily G$ at [gooddollar.org](https://gooddollar.org) or in MiniPay
2. Message [@SubmanagerAgentBot](https://t.me/SubmanagerAgentBot)
3. Send `/myid` → bot replies with your Telegram ID
4. Open the web app, enter your ID → your data loads into the dashboard
5. Ask: `"audit my subscriptions"` or `"what am I paying for"`
6. G$ micro-payments cover every operation automatically

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
- Web3Auth client ID (for auth)

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

Create `.env` in project root:

```env
AGENT_PRIVATE_KEY=0x...          # wallet with CELO for gas
LOG_CONTRACT_ADDRESS=0x5bc06976e5b46fd624195EFdD0bFC45a73569003
WEB3AUTH_CLIENT_ID=BCkzpmFTjh9pTHe7LGNlrg_jo22W7DNHGkkZSbgrQlOeSf7AzRZ1qdZXDRyxplEq5knOTiCjhH-uga6tpnASP1o
```

### 3. Deploy your own contracts (optional)

```bash
node compile-contract.js         # compiles SubBotLog.sol + SubBotVault.sol
node deploy-contract.js          # deploys to Celo mainnet
```

### 4. Start the bridge and agent

```bash
cp *.py ~/.hermes/

# Terminal 1 — API bridge
node api-bridge.js

# Terminal 2 — Telegram agent
hermes gateway run
```

### 5. Install autonomous agents (macOS)

```bash
launchctl load ~/Library/LaunchAgents/com.subbot.alerts.plist
launchctl load ~/Library/LaunchAgents/com.subbot.digest.plist
launchctl load ~/Library/LaunchAgents/com.subbot.analyze.plist
```

---

## File reference

| File | What it does |
|------|-------------|
| `agent-digest.py` | **Autonomous daily agent** — LLM reviews all users, sends briefings without being asked |
| `llm-analyze.py` | **LLM portfolio reasoning** — contextual judgment over all subscriptions |
| `negotiate.py` | **LLM negotiation strategy** — personalized retention emails with real user leverage |
| `contracts/SubBotLog.sol` | **On-chain decision log** — immutable audit trail on Celo |
| `contracts/SubBotVault.sol` | **G$/cUSD vault** — Aave yield + G$ UBI balance for agent operations |
| `extension/web3auth-login.html` | **Web3Auth login tab** — Google/Twitter/Discord/email login for the Chrome extension |
| `subscription-alerts.py` | Renewal daemon — Telegram alert 3 and 1 day before charges |
| `gmail-scanner.py` | IMAP scanner — detects subscriptions across 50+ billing patterns |
| `api-bridge.js` | Node.js bridge — JWT verification, Celo logging, Aave vault ops, web dashboard |
| `export.py` | CSV generation + Telegram delivery |
| `currency.py` | Live FX rates (NGN, GBP, EUR → USD), 6-hour cache |
| `public/` | Web dashboard — Material Design 3, MiniPay-ready, real-time sync via Railway |

---

## License

MIT
