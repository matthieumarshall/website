# Quickstart: Team Entries (Local Dev)

**Date**: 2026-06-07 | **Plan**: [plan.md](plan.md)

---

## Prerequisites

- Python 3.11+ with `uv` installed
- Node.js 18+ (for Playwright)
- A Stripe account (free) with test API keys
- The EA staging certificate file (configure with `EA_CERT_PATH`) — rename from `.pfx.txt` extension

---

## 1. Install Dependencies

```powershell
# Python deps (includes stripe and weasyprint)
uv add stripe weasyprint httpx

# WeasyPrint system deps — Ubuntu/Debian VPS only
# sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b

# Node/Playwright
npm install
npx playwright install chromium
```

---

## 2. Configure Environment Variables

Add to `.env` (never commit this file):

```env
# Stripe test keys (get from dashboard.stripe.com → Developers → API keys)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...   # from: stripe listen --forward-to localhost:8000/webhooks/stripe

# England Athletics TRAPI (staging)
EA_CALL_KEY=<staging EA call key>
EA_CALL_SECRET=<staging EA call secret>
EA_CERT_PATH=data/<staging-cert>.pfx
EA_CERT_PASSWORD=<staging cert password>
EA_STAGING=true   # set to false in production

# Existing app vars
SECRET_KEY=dev-secret-key-not-for-production
```

---

## 3. Apply Migrations

```powershell
uv run python scripts/_apply_migrations.py
```

This applies all numbered migrations including the new `0013`–`0018` tables.

---

## 4. Seed Test Data

Run the dev seed script (to be created as `scripts/seed_entries_dev.py`):

```powershell
uv run python scripts/seed_entries_dev.py
```

This creates:
- A test season with `season_entry_config` (entries open, EA reference date 2025-08-31)
- 5 fixtures with known dates (future dates so deadline check works)
- Price tiers: 5→£15/£8, 4→£12/£6.50, 3→£9/£5, 2→£6/£3.50, 1→£3/£2
- One admin user: `admin / admin123`
- One club: Oxford City AC (EA club ID: `1765` — use the staging test club)
- One club manager user: `oxc_manager / manager123`

---

## 5. Start the Dev Server

```powershell
uv run uvicorn website.main:app --reload
```

---

## 6. Set Up Stripe Webhook Forwarding

In a second terminal:

```powershell
# Install Stripe CLI if not already: https://stripe.com/docs/stripe-cli
stripe login
stripe listen --forward-to localhost:8000/webhooks/stripe
```

Copy the `whsec_...` webhook signing secret printed by the CLI into `.env` as `STRIPE_WEBHOOK_SECRET`. Restart the dev server.

---

## 7. Happy Path — Manual Test

1. Visit `http://localhost:8000` and log in as `oxc_manager / manager123`.
2. Navigate to **Entries**.
3. Select the test season.
4. The app calls the EA staging API — you should see a list of athletes for club ID `1765`.
5. Select 2–3 athletes and click **Preview**.
6. Verify the price breakdown is correct (junior vs adult, pro-rata).
7. Click **Pay** — you are redirected to Stripe Checkout.
8. Use Stripe's test card: `4000 0082 6000 0000` (UK Visa, succeeds immediately).
9. After payment, you are redirected to the success page.
10. Download the PDF receipt and verify the content.

**Test BACS flow**:
- On Stripe Checkout, select "Pay by bank account (BACS Direct Debit)".
- Use sort code `20-00-00` and account number `55779911` (Stripe test BACS details).
- After completing, batch should be in `payment_initiated` state.
- In a terminal: `stripe trigger charge.succeeded` — batch should move to `paid`.

---

## 8. Admin — Set Entry Prices

1. Log in as `admin / admin123`.
2. Navigate to **Admin → Entries → [season] → Pricing**.
3. Verify the seeded price tiers appear.
4. Change the junior price for "5 fixtures remaining" and save.
5. Log back in as manager, start a new entry flow, and confirm the updated price appears.

---

## 9. Unit Tests

```powershell
uv run pytest tests/unit/test_entries.py -v
uv run pytest tests/unit/test_payments.py -v
uv run pytest tests/unit/test_receipts.py -v
```

Key test files to create:
- `tests/unit/test_entries.py` — EA client (mocked with `httpx`), age category calc, eligibility logic
- `tests/unit/test_payments.py` — Stripe session creation (mocked), webhook handler, batch state transitions
- `tests/unit/test_receipts.py` — PDF generation (WeasyPrint), receipt template rendering

---

## 10. Playwright UI Tests

```powershell
npx playwright test tests/ui/test_entries.spec.ts
```

Key scenarios to cover:
- Full entry journey: login → season select → athlete select → preview → payment → receipt
- BACS payment flow (mock Stripe in Playwright)
- Locked entries after deadline
- Admin pricing update
- Read-only cross-club view

---

## Troubleshooting

| Problem | Solution |
|---|---|
| EA API returns 401 | Check `EA_CALL_KEY` / `EA_CALL_SECRET` env vars; verify cert path |
| EA API returns SSL error | Ensure cert is `.pfx` not `.pfx.txt`; check `EA_CERT_PASSWORD` |
| Stripe webhook 400 | Stripe CLI not running or `STRIPE_WEBHOOK_SECRET` not set |
| WeasyPrint import error | Install system deps: `libpango-1.0-0 libpangoft2-1.0-0` (Linux only) |
| Race numbers not assigned | Check webhook handler is receiving `charge.succeeded` or `checkout.session.completed` |
