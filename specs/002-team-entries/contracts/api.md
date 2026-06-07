# API Contracts: Team Entries

**Date**: 2026-06-07 | **Plan**: [../plan.md](../plan.md)

All routes are server-rendered (HTML responses). HTMX partial responses are noted where applicable.
All state-changing endpoints require a valid session cookie and CSRF token (except the Stripe webhook).

---

## Authentication & Authorisation

| Route group | Required role | Notes |
|---|---|---|
| `/entries/*` | `club_manager` | Manager must have an active `club_managers` row |
| `/admin/entries/*` | `admin` | |
| `/webhooks/stripe` | None (Stripe signature) | CSRF exempt; raw body required |

---

## Manager Routes

### `GET /entries`

**Purpose**: Season selector for team managers.

**Auth**: `club_manager`

**Response**: HTML page — list of seasons that have `season_entry_config.entries_open = true`, ordered newest first. For each season: name, fixtures remaining, entry deadline for next fixture.

**Redirect**: If the manager has no active `club_managers` row, redirect to `/` with a flash error.

---

### `GET /entries/{season_id}`

**Purpose**: Season entries overview — all clubs' entered athletes (read-only), plus the manager's own add-more button.

**Auth**: `club_manager`

**Path params**: `season_id: int`

**Response**: HTML page with:
- Table of all entered athletes across all clubs (club, athlete name, age category, race number). Only `paid` and `payment_initiated` batches are shown.
- Manager's own club section with edit controls (only if entries are still open).
- "Add more athletes" button (only if `is_entry_open_for_season(season_id)`).

**Error cases**:
- `404` if `season_id` does not exist.
- `403` if the manager's club record is inactive.

---

### `GET /entries/{season_id}/add`

**Purpose**: Fetch club athletes from EA API and display selection form.

**Auth**: `club_manager`

**Path params**: `season_id: int`

**Response**: HTML form with:
- Table of EA-returned athletes for the manager's club.
- Each row: checkbox, athlete name, age category (computed from DOB + season reference date), registration status.
- Already-entered athletes (any paid/initiated batch this season) are shown as disabled/greyed out with "Already entered" label.
- Unregistered athletes shown as disabled with "Not EA registered" label.
- Price table snippet showing current pro-rata prices (junior/adult).
- Entry deadline warning if < 48h to next fixture deadline.

**EA API call**: `GET race-provider/clubs/{ea_club_id}/athletes` using league credential + mTLS cert. Result cached in request session.

**Error cases**:
- `503` (with user-friendly message) if EA API is unreachable.
- `403` if entries are closed for this season.

---

### `POST /entries/{season_id}/batch`

**Purpose**: Create a pending entry batch for the selected athletes.

**Auth**: `club_manager`

**Path params**: `season_id: int`

**Form body**:
| Field | Type | Notes |
|---|---|---|
| `csrf_token` | `str` | Validated by `_validate_csrf()` |
| `ea_urns` | `list[int]` | Selected athlete EA URNs (≥ 1) |

**Processing**:
1. Validate CSRF.
2. Re-fetch athlete data from EA (or session cache) to prevent tampered submissions.
3. Verify each URN is registered (EA status = Registered) and not already entered this season.
4. Compute `fixtures_remaining` (fixtures with deadline > now).
5. Look up price tier for `(season_id, fixtures_remaining)`.
6. Compute `ea_age_category` and `is_junior` for each athlete.
7. Compute per-athlete `amount_pence` and `total_pence`.
8. Insert `entry_batches` row (status = `pending_payment`).
9. Insert `athlete_entries` rows.
10. Redirect to `GET /entries/{season_id}/batch/{batch_id}/preview`.

**Error cases**:
- `400` if no URNs selected.
- `400` if any URN is already entered this season (re-validates server-side).
- `400` if no price tier found for current fixtures_remaining.
- `403` if entries are closed.

---

### `GET /entries/{season_id}/batch/{batch_id}/preview`

**Purpose**: Show the batch preview with cost breakdown before payment.

**Auth**: `club_manager` (must own the batch)

**Response**: HTML page with:
- Table: athlete name, age category, price per athlete.
- Total amount.
- "Proceed to Payment" button (POST to `/entries/{season_id}/batch/{batch_id}/checkout`).
- "Cancel" link (batch left in `pending_payment`; can retry later).

