# Environment Setup Guide

Three environments are defined for this project. Each uses a different combination of England Athletics (EA) API and Stripe credentials to balance realism against safety and speed.

---

## Quick Reference

| | Local Dev | Testing (CI / local) | Production |
|---|---|---|---|
| **EA endpoint** | Production live API | EA staging API | Production live API |
| **EA credentials** | Production cert + key | Staging cert + key | Production cert + key |
| `EA_STAGING` | `false` | `true` | `false` |
| `EA_TEST_MODE` | unset / `false` | unset (CI hits staging) | unset / `false` |
| **Stripe** | Test keys (`sk_test_…`) | Test keys (`sk_test_…`) | Live keys (`sk_live_…`) |
| `PRODUCTION` | `false` | `false` | `true` |
| **Database** | `data/app.duckdb` | `:memory:` (unit) / `test_ui.duckdb` (UI) | `/home/manager/website/data/app.duckdb` |
| **Secret key** | Any string | Any string | Strong random, required |

---

## a) Local Development

**Goal:** Realistic data against the live EA API, payments safely in Stripe test mode.

### How it works

- The app starts with `PRODUCTION=false`, so HTTPS-only cookies and HSTS are disabled.
- `EA_STAGING=false` points the httpx client at `TrinityAPI.myathletics.uk` (production EA).
- Stripe uses test-mode keys, so no real money moves; use [Stripe test cards](https://docs.stripe.com/testing).
- The Stripe webhook secret comes from the local Stripe CLI forwarder, not the production dashboard.

### Environment variables (`.env`)

```env
# Core
SECRET_KEY=any-random-string-is-fine-for-dev
PRODUCTION=false

# England Athletics — PRODUCTION endpoint, production credentials
EA_STAGING=false
EA_CALL_KEY=<production EA call key>
EA_CALL_SECRET=<production EA call secret>
EA_CERT_PATH=data/<production-cert>.pfx
EA_CERT_PASSWORD=<production cert password>
# EA_TEST_MODE=   # leave unset — we want real EA data locally

# Stripe — TEST keys (no real money)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...   # from the Stripe CLI forwarder (see below)
```

### Setup steps

1. Copy `.env.example` to `.env` (done automatically by `just sync` on first run).
2. Fill in the production EA credentials and test Stripe keys.
3. Apply migrations:
   ```powershell
   uv run python scripts/_apply_migrations.py
   ```
4. Seed an admin user and test data:
   ```powershell
   just seed-user admin admin123 admin
   ```
5. Start the Stripe CLI webhook forwarder in a separate terminal:
   ```powershell
   stripe listen --forward-to localhost:8000/webhooks/stripe
   ```
   Copy the printed `whsec_…` value into `.env` as `STRIPE_WEBHOOK_SECRET`.
6. Start the dev server:
   ```powershell
   just serve
   ```

### Risks and mitigations

- **Real PII from EA** — athlete names/DOBs are real. Keep them in `data/` (gitignored). Do not log or share them outside development.
- **Production EA cert on laptop** — store it only in `data/`, never commit it. The `data/` directory is gitignored.
- **No real charges** — Stripe test mode ensures nothing is billed even when using production EA data.

---

## b) Testing (CI pipelines and local test runs)

**Goal:** Fast, deterministic, isolated tests with no dependency on external services.

### How it works

- **Unit tests** (`tests/unit/`): `TESTING=true` is set in `tests/unit/conftest.py` before the app imports. All tests use an in-memory DuckDB (`:memory:`). EA calls and Stripe calls are mocked with `unittest.mock.patch` or `pytest` monkeypatching — no network access.
- **UI / Playwright tests** (`tests/ui/`): A real server process is started against a temporary file-based database (`test_ui.duckdb`). The entry flow tests bypass the EA and Stripe APIs by directly inserting pre-paid batch records into the database (see `tests/ui/conftest.py`). `EA_TEST_MODE` is not needed here because the Playwright entry tests short-circuit before the EA call.
- **CI (GitHub Actions)**: The `unit-tests` job runs under the `testing` environment, which has the EA staging secrets and `EA_STAGING=true` set. Those secrets are only used by the live integration test in `tests/unit/test_entries_ea_api.py` (which requires a real cert file).

### Environment variables for local test runs

No `.env` file is needed for unit tests. Set these only if you want to run the live EA integration tests locally:

```env
# Only required for tests/unit/test_entries_ea_api.py live integration test
EA_STAGING=true
EA_CALL_KEY=<staging EA call key>
EA_CALL_SECRET=<staging EA call secret>
EA_CERT_PATH=data/<staging-cert>.pfx
EA_CERT_PASSWORD=<staging cert password>
```

For Playwright UI tests only:

```env
# No EA or Stripe variables needed — tests bypass those flows via DB seeding
SECRET_KEY=test-secret
PRODUCTION=false
```

### CI secrets (GitHub Actions — `testing` environment)

| Secret name | Value |
|---|---|
| `EA_CERT_PFX_BASE64` | Base64-encoded staging `.pfx` file |
| `EA_CERT_PASSWORD` | Stored in GitHub environment secret |
| `EA_CALL_KEY` | Stored in GitHub environment secret |
| `EA_CALL_SECRET` | Stored in GitHub environment secret |

These are loaded by the `unit-tests` job and written to `$GITHUB_ENV`. They point at the **staging** EA endpoint only (`EA_STAGING=true`). No production credentials are stored in CI.

### EA staging credentials

| Field | Value |
|---|---|
| Call key | Managed as a secret (do not commit) |
| Call secret | Managed as a secret (do not commit) |
| Certificate | Local file referenced by `EA_CERT_PATH` |
| Certificate password | Managed as a secret (do not commit) |
| Base URL | Set by `EA_STAGING=true` (staging endpoint) |

The staging cert is stored under `data/` as a `.pfx.txt` file (rename to `.pfx` before use). It contains no production data.

### Running tests locally

```powershell
# All unit tests (no network, no env vars needed)
just test-unit

# All UI / Playwright tests
just test-ui

# Everything
just test

# Run the live EA staging integration test (requires staging env vars above)
uv run pytest tests/unit/test_entries_ea_api.py -v
```

---

## c) Production

**Goal:** Real EA data, real Stripe payments, full security enforcement.

### How it works

- `PRODUCTION=true` enforces HTTPS-only cookies, HSTS headers, and requires `SECRET_KEY` to be set (app refuses to start without it).
- `EA_STAGING=false` points the app at the production EA endpoint.
- Stripe uses live keys; real cards are charged.
- The EA production certificate must be placed on the VPS and its path set in the systemd environment file.

### Environment variables (set in `/home/manager/website/.env` on the VPS)

```env
# Core
SECRET_KEY=<strong random hex — generate with: python3 -c "import secrets; print(secrets.token_hex(32))">
PRODUCTION=true

# England Athletics — PRODUCTION endpoint, production credentials
EA_STAGING=false
EA_CALL_KEY=<production EA call key>
EA_CALL_SECRET=<production EA call secret>
EA_CERT_PATH=/home/manager/website/data/<production-cert>.pfx
EA_CERT_PASSWORD=<production cert password>

# Stripe — LIVE keys
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...   # from Stripe Dashboard → Webhooks → your endpoint
```

### Setup steps

1. Transfer the production EA certificate securely to the VPS (use `scp` — never via git or email):
   ```powershell
   scp data/<production-cert>.pfx vps:/home/manager/website/data/
   ```
2. SSH to the VPS and create/edit the `.env` file:
   ```sh
   ssh vps
   nano /home/manager/website/.env
   ```
3. Restart the service:
   ```sh
   sudo systemctl restart oxcross
   ```
4. Verify it started cleanly (missing `SECRET_KEY` causes immediate exit):
   ```sh
   sudo systemctl status oxcross
   sudo journalctl -u oxcross -n 50
   ```

### Stripe webhook endpoint

Register the webhook endpoint in the [Stripe Dashboard](https://dashboard.stripe.com/webhooks):

- **URL:** `https://oxfordshirexcleague.uk/webhooks/stripe`
- **Events to listen for:** `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`

Copy the signing secret (`whsec_…`) into `.env` as `STRIPE_WEBHOOK_SECRET`.

### Security checklist before deploying entries to production

- [ ] `SECRET_KEY` is a strong random value (not the dev placeholder)
- [ ] `PRODUCTION=true`
- [ ] `EA_STAGING=false` and production EA credentials are set
- [ ] `STRIPE_SECRET_KEY` starts with `sk_live_` (not `sk_test_`)
- [ ] `STRIPE_WEBHOOK_SECRET` matches the Stripe Dashboard endpoint
- [ ] Production EA cert is not in git history
- [ ] `data/` directory permissions are restrictive (`chmod 700 data/`)
- [ ] Stripe webhook endpoint is registered and verified in the Dashboard

---

## Environment variable summary

| Variable | Local dev | Testing | Production |
|---|---|---|---|
| `SECRET_KEY` | Any string | Any string | Required: strong random |
| `PRODUCTION` | `false` | `false` | `true` |
| `DATABASE_URL` | unset (`data/app.duckdb`) | unset (`:memory:` / temp file) | unset (`data/app.duckdb`) |
| `EA_STAGING` | `false` | `true` | `false` |
| `EA_TEST_MODE` | unset | unset | unset |
| `EA_CALL_KEY` | Production key | Staging key (secret) | Production key |
| `EA_CALL_SECRET` | Production secret | Staging secret (secret) | Production secret |
| `EA_CERT_PATH` | Path to prod cert | Path to staging cert | Path to prod cert |
| `EA_CERT_PASSWORD` | Prod cert password | Staging cert password (secret) | Prod cert password |
| `STRIPE_SECRET_KEY` | `sk_test_…` | `sk_test_…` (mocked in unit tests) | `sk_live_…` |
| `STRIPE_PUBLISHABLE_KEY` | `pk_test_…` | `pk_test_…` | `pk_live_…` |
| `STRIPE_WEBHOOK_SECRET` | Stripe CLI `whsec_…` | mocked in unit tests | Dashboard `whsec_…` |
