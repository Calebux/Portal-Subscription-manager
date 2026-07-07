# SubBot Monetization Plan

## Current state

The only monetization mechanism today is G$ (GoodDollar UBI) micro-payments — fractions of a cent per scan/audit/negotiate action, currently paused entirely for a free beta. Even switched back on, this produces effectively $0 in real revenue: the amounts are sized to be affordable from daily UBI claims, not to capture value from savings delivered. It also caps the addressable market to GoodDollar/Celo users, which is a small fraction of anyone who has subscriptions to manage.

## Recommended model: success fee on confirmed savings

Charge a percentage of savings only when SubBot's action demonstrably saved the user money — the same model Rocket Money and Trim use, but with a verifiable audit trail SubBot already has (`SubBotLog.sol` + `decision-log.json`).

**Why this over a flat subscription fee:** a flat $5-10/mo fee competes with the very subscriptions the app is trying to help people cut, and undersells the product's actual value (someone whose SubBot found $80/mo in cancellable overlap will happily pay a cut of that; they may balk at a fixed fee before proving the app works for them). Success-fee pricing also means SubBot only gets paid when it delivers, which is a stronger trust signal for a new product.

**Structure:**
- **Free tier (G$ UBI):** unchanged — crypto-native users pay in G$ for individual actions (scan, audit, negotiate, export). Keep this as the low-friction, no-card entry point and the differentiated "an agent that pays for itself" story.
- **Success-fee tier (Stripe):** for any user, whether or not they have a wallet. When a subscription's `status` flips from `active` to `cancelled` (via the existing `/update-sub` confirm-cancellation flow) or a negotiation is confirmed to have reduced `monthly_cost`, charge a one-time fee equal to 30–50% of one month's saving via a Stripe payment intent, with the exact percentage as an experiment variable.

## Verification mechanism (already half-built)

Every negotiation/cancellation recommendation already logs `amountSavedUSD` through `/log-decision` into `decision-log.json` and (when the on-chain path is live) `SubBotLog.sol`. The success fee is charged against a *confirmed* entry in that log, not the raw recommendation — i.e., only after the user explicitly marks a subscription cancelled or a negotiated discount as accepted (the existing `confirmCancellation()` flow in `popup.js` already captures this moment). This means the billing trigger is a state transition SubBot already detects, not new instrumentation.

## Implementation sketch

1. **Stripe Connect/Payments setup** — one-time: create a Stripe account, add `STRIPE_SECRET_KEY` to `.env`, add `stripe` npm dependency to `api-bridge.js`.
2. **Payment method on file** — new `POST /billing/setup-intent` returning a Stripe SetupIntent client secret; frontend collects a card via Stripe Elements once, stored as a Stripe Customer + PaymentMethod (never touches SubBot's own servers — same "don't handle card data directly" principle already followed for Web3Auth).
3. **Charge on confirmed savings** — extend the existing cancellation-confirmation and negotiation-acceptance code paths (`confirmCancellation()` in `popup.js`, the `/update-sub` handler) to also call a new `POST /billing/charge-savings` endpoint, which computes the fee from the logged `amountSavedUSD`, creates a Stripe PaymentIntent against the stored payment method, and records the charge in `decision-log.json` alongside the original savings entry.
4. **Failure handling** — if the charge fails (expired card, insufficient funds), don't block the cancellation confirmation itself; log it as `feeStatus: "failed"` and retry or prompt for an updated card on next login. Never let a billing failure make SubBot look like it's blocking the user from managing their own subscriptions.
5. **Transparency** — show the fee *before* the user confirms a cancellation/negotiation ("Confirming this will save you $9.99/mo — SubBot's fee is $4.00, charged once"), not as a surprise afterward.

## Open questions to resolve before building

- **Fee percentage and cap** — 30-50% of one month's saving is the Rocket-Money-style default; worth testing a lower percentage against conversion once there's real usage data.
- **Refund policy** — what happens if a user re-subscribes to a "cancelled" service a week later? Probably: no refund, since the fee is for the successful action taken, not a savings guarantee.
- **International cards / currencies** — the dashboard already supports NGN/GBP/EUR/KES/GHS/ZAR; Stripe's coverage of these varies by country and may need a fallback (G$ tier) for markets Stripe doesn't serve well — which nicely keeps the free tier's original purpose (serving users mainstream fintech ignores) intact rather than replacing it.
- **Legal** — success-fee billing on financial recommendations may brush up against financial-advice regulation in some jurisdictions depending on how the negotiation/cancellation copy is worded; worth a quick legal read before charging real money at scale.