**Error cases**:
- `403` if batch belongs to a different club.
- `404` if batch not found.
- `400` if batch is already `paid`.

---

### `POST /entries/{season_id}/batch/{batch_id}/checkout`

**Purpose**: Create a Stripe Checkout Session and redirect the manager to Stripe's hosted page.

**Auth**: `club_manager` (must own the batch)

**Form body**:
| Field | Type |
|---|---|
| `csrf_token` | `str` |

**Processing**:
1. Validate CSRF.
2. Load batch (must be `pending_payment` or `payment_failed`).
3. Build Stripe line items (one item per `is_junior` group — "Junior entry × N" and "Adult entry × M").
4. Call `stripe.checkout.Session.create(payment_method_types=['card', 'bacs_debit'], currency='gbp', ...)`.
5. Store `stripe_checkout_session_id` on batch.
6. Redirect (`302`) to `session.url`.

**Error cases**:
- `400` if batch is already `paid`.
- `500` (user-friendly error page) if Stripe API call fails.

---

### `GET /entries/{season_id}/batch/{batch_id}/success`

**Purpose**: Post-Stripe-redirect landing page. Confirms payment status and links to receipt.

**Auth**: `club_manager` (must own the batch)

**Query params**: `session_id` (Stripe passes this automatically)

**Response**: HTML page with status message:
- If batch is `paid`: "Payment confirmed — download your receipt below."
- If batch is `payment_initiated`: "BACS Direct Debit mandate set up — payment will be collected in 3–5 business days."
- If batch is `pending_payment` (webhook not yet received): show a loading indicator with a note to refresh.

---

### `GET /entries/{season_id}/batch/{batch_id}/receipt`

**Purpose**: Web receipt page.

**Auth**: `club_manager` (must own the batch)

**Response**: HTML page — OXL logo, season, club, manager name, date, payment method, athlete list (name, age category, race number, price), total.

**Error cases**: `404` if batch is not `paid` or `payment_initiated`.

---

### `GET /entries/{season_id}/batch/{batch_id}/receipt.pdf`

**Purpose**: PDF download of receipt.

**Auth**: `club_manager` (must own the batch)

**Response**: `application/pdf` — generated by WeasyPrint from `templates/entries/receipt.html`.

**Error cases**: `404` if batch is not `paid` or `payment_initiated`.

---

## Stripe Webhook

### `POST /webhooks/stripe`

**Purpose**: Receive Stripe event notifications and update batch status.

**Auth**: None — verified via `Stripe-Signature` header using `stripe.Webhook.construct_event()`.

**⚠️ CSRF exempt** — must be excluded from CSRF middleware.

**Events handled**:

| Event type | Condition | Action |
|---|---|---|
| `checkout.session.completed` | `payment_status = 'paid'` | Batch → `paid`; assign race numbers; set `paid_at` |
| `checkout.session.completed` | `payment_status = 'unpaid'` | Batch → `payment_initiated`; store payment method |
| `charge.succeeded` | Batch in `payment_initiated` | Batch → `paid`; assign race numbers; set `paid_at` |
| `checkout.session.expired` | Any | Batch → `payment_failed` |

**Response**: `200 OK` with `{"received": true}` on success. Must return `200` even for ignored events.

**Race number assignment**:
```sql
-- Assign next available race number in the season
SELECT COALESCE(MAX(race_number), 0) + 1
FROM athlete_entries
WHERE season_id = ?;
-- Then increment for each athlete in the batch
```

---

## Admin Routes

### `GET /admin/entries`

**Purpose**: Full entries overview — all clubs, all seasons, all payment statuses.

**Auth**: `admin`

**Query params**: `season_id: int (optional)`, `club_id: int (optional)`, `status: str (optional)`

**Response**: HTML table with: season, club, manager, batch count, athletes entered, total paid (pence), outstanding (payment_initiated count). Filterable via HTMX.

---

### `GET /admin/entries/{season_id}`

**Purpose**: Per-season drill-down.

**Auth**: `admin`

**Response**: HTML page with per-club breakdown: club name, athletes entered, total paid, batch details (date, payment method, status). Links to individual batch detail.

---

### `GET /admin/entries/{season_id}/pricing`

**Purpose**: View and edit the price tier lookup table for a season.

