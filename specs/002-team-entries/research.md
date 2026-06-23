# Research: Team Entries

**Date**: 2026-06-07 | **Plan**: [plan.md](plan.md)

All NEEDS CLARIFICATION items from the Technical Context are resolved below.

---

## 1. England Athletics TRAPI — "Get Athletes for Club" Endpoint

**Decision**: Use `GET race-provider/clubs/{clubId}/athletes` as the inferred endpoint URL (undocumented Method 5).

**Rationale**:
The API doc lists 5 methods. The four documented endpoints follow a consistent REST pattern:
- `race-provider/individuals` (search by name/DOB)
- `race-provider/individuals/{urn}/roles`
- `race-provider/clubs` (all clubs)
- (Method 5) "Returns all athletes within a given club" — logically: `race-provider/clubs/{clubId}/athletes`

All calls use the same three mandatory headers (`X-TRAPI-CALLKEY`, `X-TRAPI-CALLSECRET`, `X-TRAPI-CALLDATETIME`) plus a client certificate. League-level credentials are used for all calls on behalf of any club.

**Alternative considered**: `race-provider/clubs/{clubId}/individuals` — less likely given "athletes" is used in the API context. If Method 5 returns a 404, fall back to batch-searching athletes by URN from a local cache or prompt the manager to add athletes manually by EA URN.

**Implementation**:
```python
# entries.py
import httpx
from datetime import datetime, timezone

def _ea_headers(call_key: str, call_secret: str) -> dict[str, str]:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "X-TRAPI-CALLKEY": call_key,
        "X-TRAPI-CALLSECRET": call_secret,
        "X-TRAPI-CALLDATETIME": ts,
    }

def fetch_club_athletes(
    ea_club_id: str,
    call_key: str,
    call_secret: str,
    cert_path: str,
    cert_password: str,
    staging: bool = False,
) -> list[dict]:
    base = (
        "https://staging.myathletics.uk/TrinityAPIstaging/TrinityAPIService.svc/"
        if staging
        else "https://TrinityAPI.myathletics.uk/TrinityAPIService.svc/"
    )
    url = f"{base}race-provider/clubs/{ea_club_id}/athletes"
    headers = _ea_headers(call_key, call_secret)
    # httpx supports PKCS12 certs via (path, password) tuple
    with httpx.Client(cert=(cert_path, cert_password), http1=True) as client:
        resp = client.get(url, headers=headers, timeout=10.0)
        resp.raise_for_status()
    return resp.json().get("Athletes", [])
```

**Certificate handling**: The certificate path is configured via `EA_CERT_PATH` env var. The file must not be committed for production (use a secrets manager or VPS file path).

**Caching**: EA API responses are cached in the user session (FastAPI `Request.session`) for the duration of the request flow (athlete selection → preview → payment). No persistent caching — freshness on each new entry flow.

---

## 2. England Athletics Age Category Calculation

**Decision**: Age is calculated as of **31 August** of the season's starting year (standard UK athletics season reference date). OXL categories are: U9, U11, U13, U15, U17, U20, Senior, Veteran.

**Rationale**: UK Athletics (and EA) define competing age by age on 31 August. The OXL season runs Nov–Mar; the relevant reference date is the **31 August before the season starts** (i.e., for the 2025–2026 season, use 31 August 2025).

**Junior vs Adult split (for pricing)**:
- **Junior** (lower price): U9, U11, U13, U15, U17 (age < 17 on reference date)
- **Adult** (higher price): U20, Senior, Veteran (age ≥ 17 on reference date)

**OXL age category rules** (from race schedule in league manual):

| Age on 31 Aug (season start) | Category |
|------|----------|
| 7–8 | U9 |
| 9–10 | U11 |
| 11–12 | U13 |
| 13–14 | U15 |
| 15–16 | U17 |
| 17–19 | U20 |
| 20–34 | Senior |
| 35+ | Veteran |

**Implementation**:
```python
from datetime import date

def get_oxl_age_category(dob: date, reference_date: date) -> str:
    age = reference_date.year - dob.year - (
        (reference_date.month, reference_date.day) < (dob.month, dob.day)
    )
    if age <= 8:
        return "U9"
    elif age <= 10:
        return "U11"
    elif age <= 12:
        return "U13"
    elif age <= 14:
        return "U15"
    elif age <= 16:
        return "U17"
    elif age <= 19:
        return "U20"
    elif age <= 34:
        return "Senior"
    else:
        return "Veteran"

def is_junior(category: str) -> bool:
    return category in {"U9", "U11", "U13", "U15", "U17"}
```

