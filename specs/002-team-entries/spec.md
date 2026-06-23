# Feature Specification: Team Entries

**Feature Branch**: `ea_api_start`
**Created**: 2026-06-07
**Status**: Draft
**Input**: Team managers from member clubs must be able to enter athletes for a season, validate EA licenses, and pay via Stripe. Admins manage pricing and view all entries.

---

## Context

The OXL (Oxfordshire Cross Country League) is a 5-fixture season (Nov–Mar). Only EA-affiliated athletes may compete. Member clubs pay a **per-athlete, per-season** entry fee which covers all remaining fixtures from the point of entry. Prices are pro-rated based on fixtures remaining when payment is made. Junior (U9–U17) and adult (U20+) athletes are priced differently.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Team Manager Selects Athletes to Enter (Priority: P1)

A team manager for a member club (e.g. Oxford City AC) logs in and selects athletes from their club's EA membership list to enter into the current season. All displayed athletes have a valid EA license; unlicensed athletes cannot be entered.

**Why this priority**: Core gating requirement — no entries without valid EA license.

**Independent Test**: Can be fully tested by mocking the EA API and verifying that only licensed athletes are shown, and that selecting them creates a pending entry batch.

**Acceptance Scenarios**:

1. **Given** a user with the `club_manager` role logs in, **When** they navigate to `/entries`, **Then** they see a list of active seasons and can select one.
2. **Given** a manager selects a season, **When** the page loads, **Then** the system calls the EA API to fetch all athletes for their club and displays them with name, age category, and registration status.
3. **Given** the EA API returns athletes, **When** the manager views the list, **Then** only athletes with `RegistrationStatus = Registered` are shown as selectable; unregistered athletes are shown as ineligible with a clear reason.
4. **Given** the manager selects athletes, **When** they proceed, **Then** athletes already entered this season by their own club (in any previous batch) are excluded from selection. The same athlete may simultaneously be entered by a different club.
5. **Given** the entry deadline for the next fixture has passed (midday on fixture day), **When** the manager tries to add athletes, **Then** entries are locked and a clear message explains when entries reopen (after that fixture).

---

### User Story 2 — Preview and Pay for Entry Batch (Priority: P1)

The team manager reviews the list of selected athletes, sees the cost breakdown (junior vs adult, pro-rata price), and pays via Stripe Checkout (card or BACS Direct Debit).

**Why this priority**: No payment = no confirmed entry. Pricing transparency is required before payment.

**Independent Test**: Can be tested by mocking Stripe and verifying a Checkout Session is created with correct line items, and that a pending entry batch is stored in the DB.

**Acceptance Scenarios**:

1. **Given** a manager has selected athletes, **When** they view the preview, **Then** they see a table with each athlete's name, age category (junior/adult), and individual price, plus a total.
2. **Given** the season has 3 of 5 fixtures remaining, **When** the price is displayed, **Then** it matches the admin-configured price for `fixtures_remaining = 3`.
3. **Given** the manager clicks Pay, **When** the Stripe Checkout Session is created, **Then** they are redirected to Stripe's hosted checkout page with card and BACS Direct Debit available in GBP.
4. **Given** Stripe completes a card payment, **When** the webhook `checkout.session.completed` fires, **Then** the entry batch status is set to `paid` and race numbers are auto-assigned. Stripe redirects the manager to the success page, which displays a link to the receipt.
5. **Given** a BACS mandate is initiated, **When** the checkout session completes, **Then** the batch status is `payment_initiated` until `charge.succeeded` confirms settlement (T+3–7 days).
6. **Given** a manager cancels on the Stripe page, **When** they return, **Then** the batch is left in `pending_payment` status and no race numbers are assigned.

---

### User Story 3 — Receipt (PDF and Web) (Priority: P1)

After a successful payment (or mandate initiation), the manager receives a confirmation page and can download a branded PDF receipt.

**Why this priority**: Clubs need proof of payment for their records.

**Independent Test**: Can be tested by generating a receipt from a fixture entry row and asserting all required fields appear in both the HTML and PDF responses.

**Acceptance Scenarios**:

1. **Given** an entry batch is in `paid` or `payment_initiated` status, **When** the manager visits `/entries/{season_id}/batch/{batch_id}/receipt`, **Then** they see a web receipt showing: OXL logo, season, club, manager name, date, payment method, athlete list with race numbers, price per athlete, and total.
2. **Given** the manager clicks "Download PDF", **When** the PDF is generated, **Then** it matches the web receipt content and is returned as `application/pdf`.
3. **Given** the batch is `pending_payment` or `payment_failed`, **When** the manager tries to view the receipt, **Then** a 404 or redirect to the payment page is returned.

---

### User Story 4 — View All Entered Athletes for a Season (Priority: P2)

Any team manager can view a read-only list of all athletes entered for the current season across all clubs.

**Why this priority**: Transparency between clubs for season planning.

**Independent Test**: Can be tested by inserting entries for two clubs and asserting both appear in the aggregate view for any authenticated manager.

**Acceptance Scenarios**:

1. **Given** a manager is logged in, **When** they visit `/entries/{season_id}`, **Then** they see a table of all entered athletes grouped by club (from `paid` or `payment_initiated` batches), with name, age category, and race number.
2. **Given** the manager views another club's entries, **Then** no edit or delete controls are shown — it is read-only.
3. **Given** no entries exist yet for a season, **When** the manager visits the season entries page, **Then** an empty state is shown with a prompt to add athletes.

---

### User Story 5 — Multiple Submissions per Season (Priority: P2)

A team manager can submit additional athletes mid-season (after some fixtures have already occurred). Each submission is a separate payment batch with its own receipt.

**Why this priority**: Clubs may have new members join or late registrations throughout the season.

**Independent Test**: Can be tested by creating two entry batches for the same club/season and asserting: different fixtures_remaining values, different totals, and no duplicate ea_urn per season.

**Acceptance Scenarios**:

1. **Given** a manager has already paid for a batch this season, **When** they visit the entries page, **Then** they see a button to add more athletes.
2. **Given** the manager adds more athletes in a second batch, **When** they pay, **Then** the price reflects the current fixtures remaining (lower than the first batch if fixtures have passed).
3. **Given** a manager tries to add an athlete already entered by their own club in a previous batch, **When** the system validates, **Then** that athlete is excluded from selection and shown as "already entered by your club".

---

### User Story 6 — Admin Price Management (Priority: P1)

An admin can set and modify the entry price lookup table for a season (junior and adult price per fixtures-remaining count).

**Why this priority**: Prices must be configurable before entries open each season and adjustable if the AGM votes to change them.

**Independent Test**: Can be tested by updating a price tier via the admin form and verifying the new price appears on the next entry batch preview.

**Acceptance Scenarios**:

1. **Given** an admin visits `/admin/entries/{season_id}/pricing`, **When** the page loads, **Then** they see the current price tiers (fixtures remaining 1–5, junior price, adult price).
2. **Given** the admin edits a tier and saves, **When** a team manager next creates a batch, **Then** the new price is used.
3. **Given** existing paid batches exist, **When** the admin changes a price, **Then** existing receipts are unaffected (prices are snapshotted at batch creation time).

---

### User Story 7 — Admin Entries Overview (Priority: P2)

An admin can view all entries across all clubs, seasons, and payment statuses from a single dashboard.

**Why this priority**: Needed for league administration, reconciliation, and chasing unpaid batches.

**Acceptance Scenarios**:

1. **Given** the admin visits `/admin/entries`, **When** the page loads, **Then** they see a filterable table: season, club, manager, athletes entered, total paid, payment status.
2. **Given** the admin selects a specific season, **Then** the table shows per-club totals and individual athlete detail on drill-down.
3. **Given** a batch is in `payment_initiated` (BACS pending), **Then** a clear indicator distinguishes it from `paid` (card, settled) and `pending_payment` (not yet paid).

---

### User Story 8 — Admin Club Management (Priority: P1)

An admin can create and manage the list of OXL member clubs, including each club's EA club ID which is used to fetch athletes from the EA API.

**Why this priority**: Club records (with EA club ID) must exist before any manager can be linked to a club or any EA API call can be made.

**Independent Test**: Create a club via admin form; verify it appears with correct EA club ID; attempt to deactivate a club with active batches and verify it is rejected.

**Acceptance Scenarios**:

1. **Given** the admin visits `/admin/clubs`, **When** the page loads, **Then** they see all clubs with name, OXL code, EA club ID, and active status.
2. **Given** the admin submits the create form with a unique `oxl_code` and numeric `ea_club_id`, **When** saved, **Then** the club appears in the list.
3. **Given** a club has active `entry_batches`, **When** the admin tries to deactivate it, **Then** a 409 error explains the club cannot be deactivated while batches exist.
4. **Given** the admin updates a club's EA club ID, **When** a manager next runs the entry flow, **Then** the EA API is called with the updated ID.

---

### User Story 9 — Admin Club Manager Account Creation (Priority: P1)

An admin creates team manager user accounts and assigns each to a club. Managers do not self-register.

**Why this priority**: Without manager accounts, no club can enter athletes.

**Independent Test**: Create a manager account via admin form; log in as that manager; confirm `/entries` is accessible and shows the correct club.

**Acceptance Scenarios**:

1. **Given** the admin visits `/admin/club-managers`, **When** the page loads, **Then** they see all managers with username, club, and active status.
2. **Given** the admin submits the create form (username, email, password, club), **When** saved, **Then** a user with `role='club_manager'` is created, linked to the selected club, and can log in immediately.
3. **Given** the admin deactivates a manager, **When** that manager tries to create a new entry batch, **Then** they receive a 403 error. Existing paid batches are unaffected.

---

## Out of Scope

- Self-registration for team managers (admin-created only).
- Automated refund flows (admin uses Stripe dashboard).
- Results linking (race numbers linking entries to results handled separately).
- Affiliation fee collection (club fees are separate from athlete entry fees).