**Auth**: `admin`

**Response**: HTML form — table with one row per `fixtures_remaining` value (1 to `total_fixtures`). Each row: fixtures remaining, junior price (£), adult price (£), last updated. Inline edit via HTMX POST.

---

### `POST /admin/entries/{season_id}/pricing`

**Purpose**: Create or update a single price tier.

**Auth**: `admin`

**Form body**:
| Field | Type | Notes |
|---|---|---|
| `csrf_token` | `str` | |
| `fixtures_remaining` | `int` | 1–5 |
| `junior_pence` | `int` | ≥ 0 |
| `adult_pence` | `int` | ≥ 0 |

**Processing**: UPSERT into `entry_price_tiers`; update `updated_at`.

**Response**: HTMX partial — updated table row.

---

### `POST /admin/entries/{season_id}/config`

**Purpose**: Open or close entries for a season; set EA reference date.

**Auth**: `admin`

**Form body**:
| Field | Type |
|---|---|
| `csrf_token` | `str` |
| `entries_open` | `bool` |
| `ea_reference_date` | `date` |
| `total_fixtures` | `int` |

**Processing**: UPSERT into `season_entry_config`.

**Response**: Redirect to `/admin/entries/{season_id}`.

---

## Admin Club Routes

### `GET /admin/clubs`

**Purpose**: List all clubs.

**Auth**: `admin`

**Response**: HTML page — table of all clubs (name, OXL code, EA club ID, active status); "Add Club" inline form at the top.

---

### `POST /admin/clubs`

**Purpose**: Create a new club.

**Auth**: `admin`

**Form body**:
| Field | Type | Notes |
|---|---|---|
| `csrf_token` | `str` | |
| `name` | `str` | Non-empty |
| `oxl_code` | `str` | Non-empty; must be unique |
| `ea_club_id` | `str` | Digits only |
| `is_active` | `bool` | Default true |

**Processing**: Validate CSRF; validate `oxl_code` uniqueness and `ea_club_id` matches `\d+`; INSERT into `clubs`.

**Response**: Redirect to `GET /admin/clubs`. `400` with error message if validation fails.

---

### `GET /admin/clubs/{club_id}/edit`

**Purpose**: Edit form for an existing club.

**Auth**: `admin`

**Response**: HTML form pre-populated with club fields.

---

### `POST /admin/clubs/{club_id}`

**Purpose**: Update an existing club.

**Auth**: `admin`

**Form body**: Same as `POST /admin/clubs`.

**Processing**: Validate CSRF; if setting `is_active = false`, check for any `entry_batches` with `status IN ('pending_payment', 'payment_initiated', 'paid')` for this club — if found, return `409` with message "Club has active entry batches and cannot be deactivated." Otherwise UPDATE `clubs`.

**Response**: Redirect to `GET /admin/clubs`.

---

## Admin Club Manager Routes

### `GET /admin/club-managers`

**Purpose**: List all club manager accounts.

**Auth**: `admin`

**Response**: HTML page — table of managers (username, email, club name, is_active); "Add Manager" form section.

---

### `POST /admin/club-managers`

**Purpose**: Create a new club manager user and link to a club.

**Auth**: `admin`

**Form body**:
| Field | Type | Notes |
|---|---|---|
| `csrf_token` | `str` | |
| `username` | `str` | Non-empty; must be unique in `users` |
| `email` | `str` | Valid email |
| `password` | `str` | Min 8 chars; hashed with bcrypt before storage |
| `club_id` | `int` | Must reference an active club |

**Processing**: Validate CSRF; validate username uniqueness and club is active; INSERT into `users` with `role='club_manager'` and bcrypt-hashed password; INSERT into `club_managers` linking `user_id` to `club_id`.

**Response**: Redirect to `GET /admin/club-managers`. `400` on validation failure.

---

### `POST /admin/club-managers/{manager_id}/toggle`

**Purpose**: Toggle `is_active` on a `club_managers` row (activate or deactivate a manager without deleting).

**Auth**: `admin`

**Form body**:
| Field | Type |
|---|---|
| `csrf_token` | `str` |

**Processing**: Validate CSRF; flip `is_active` on the `club_managers` row (does not affect the `users` row — manager can still log in but entry routes return 403).

**Response**: HTMX partial — updated table row showing new active status.
