---

description: "Task list for Team Entries feature implementation"
---

# Tasks: Team Entries

**Input**: Design documents from `specs/002-team-entries/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/api.md ✅, quickstart.md ✅

**Organization**: Tasks grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US7)
- Exact file paths in every description

---

## Phase 1: Setup

**Purpose**: Install new dependencies and register environment configuration.

- [X] T001 Add `stripe`, `weasyprint`, `httpx` to project deps via `uv add stripe weasyprint httpx`
- [X] T002 [P] Add `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `EA_CALL_KEY`, `EA_CALL_SECRET`, `EA_CERT_PATH`, `EA_CERT_PASSWORD`, `EA_STAGING` to `.env.example` with placeholder values
- [X] T003 [P] Add `.env` to `.gitignore` if not already present; confirm EA certificate files under `data/` are also gitignored

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database schema, identity extensions, and new modules that all user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Write migration `migrations/0013_create_clubs.sql` — `clubs` table with `club_id_seq`, fields: `id`, `name`, `oxl_code`, `ea_club_id`, `is_active`, `created_at` (see data-model.md)
- [X] T005 [P] Write migration `migrations/0014_create_club_managers.sql` — `club_managers` table with `club_manager_id_seq`, fields: `id`, `user_id` (UNIQUE FK→users), `club_id` (FK→clubs), `is_active`, `created_at`
- [X] T006 [P] Write migration `migrations/0015_create_season_entry_config.sql` — `season_entry_config` table (PK=`season_id`), fields: `entries_open`, `ea_reference_date`, `total_fixtures`, `created_at`
- [X] T007 [P] Write migration `migrations/0016_create_entry_price_tiers.sql` — `entry_price_tiers` table with `entry_price_tier_id_seq`, fields: `id`, `season_id`, `fixtures_remaining` (CHECK ≥1), `junior_pence`, `adult_pence`, `updated_at`; UNIQUE `(season_id, fixtures_remaining)`
- [X] T008 [P] Write migration `migrations/0017_create_entry_batches.sql` — `entry_batches` table with `entry_batch_id_seq`; all fields from data-model.md including `status`, `fixtures_remaining_at_entry`, `total_pence`, stripe fields, `paid_at`; indexes on `(season_id, club_id)` and `stripe_checkout_session_id`
- [X] T009 [P] Write migration `migrations/0018_create_athlete_entries.sql` — `athlete_entries` table with `athlete_entry_id_seq`; all fields from data-model.md; UNIQUE `(season_id, club_id, ea_urn)` (same athlete may be entered by different clubs); indexes on `batch_id` and `(season_id, club_id)`
- [X] T010 Apply all 6 migrations locally and confirm schema with `uv run python scripts/_apply_migrations.py`
- [X] T011 Add Pydantic models to `src/website/models.py`: `Club`, `PriceTier`, `AthleteEntryRow`, `EntryBatch` — exact fields from data-model.md
- [X] T012 [P] Create `src/website/entries.py` — stub module with: `_ea_headers()`, `fetch_club_athletes()`, `get_oxl_age_category()`, `is_junior()`, `compute_fixtures_remaining()`, `is_entry_open_for_fixture()` (see research.md for implementations)
- [X] T013 [P] Create `src/website/payments.py` — stub module with: `create_checkout_session()`, `verify_webhook()` (see research.md for Stripe patterns)
- [X] T014 [P] Create `src/website/receipts.py` — stub module with: `generate_pdf_receipt(batch_id, db) -> bytes` using WeasyPrint
- [X] T015 Add DB repository helpers to `src/website/repository.py`: `get_club_for_manager(user_id, db)`, `get_season_entry_config(season_id, db)`, `get_price_tier(season_id, fixtures_remaining, db)`, `get_entered_ea_urns(season_id, db)`, `create_entry_batch(...)`, `create_athlete_entries(...)`, `get_entry_batch(batch_id, db)`, `update_batch_status(...)`, `assign_race_numbers(batch_id, db)`
- [X] T016 Add `club_manager` role handling to `src/website/identity.py`: `require_club_manager(request, db)` dependency that resolves the current user's active `club_managers` row; raises `403` if not found or `is_active=False`
- [X] T017 Register the Stripe webhook route `POST /webhooks/stripe` in `src/website/main.py` with CSRF exemption (raw body endpoint); stub handler that verifies Stripe signature using `verify_webhook()` from `payments.py`

