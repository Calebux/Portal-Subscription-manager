# SubBot — Judge Demo Script

Bot link: Share your `t.me/YourBotName` with judges.

---

## Flow (5 minutes)

### 1. Onboarding (30 seconds)
Send any message to the bot. It replies with the welcome + 4 options.

### 2. Gmail Scan (option 1)
- Say `1`
- Bot explains App Password and asks for Gmail + password
- Provide credentials → bot scans inbox, reports subscriptions found
- **Shows:** service names, amounts, currencies, renewal dates

### 3. Full Audit (1 minute)
Say: `audit my subscriptions`

Bot responds with:
- Total monthly spend in USD (multi-currency normalized)
- Each subscription with health score
- Overlaps and redundancies flagged
- Monthly budget % used (if budget set)
- Projected annual spend
- Quick wins list with cancel URLs

### 4. Set a Budget
Say: `set my budget to $100/month`

Bot saves it and shows how much of the budget is already used.

### 5. Token ROI Analysis (option 4)
Say: `show my token usage`

Bot asks for API keys (OpenAI / Anthropic / OpenRouter).
Provide one and it shows:
- Actual API spend this month
- Token counts by model
- Whether subscription is worth it vs API-only
- Break-even analysis

### 6. Renewal Alert Demo
Say: `what renews this month`

Bot lists upcoming renewals with amounts and direct cancel links.

### 7. Export
Say: `export my subscriptions`

Bot sends a CSV file directly to Telegram with full audit data.

### 8. Cancel + Negotiate
Say: `cancel [service name]`

Bot asks if you want to try for a discount first, drafts a retention email, offers to send it.

---

## Key Talking Points

- **Multi-user**: every person who DMs the bot gets their own isolated data
- **Multi-currency**: NGN, GBP, EUR all normalized to USD in reports
- **Token ROI**: unique feature — tells you if your LLM subscription is worth it based on actual usage
- **Automated alerts**: renewal daemon fires Telegram alerts 3 days + 1 day before each charge
- **Full lifecycle**: detect → audit → negotiate → cancel → track savings

---

## Commands Cheat Sheet

| Say this | Does this |
|----------|-----------|
| `audit` | Full subscription audit |
| `scan my email` | Gmail IMAP scan |
| `set budget $100` | Set monthly budget |
| `token usage` | API token ROI analysis |
| `what renews this month` | Upcoming renewals |
| `cancel [service]` | Negotiation + cancellation flow |
| `export` | Send CSV report to Telegram |
| `add [service] $X/month` | Manually add a subscription |