**Reference date derivation**: Extract from `season_entry_config.reference_date` (set by admin when configuring entries for a season, defaulting to 31 Aug of the season's first year).

---

## 3. Stripe — Card + BACS Direct Debit Checkout

**Decision**: Use **Stripe Checkout Session** with `payment_method_types=['card', 'bacs_debit']`, GBP currency.

**Rationale**:
- Checkout Session handles both payment methods and mandate collection (for BACS) in a single hosted UI.
- BACS Direct Debit requires GBP and is asynchronous (T+3 to T+7 settlement). The batch enters `payment_initiated` state immediately and transitions to `paid` on `charge.succeeded` webhook.
- Card payment settles synchronously; `checkout.session.completed` is sufficient to mark as `paid`.

**Flow**:
```
Manager clicks Pay
  → POST /entries/{season_id}/batch/{batch_id}/checkout
    → create Stripe Checkout Session
    → redirect to session.url (Stripe-hosted page)
      → Card: stripe fires checkout.session.completed (payment_status = "paid")
      → BACS: stripe fires checkout.session.completed (payment_status = "unpaid")
                then later: charge.succeeded (settled)
  → Stripe redirects to success_url
    → mark batch as paid/payment_initiated, assign race numbers
    → show receipt page
```

**Webhook events handled**:
| Event | Action |
|---|---|
| `checkout.session.completed` + `payment_status = paid` | Mark batch `paid`, assign race numbers |
| `checkout.session.completed` + `payment_status = unpaid` | Mark batch `payment_initiated` (BACS mandate collected) |
| `charge.succeeded` | If batch is `payment_initiated`, mark `paid`, assign race numbers |
| `checkout.session.expired` | Mark batch `payment_failed` |

**Security**: Webhook endpoint at `POST /webhooks/stripe` verifies `Stripe-Signature` header using `stripe.Webhook.construct_event()`. This endpoint is exempt from CSRF (webhook secret is the authentication mechanism). Include `await request.body()` before any parsing (raw bytes required for signature verification).

**Implementation sketch**:
```python
# payments.py
import stripe, os

def create_checkout_session(
    batch_id: int,
    line_items: list[dict],
    success_url: str,
    cancel_url: str,
    customer_email: str,
) -> str:
    """Returns the Stripe Checkout Session URL."""
    session = stripe.checkout.Session.create(
        payment_method_types=["card", "bacs_debit"],
        line_items=line_items,
        mode="payment",
        currency="gbp",
        customer_email=customer_email,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"batch_id": str(batch_id)},
    )
    return session.url

def verify_webhook(payload: bytes, sig_header: str) -> stripe.Event:
    return stripe.Webhook.construct_event(
        payload, sig_header, os.environ["STRIPE_WEBHOOK_SECRET"]
    )
```

**Alternatives considered**:
- PaymentIntent directly: Requires manual mandate UI for BACS — more code, not PCI-compliant without Stripe Elements.
- Payment Link: Less control over metadata; cannot embed batch_id; not suited for programmatic use.

---

## 4. Pro-Rata Pricing via Fixed Lookup Table

**Decision**: Admins configure a price per `(season_id, fixtures_remaining)` pair. The system looks up the price when the manager creates a batch, snapshots it, and does not recalculate.

**Rationale**: Simple, auditable, and gives admins full control after each fixture. The `fixtures_remaining` count is computed at batch creation time by querying how many fixtures in the season have a date > today (or more precisely: have their entry deadline in the future).

**Example price table** (admin-configured):
| Fixtures remaining | Junior (£) | Adult (£) |
|---|---|---|
| 5 | 8.00 | 15.00 |
| 4 | 6.50 | 12.00 |
| 3 | 5.00 | 9.00 |
| 2 | 3.50 | 6.00 |
| 1 | 2.00 | 3.00 |

**Fixtures remaining** = count of fixtures in the season where `date > current date AND entry_deadline > current datetime`.

**Price snapshot**: When a batch is created, `fixtures_remaining` and per-athlete prices are stored on the batch and individual `athlete_entries` rows respectively. Admin price changes do not affect existing batches.

---

## 5. Entry Deadline Logic

**Decision**: The entry deadline per fixture is **midday (12:00) on the day of the fixture**. The system enforces this automatically.

**Implementation**:
```python
from datetime import datetime, time, timezone

def is_entry_open_for_fixture(fixture_date: date) -> bool:
    deadline = datetime.combine(fixture_date, time(12, 0), tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < deadline
```

A season accepts new entries if at least one fixture is still open. The `fixtures_remaining` count uses the same logic.

**Admin override**: Admin can manually close entries for the whole season by setting `season_entry_config.entries_open = false`.

---

## 6. PDF Generation — WeasyPrint

**Decision**: Use `weasyprint` to render a Jinja2 HTML template to PDF bytes.

**Rationale**: Best HTML→PDF library for Python. Integrates with the existing Jinja2 templating approach. Supports CSS for branding.

**Ubuntu VPS dependencies** (add to deployment notes):
```bash
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b
```

**Route**: `GET /entries/{season_id}/batch/{batch_id}/receipt.pdf` returns `Response(content=pdf_bytes, media_type="application/pdf")`.

**Shared template**: `templates/entries/receipt.html` is used for both the web view and the PDF — WeasyPrint renders it server-side. Absolute URLs are needed for images in PDF mode (logo loaded as base64 or absolute file path).

**Alternatives rejected**:
- `reportlab`: No HTML rendering; requires layout code — too much boilerplate.
- `fpdf2`: Limited CSS support; not suited for branded receipts.
- `xhtml2pdf`: Unmaintained.

---

## 7. DuckDB Sequence and Primary Key Pattern

**Decision**: Use `CREATE SEQUENCE IF NOT EXISTS <name>_id_seq START 1` + `INTEGER DEFAULT nextval('<name>_id_seq') PRIMARY KEY` (matches all existing migrations).

This is confirmed by reviewing migrations `0001` through `0012`. All new tables follow the same pattern.