**Checkpoint**: All migrations applied, all stubs importable, `get_club_for_manager` returns correct data.

---

## Phase 2b: Admin Bootstrap — Clubs & Manager Accounts (Priority: P1)

**Purpose**: Admin must be able to create club records (with EA club IDs) and club manager accounts before any entry flow can be tested end-to-end. These are blocking for Phase 3 onwards.

**Independent Test**: Create a club via admin form; create a manager linked to it; log in as that manager; confirm `/entries` is accessible and the club's EA club ID is correct.

- [X] T063 [US8] Implement `GET /admin/clubs` (list) and `POST /admin/clubs` (create) routes in `src/website/main.py`: validate CSRF; validate `oxl_code` is unique and `ea_club_id` matches `\d+`; INSERT into `clubs`; redirect to list on success; render `templates/admin/clubs/list.html`
- [X] T064 [P] [US8] Create `templates/admin/clubs/list.html`: table of clubs (name, OXL code, EA club ID, active status, edit link); "Add Club" inline form at top (name, OXL code, EA club ID fields); CSRF hidden input
- [X] T065 [US8] Implement `GET /admin/clubs/{club_id}/edit` and `POST /admin/clubs/{club_id}` routes: load club; validate CSRF on POST; if deactivating, check for active `entry_batches` and return 409 if found; otherwise UPDATE `clubs`; redirect to list
- [X] T066 [US9] Implement `GET /admin/club-managers` (list) and `POST /admin/club-managers` (create) routes in `src/website/main.py`: on POST, validate CSRF + username uniqueness + club is active; INSERT into `users` with `role='club_manager'` and bcrypt-hashed password; INSERT into `club_managers`; render `templates/admin/club-managers/list.html`
- [X] T067 [P] [US9] Create `templates/admin/club-managers/list.html`: table of managers (username, email, club name, is_active, toggle button); "Add Manager" inline form (username, email, password, club dropdown); CSRF hidden input
- [X] T068 [US9] Implement `POST /admin/club-managers/{manager_id}/toggle` route: validate CSRF; flip `is_active` on `club_managers` row; return HTMX partial of updated row
- [X] T069 Register all clubs and club-manager routes in `src/website/main.py` with `require_admin` dependency; create `templates/admin/clubs/` and `templates/admin/club-managers/` directories

**Checkpoint**: Admin can create clubs with correct EA club IDs and create manager accounts linked to those clubs. Manager can log in and reach `/entries`.

---

## Phase 3: User Story 6 — Admin Price Management (Priority: P1) 🎯 MVP first

**Goal**: Admin can configure price tiers for a season before entries open. This must be done before managers can pay, so it is implemented first.

**Independent Test**: Create a season, POST price tiers via admin form, GET the pricing page and assert rows match input; change a tier, verify update.

- [X] T018 [US6] Implement `GET /admin/entries/{season_id}/pricing` route in `src/website/main.py`: query `entry_price_tiers` for season, render `templates/admin/entries/pricing.html`
- [X] T019 [P] [US6] Create `templates/admin/entries/pricing.html`: table with one row per fixtures-remaining, inline edit form (junior £, adult £), HTMX `hx-post` on each row, CSRF token hidden input
- [X] T020 [US6] Implement `POST /admin/entries/{season_id}/pricing` route: validate CSRF, validate `fixtures_remaining` (1–`total_fixtures`), `junior_pence ≥ 0`, `adult_pence ≥ 0`; UPSERT into `entry_price_tiers` (set `updated_at = now()`); return HTMX partial of updated row
- [X] T021 [US6] Implement `POST /admin/entries/{season_id}/config` route: validate CSRF, UPSERT `season_entry_config` (`entries_open`, `ea_reference_date`, `total_fixtures`); redirect to `/admin/entries/{season_id}`
- [X] T022 [P] [US6] Create `templates/admin/entries/season_detail.html`: per-season view with: entry config panel (open/close toggle, reference date form), price tiers table, placeholder for entries list
- [X] T023 [US6] Implement `GET /admin/entries` route: query `entry_batches` joined to `clubs`, `seasons`, `users`; support optional `season_id`, `club_id`, `status` query params; render `templates/admin/entries/overview.html`
- [X] T024 [P] [US6] Create `templates/admin/entries/overview.html`: filterable table (season, club, manager, athletes entered, total paid, payment_initiated count); HTMX filter controls
- [X] T025 [US6] Register all admin entries routes in `src/website/main.py` with `require_admin` dependency

