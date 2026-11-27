# Billing and onboarding (Phase 6)

## Plans

| Plan | Monthly | Yearly (10 months' price) | Assets | Members | Collectors |
| --- | --- | --- | --- | --- | --- |
| Starter | GH₵150 | GH₵1,500 | 5 | 3 | 0 |
| Business | GH₵350 | GH₵3,500 | 20 | 10 | 0 |
| Professional | GH₵750 | GH₵7,500 | 50 | 25 | 2 |
| Enterprise | Custom | Custom | Custom | Custom | Custom |

Prices are the proposed launch prices from the product plan, in Ghana cedis, and still need
validating with SMEs. Receipts are not VAT invoices. Tax registration and invoicing rules are an
owner decision before launch.

## How paying works

Billing is **prepaid**. Mobile Money can't be charged automatically, so there are no silent
renewals.

1. An owner chooses a plan, monthly or yearly, and **Mobile Money** (MTN MoMo, Telecel Cash,
   AirtelTigo Money) or **card** (Visa, Mastercard, Verve).
2. The API creates a pending payment with a random reference and opens Paystack's hosted
   checkout. Card numbers and wallet PINs never touch our servers.
3. On return, the web app asks the API to verify the payment. The API asks Paystack directly,
   and activates only if the amount and currency match what was ordered. Paystack's signed
   webhook (`charge.success`, HMAC-SHA512) does the same if the customer closes the browser
   first. Both paths are idempotent.
4. The subscription becomes active for 30 days (or 365). A receipt number (`SMECM-2026-00001`)
   is issued, and a PDF receipt can be downloaded from the billing history.

**Renewing early** adds the new period after the current one ends. **Changing plan** starts the
new plan now and converts unused paid time into extra days on the new plan (e.g. half a month of
Business is worth about 7 days of Professional). **Downgrades** are refused while usage exceeds
the smaller plan, and the message says what to remove.

Only owners (`billing:manage`) can pay. Admins, auditors and executives can see the plan, usage
and receipts (`billing:read`).

## Lifecycle

```
trialing ──pay──▶ active ──period ends──▶ past_due ──7-day grace──▶ expired
    └────────────── trial ends ───────────────────────────────────▶ expired
```

- New workspaces get a 14-day Starter trial without payment details.
- Owners and admins are emailed 7, 3 and 1 day before a trial or plan ends (once each), when
  payment becomes due, and when it expires. A banner appears in the app 3 days before a trial
  ends, and whenever payment is due.
- **Expired** organisations keep their data and their existing monitoring. Turning security
  monitoring off abruptly would put the customer at risk. They can't add assets, invite people,
  or create agent or collector enrolment tokens (`402 subscription_lapsed`) until they pay.
- The monitor worker runs the lifecycle sweep hourly. Statuses are also computed on read, so a
  lapsed plan is enforced even before the sweep runs.

## Development

`PAYMENT_PROVIDER=sandbox` (the default in development) replaces Paystack with a test checkout
page (`/billing/sandbox`) where you approve, decline or cancel. The API refuses to start with the
sandbox outside development. To try Paystack's own test mode, set `PAYMENT_PROVIDER=paystack`
and a `sk_test_…` key.

## Getting started checklist

`GET /onboarding` follows the business onboarding journey and is computed from live data:

| Step | Done when |
| --- | --- |
| Business profile | Industry and phone number are set |
| Add your website or domain | An active asset exists |
| Prove you control it | An asset is authorised (DNS or file proof) |
| See your first results | An asset has a successful check |
| Invite your team | Another member or an invitation exists |
| Two-step sign-in | The viewer has MFA on |
| Agent on your computers (optional) | An endpoint agent has enrolled |
| Alerts on your phone (optional) | The viewer has registered a phone |
| Choose a plan (optional, billing roles) | The subscription is paid |

New workspaces open on **Getting started**. Until the six required steps are done, the overview
shows the next steps and the navigation shows progress (for example 4/6). Admins can hide the
checklist for everyone.