**Checkpoint**: Admin can open a season for entries, set price tiers, and view the (empty) overview.

---

## Phase 4: User Story 1 — Team Manager Selects Athletes (Priority: P1)

**Goal**: Manager logs in, selects a season, fetches EA athletes, sees eligibility, and builds a pending batch.

**Independent Test**: Mock EA API returning 5 athletes (3 registered, 1 unregistered, 1 already entered); assert only 3 selectable; POST batch with 2 valid URNs; assert `entry_batches` row exists in `pending_payment` status with correct `total_pence`.

- [X] T026 [US1] Implement `fetch_club_athletes()` in `src/website/entries.py`: `httpx.Client` with `http1=True`, mTLS cert loaded from `EA_CERT_PATH`/`EA_CERT_PASSWORD` env vars, headers from `_ea_headers()`, URL from staging/live toggle (`EA_STAGING` env var); return `list[dict]` of athlete objects
- [X] T027 [US1] Implement `compute_fixtures_remaining(season_id, db) -> int` in `src/website/entries.py`: count fixtures where `date > today AND combine(date, time(12,0), utc) > now()`
- [X] T028 [US1] Implement `GET /entries` route in `src/website/main.py`: require `club_manager`; query seasons with `season_entry_config.entries_open = true`; render `templates/entries/season_select.html`
- [X] T029 [P] [US1] Create `templates/entries/season_select.html`: list of open seasons with name, fixtures remaining count, next fixture date and deadline; link to `/entries/{season_id}/add`
- [X] T030 [US1] Implement `GET /entries/{season_id}/add` route: require `club_manager`; check `entries_open` + `compute_fixtures_remaining > 0`; call `fetch_club_athletes()` with club's `ea_club_id`; compute `ea_age_category` + `is_junior` for each athlete using `get_oxl_age_category()`; load `get_entered_ea_urns(season_id)`; render `templates/entries/athlete_select.html`
- [X] T031 [P] [US1] Create `templates/entries/athlete_select.html`: table with checkbox per athlete (disabled if unregistered or already entered), name, age category, registration status badge, price preview (junior/adult for current fixtures_remaining); submit button; CSRF hidden input; deadline warning banner
- [X] T032 [US1] Implement `POST /entries/{season_id}/batch` route: validate CSRF; re-fetch EA athletes (re-validates server-side — no client trust); validate each submitted URN is registered + not already entered; look up price tier; compute age categories + `amount_pence` per athlete; insert `entry_batches` + `athlete_entries` rows; redirect to `GET /entries/{season_id}/batch/{batch_id}/preview`
- [X] T033 [US1] Add `503` error handler for EA API failures in `src/website/entries.py`: catch `httpx.RequestError`; raise `HTTPException(503)` with user-friendly message "The England Athletics system is temporarily unavailable. Please try again shortly."

**Checkpoint**: Manager can browse seasons, see EA athletes, and create a `pending_payment` batch in the DB.

---

## Phase 5: User Story 2 — Preview and Pay (Priority: P1)

**Goal**: Manager sees cost breakdown and pays via Stripe Checkout (card or BACS).

**Independent Test**: Given a `pending_payment` batch, GET preview and assert all athletes shown with correct prices; POST checkout creates a Stripe session (mocked); simulate `checkout.session.completed` webhook (card) and assert batch transitions to `paid` with race numbers assigned.

- [X] T034 [US2] Implement `GET /entries/{season_id}/batch/{batch_id}/preview` route: require `club_manager`; assert batch belongs to manager's club; load `athlete_entries` for batch; render `templates/entries/batch_preview.html`
- [X] T035 [P] [US2] Create `templates/entries/batch_preview.html`: table (athlete name, age category, price); totals (junior subtotal, adult subtotal, grand total in £); "Proceed to Payment" button; "Save for later" link; CSRF hidden input
- [X] T036 [US2] Implement `create_checkout_session()` fully in `src/website/payments.py`: build Stripe line items grouped by junior/adult (e.g. "Junior entry × 3 — Oxford City AC" at unit price); call `stripe.checkout.Session.create()` with `payment_method_types=['card', 'bacs_debit']`, `currency='gbp'`, `metadata={'batch_id': str(batch_id)}`; return session URL
- [X] T037 [US2] Implement `POST /entries/{season_id}/batch/{batch_id}/checkout` route: validate CSRF; assert batch is `pending_payment` or `payment_failed`; call `create_checkout_session()`; store `stripe_checkout_session_id` on batch; redirect `302` to Stripe session URL
- [X] T038 [US2] Implement `POST /webhooks/stripe` handler fully in `src/website/main.py`: call `verify_webhook()`; dispatch on event type; `checkout.session.completed` (payment_status=paid) → call `update_batch_status(paid)` + `assign_race_numbers()`; `checkout.session.completed` (payment_status=unpaid) → `update_batch_status(payment_initiated)`, store `stripe_payment_method='bacs_debit'`; `charge.succeeded` → if batch is `payment_initiated`, `update_batch_status(paid)` + `assign_race_numbers()`; `checkout.session.expired` → `update_batch_status(payment_failed)`; return `{"received": true}`
- [X] T039 [US2] Implement `assign_race_numbers(batch_id, db)` in `src/website/repository.py`: `SELECT COALESCE(MAX(race_number), 0) + 1 FROM athlete_entries WHERE season_id = ?`; assign incrementally to each athlete in the batch ordered by `id`
- [X] T040 [US2] Implement `GET /entries/{season_id}/batch/{batch_id}/success` route: load batch status; render `templates/entries/batch_success.html` with appropriate message (paid / payment_initiated / pending)
- [X] T041 [P] [US2] Create `templates/entries/batch_success.html`: status-specific message panel; link to receipt (if paid/initiated); BACS note about T+3–7 days settlement

**Checkpoint**: Manager can complete card payment end-to-end; batch transitions to `paid`; race numbers assigned.

---

## Phase 6: User Story 3 — Receipt (PDF and Web) (Priority: P1)

**Goal**: Manager sees a web receipt and can download a branded PDF.

**Independent Test**: Given a `paid` batch, GET the receipt page and assert all fields present (logo, season, club, manager, payment method, athlete table with race numbers, total); GET receipt.pdf and assert response is `application/pdf` with non-zero content.

- [X] T042 [US3] Create `templates/entries/receipt.html`: OXL logo (absolute path for WeasyPrint compatibility), season name, club name, manager name, date, payment method, athletes table (name, age category, race number, price), total; print-friendly CSS block
- [X] T043 [US3] Implement `generate_pdf_receipt(batch_id, db) -> bytes` fully in `src/website/receipts.py`: query batch + athlete entries + club + manager; render `receipt.html` via Jinja2; pass to `weasyprint.HTML(string=html).write_pdf()`; return bytes
- [X] T044 [US3] Implement `GET /entries/{season_id}/batch/{batch_id}/receipt` route: require `club_manager` owning the batch; assert batch is `paid` or `payment_initiated`; render `templates/entries/receipt.html` as HTML response
- [X] T045 [US3] Implement `GET /entries/{season_id}/batch/{batch_id}/receipt.pdf` route: same auth + status check; call `generate_pdf_receipt()`; return `Response(content=bytes, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename=receipt-{batch_id}.pdf'})`

**Checkpoint**: Web receipt renders correctly; PDF downloads and contains all required fields.

---

## Phase 7: User Story 4 — Season Entries Overview (Priority: P2)

**Goal**: Any logged-in manager can view a read-only list of all entered athletes for a season across all clubs.

**Independent Test**: Insert paid batches for two clubs; assert both clubs' athletes appear in the overview for any authenticated manager; assert no edit/delete controls are shown for the other club.

- [X] T046 [US4] Implement `GET /entries/{season_id}` route: require `club_manager`; query `athlete_entries` joined to `clubs` for all `paid`/`payment_initiated` batches in the season; group by club; render `templates/entries/season_overview.html`
- [X] T047 [P] [US4] Create `templates/entries/season_overview.html`: per-club sections with athlete table (name, age category, race number); own club section has "Add more athletes" button if entries still open; other clubs are read-only; empty-state message if no entries yet

**Checkpoint**: Manager can see all clubs' entered athletes; own club has add button; others are read-only.

---

## Phase 8: User Story 5 — Multiple Submissions (Priority: P2)

**Goal**: Manager can add more athletes mid-season as a new batch (incremental payment).

**Independent Test**: Create first batch (paid, 5 fixtures remaining); advance mock date so 1 fixture has passed; create second batch; assert price reflects `fixtures_remaining=4`; assert athletes from first batch are excluded from selection.

- [X] T048 [US5] Update `GET /entries/{season_id}` to show "Add more athletes" button for manager's own club when `compute_fixtures_remaining > 0` (button links to `/entries/{season_id}/add`) — no new route needed; logic already handles multiple batches
- [X] T049 [US5] Update `get_entered_ea_urns` to `get_entered_ea_urns(season_id, club_id, db)` in `src/website/repository.py`: queries `athlete_entries` for that club across ALL batches (any status: `paid`, `payment_initiated`, `pending_payment`) to prevent the same club entering the same athlete twice — the same athlete entered by a different club is not excluded
- [X] T050 [US5] Add unit test `tests/unit/test_entries.py::test_second_batch_excludes_already_entered_athletes` — mock two batches, assert URNs from first batch not selectable in second

**Checkpoint**: Manager can submit a second batch; already-entered athletes excluded; new batch priced at current fixtures_remaining.

---

## Phase 9: User Story 7 — Admin Entries Overview (Priority: P2)

**Goal**: Admin sees all entries across clubs, seasons, and payment statuses with drill-down.

**Independent Test**: Insert batches for 3 clubs across 2 seasons; GET `/admin/entries` and assert all 3 clubs appear; filter by `season_id` and assert only that season's clubs appear; GET drill-down and assert per-club totals correct.

- [X] T051 [US7] Extend `GET /admin/entries/{season_id}` (already scaffolded in T022) to include per-club entry counts, total amount paid, count of `payment_initiated` batches; render full data in `templates/admin/entries/season_detail.html`
- [X] T052 [US7] Add HTMX filter to `templates/admin/entries/overview.html`: season dropdown + club dropdown + status filter; `hx-get` to `/admin/entries` with updated params; partial HTML response for table body

**Checkpoint**: Admin can filter by season/club/status and see per-club drill-down with correct totals.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Security hardening, GDPR, WCAG, error handling, and dev tooling.

- [X] T053 Update `templates/privacy.html` data inventory: add EA athlete data (ea_urn, athlete_name, date_of_birth, ea_age_category) with purpose (EA license validation + league entry), retention (season + 1 year), basis (contract/legitimate interest)
- [X] T054 [P] Add `STRIPE_PUBLISHABLE_KEY` to Jinja2 global context in `src/website/main.py` (via `app.state` or template context injection) so templates can embed it for future Stripe.js use without hardcoding
- [X] T055 [P] Write unit tests `tests/unit/test_entries.py`: `test_get_oxl_age_category` (boundary ages for each category), `test_is_junior`, `test_is_entry_open_for_fixture` (before/after 12:00 midday), `test_compute_fixtures_remaining_counts_only_future` — all with in-memory DuckDB `:memory:`
- [X] T056 [P] Write unit tests `tests/unit/test_payments.py`: `test_verify_webhook_valid_signature`, `test_verify_webhook_invalid_signature_raises`, `test_batch_status_transitions` (state machine for all 4 webhook events) — Stripe calls mocked with `unittest.mock.patch`
- [X] T057 [P] Write unit tests `tests/unit/test_receipts.py`: `test_generate_pdf_receipt_returns_bytes`, `test_receipt_html_contains_required_fields` — WeasyPrint mocked to avoid system dep in CI
- [X] T058 [P] Accessibility pass on all new templates: verify all `<input>` elements have `<label>` or `aria-label`; status badges use `role="status"`; table headers use `<th scope="col">`; keyboard navigation reachable (Tab order); run `axe` check in Playwright on entry + receipt pages
- [X] T059 [P] Run `bandit -r src/ -ll` and resolve any new findings introduced by `entries.py`, `payments.py`, `receipts.py`; add `# nosec` with comment only where finding is a confirmed false positive
- [X] T060 Write dev seed script `scripts/seed_entries_dev.py`: create test season + 5 fixtures + `season_entry_config` + price tiers + admin user + Oxford City AC club + club_manager user (as per quickstart.md)
- [X] T061 [P] Add WeasyPrint system dependency note to `docs/setup.md`: `sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b` required on Ubuntu VPS
- [X] T062 Write Playwright UI test `tests/ui/test_entries.spec.ts`: full happy-path card payment journey (login as manager → select season → select athletes → preview → mock Stripe redirect → receipt page → download PDF); assert receipt PDF response header and page content

---

## Dependency Graph

```
Phase 1 (Setup)
  └─→ Phase 2 (Foundational: migrations T004–T009, models T011, modules T012–T014, repo T015, identity T016, webhook stub T017)
        └─→ Phase 2b (Admin Bootstrap: clubs T063–T065, club-managers T066–T069)
              ├─→ Phase 3 (US6: Admin pricing — needed before managers can pay) [T018–T025]
              ├─→ Phase 4 (US1: Athlete selection) [T026–T033]
              │     └─→ Phase 5 (US2: Preview + Pay) [T034–T041]
              │           └─→ Phase 6 (US3: Receipt) [T042–T045]
              │                 └─→ Phase 7 (US4: Season overview) [T046–T047]
              │                       └─→ Phase 8 (US5: Multiple submissions) [T048–T050]
              └─→ Phase 9 (US7: Admin overview — extends Phase 3 scaffold) [T051–T052]

Phase 10 (Polish) — runs after all user stories; T055–T057 can be written any time
```

## Parallel Execution Examples

**Within Phase 2** (run T004–T009 simultaneously — all different SQL files):
```
T004 0013_create_clubs.sql
T005 0014_create_club_managers.sql   ← parallel
T006 0015_create_season_entry_config.sql  ← parallel
T007 0016_create_entry_price_tiers.sql    ← parallel
T008 0017_create_entry_batches.sql        ← parallel
T009 0018_create_athlete_entries.sql      ← parallel
```

**Within Phase 4** (after T026, T027 done):
```
T028 GET /entries route
T029 season_select.html           ← parallel
T030 GET /entries/{id}/add
T031 athlete_select.html          ← parallel with T030
```

**Phase 10** — all T055, T056, T057, T058, T059, T061 fully parallel.

## Implementation Strategy

**MVP scope (deliver value quickly)**:
1. Phase 1 + Phase 2 — foundation
2. Phase 3 (US6) — admin prices configured
3. Phase 4 (US1) — managers can select athletes
4. Phase 5 (US2) — card payment only (BACS tested separately)
5. Phase 6 (US3) — receipt page + PDF

**Phase 7–9** extend the MVP after it is confirmed working end-to-end.

**Phase 10** runs concurrently with later phases.

---

## Summary

| Phase | User Story | Tasks | Parallel? |
|---|---|---|---|
| 1 — Setup | — | T001–T003 | T002, T003 ✓ |
| 2 — Foundation | — | T004–T017 | T004–T009 ✓; T011–T014 ✓; T016 ✓ |
| 2b — Admin Bootstrap | US8 (P1), US9 (P1) | T063–T069 | T064, T067 ✓ |
| 3 — Admin Pricing | US6 (P1) | T018–T025 | T019, T022, T024 ✓ |
| 4 — Athlete Selection | US1 (P1) | T026–T033 | T029, T031, T033 ✓ |
| 5 — Preview + Pay | US2 (P1) | T034–T041 | T035, T036, T041 ✓ |
| 6 — Receipt | US3 (P1) | T042–T045 | — |
| 7 — Season Overview | US4 (P2) | T046–T047 | T047 ✓ |
| 8 — Multi-Submission | US5 (P2) | T048–T050 | T050 ✓ |
| 9 — Admin Overview | US7 (P2) | T051–T052 | — |
| 10 — Polish | — | T053–T062 | T054–T059, T061–T062 ✓ |
| **Total** | | **69 tasks** | **~26 parallelisable** |
