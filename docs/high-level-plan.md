# Project Plan

---

## Architecture

This project uses an **Islands Architecture** on the frontend: pages are server-rendered (FastAPI + Jinja2) with HTMX handling partial updates. JavaScript is introduced only as isolated islands where HTMX is insufficient — each island lives in its own `static/<feature>.js` file.

Existing islands:
- `static/post-editor.js` — Quill rich-text editor (Phase 2)
- `static/timetable-editor.js` — timetable drag/edit UI (Phase 3)
- `static/fixture-map.js` — embedded Leaflet interactive map with self-hosted assets, regional bounding, and fixture-specific scoping (Phase 3)
- `static/fixture-images.js` — client-side image preview and multi-image manager (Phase 3)
- `static/standings-tabs.js` — standings category tab management (Phase 4)
- `static/results-filter.js` — dynamic results searching and filtering (Phase 4)
- `static/rules-editor.js` & `static/rules-toc.js` — rules editing and interactive table of contents (Phase 2)

Planned islands:
- `static/entry-payment.js` — *(superseded)*: Stripe integration was implemented via server-redirected hosted Stripe Checkout rather than an embedded Elements widget, keeping the site free of external JS widgets.

---

## Phase 1: Foundation & Authentication

### 1.1 Security Fundamentals
- Secrets managed via environment variables, never committed to Git — **DONE**
- HTTPS everywhere (SSL/TLS) — *(handled in deployment phase)*
- Parameterised SQL queries to prevent injection — **DONE**
- Jinja2 auto-escaping on (no `| safe` on user data) — **DONE**
- Security headers middleware (CSP, X-Frame-Options, HSTS, etc.) — **DONE**
- CSRF token validation on all state-changing POST routes — **DONE**

### 1.2 Authentication
- Login / logout — **DONE**
- Password hashing with bcrypt (with SHA-256 pre-hash) — **DONE**
- Session management (`SessionMiddleware`, `https_only` in prod, `same_site="lax"`) — **DONE**
- Session fixation protection (clear session before writing on login) — **DONE**
- Rate limiting on login (5 attempts / 15 min in production) — **DONE**
- Password reset via email — *not started*

### 1.3 Roles & Permissions
- `fastapi-permissions` integration — **DONE**
- `admin` and `content_creator` roles — **DONE**
- Account page (shows username + role badge) — **DONE**
- `club_manager` role (team manager equivalent) — **DONE** (`require_club_manager` dependency in `identity.py`)
- User control centre / admin user management (CRUD users, assign roles, reset credentials within the website) — *not started*

---

## Phase 2: Content & News

### 2.1 Posts / News CRUD
- News listing page with pagination — **DONE**
- Post detail view — **DONE**
- Post "see more.." link — **DONE**
- Create / edit / delete posts (content creator / admin only) — **DONE**
- Rich-text editor (Quill) — **DONE**
- Image upload (MIME allowlist, 5 MB cap, staff only) — **DONE**
- HTML sanitisation with `nh3` before DB write — **DONE**
- Custom fonts - **DONE**

### 2.2 Rules & Constitution
- View rules & constitution page — **DONE**
- Edit rules & constitution (rich-text editor, admin / content creator only) — **DONE**
- HTML sanitisation with `nh3` before DB write — **DONE**
- Export rules & constitution to PDF — **DONE**

### 2.3 Other pages
- Divisions — **DONE** (season-linked, staff-managed assignments at `/divisions` and `/admin/divisions` for admin and content creator)
- Past individual and team winners — **DONE** (standings-derived with staff overrides at `/winners` and `/admin/winners` for admin and content creator)
- Links — **DONE** (structured staff-managed external links at `/links` and `/admin/links` for admin and content creator)
  - to national athletics organisations, local clubs, other cross country leagues
- Member clubs — **DONE** (public directory at `/clubs` with staff-managed metadata and website links at `/admin/clubs` for admin and content creator)
- Administration documents store — **DONE** (public categorized downloads at `/administration` in a 2-column grid; staff management at `/administration/manage` supporting section CRUD, reordering, and uploads up to 20 MB with nginx 25 MB proxy support for admin and content creator)
- Legacy content migration scripts — **DONE** (`scripts/upload_legacy_admin_content.py` and `scripts/migrate_admin_documents.py` for legacy administration documents and course/venue maps from the old PHP site)
- Make every page editable via CMS/admin interface (extend static page editing to all public pages: about, contact, etc.) — *planned (to be done soon)*

---

## Phase 3: Fixtures

### 3.1 Season Management
- Create / delete seasons (staff only) — **DONE**
- Season selector with HTMX partial swap — **DONE**

### 3.2 Fixture CRUD
- Create / edit / delete fixtures per season — **DONE**
- Copy fixture — **DONE**
- Fixture detail panel (HTMX tab interaction) — **DONE**
- Timetable editor (JSON array, custom JS) — **DONE**
- Fixture history from past seasons — **DONE**
- Map of location (embedded map from address) — **DONE** (self-hosted Leaflet map loaded in `extra_head`, regional boundary guards skipping invalid or out-of-region coordinates, unique fixture DOM IDs preventing HTMX swap-settling layout bugs)
- What3Words location support. User provides three words in separate small text boxes and we convert that ourselves to a what3words style clickable url — **DONE**
- Course map image uploads (support multiple images per fixture) — **DONE** (`static/fixture-images.js` preview and reordering, multi-upload support)
- Weather forecast integration — *planned* (fetch weather forecast for fixture coordinates/date via a free, open API such as Open-Meteo in advance, and persist/freeze as static historical weather data once race day has passed)
- Upload and display Event license, Risk assessment and Medical Assessment - *not started*
- Copy details from a different fixture, including within that season and previous year - *not started*

---

## Phase 4: Results & Standings

### 4.1 Results History
- Results page (currently a "coming soon" placeholder) — **DONE**
- Display all historical results in web page — **DONE**
- Export results to CSV — **DONE**
- Export results to PDF — **DONE**
- Serve original source PDF for each race (uploaded during migration) — **DONE**

### 4.2 Standings
- Calculate standings dynamically per season — **DONE**
- Publish historical standings (static data for past seasons) — **DONE** (supports spaced round-column headers e.g. "R 1", "R 2", sequence-backed IDs)
- Entries & results reporting and analysis charts — **DONE** (`scripts/generate_entries_report.py` producing per-round and per-season participation trends and cohort breakdowns)

### 4.3 Live / External Data
- Integrate results dynamically from Tempo Events API — *not started*

---

## Phase 5: Entries

**Status**: Fully built (all tasks in `specs/002-team-entries/tasks.md` complete) but currently **hidden from navigation** — the public `/entries` route renders a "work in progress" placeholder pending final production England Athletics TRAPI authentication and full live testing. The underlying backend, models, migrations (0013-0021), Stripe Checkout redirect, BACS/card webhook processing, and admin allocation/pricing management are fully operational.

### 5.1 Athlete & Category Management
- `club_manager` role — **DONE** (`require_club_manager` dependency, admin manager assignment UI)
- Fetch club athletes from England Athletics TRAPI API, compute age category — **DONE** (`src/website/entries.py` with PKCS#12 client cert auth, auto-retry via `tenacity`, category mapping for junior and senior/vet age groups; production live API credentials configured)
- Add athletes to a season as an entry batch — **DONE** (batch draft, validation, and submission)
- Assign competition (race) numbers — **DONE** (`assign_race_numbers`)
- Admin clubs / club-managers management UI — **DONE** (`/admin/clubs`, `/admin/club-managers`)
- Admin pricing, club allocations & season entry config UI — **DONE** (`/admin/entries`, `/admin/entries/{season_id}`)
- Link athletes to their results — *not started (not part of original scope; would need race_number ↔ results matching)*

### 5.2 Payments
- Stripe integration (server-side Checkout Session via Python `stripe` SDK) — **DONE** — implemented as a hosted Stripe Checkout redirect rather than an embedded Elements widget, so no `entry-payment.js` island or CSP change was needed
- Post-payment confirmation page (server redirect, no JS) — **DONE**
- Webhook handler for async payment events (`/webhooks/stripe`) — **DONE** (card + BACS Direct Debit state machine)
- PDF receipt generation (WeasyPrint) — **DONE**

### 5.3 GDPR Compliance for Athlete Data
- Lawful basis for processing personal data — **DONE** (documented as contract/legitimate interest)
- EA athlete data added to `templates/privacy.html` data inventory — **DONE**
- Right to access data (data export) — *not started*
- Right to erasure (deletion flow) — *not started*

---

## Phase 6: Accessibility & Mobile-First Design

### 6.1 Mobile Responsiveness
- Website must be mobile-friendly and responsive across all device sizes (mobile, tablet, desktop) — **DONE** (responsive viewport layouts across phone, tablet, and desktop tested and verified in Playwright)
- Test layout and usability on common mobile devices and screen sizes — **DONE** (Playwright test projects configured for Pixel 5, iPhone 12, and iPad gen 7)
- Ensure touch-friendly interactive elements (sufficient tap target size) — *in progress*

### 6.2 Web Content Accessibility Guidelines (WCAG) 2.1 AA
- Website must be WCAG 2.1 Level AA compliant — **DONE** (all 104 `@axe-core/playwright` accessibility tests passing across desktop, mobile, and tablet viewports)
- Keyboard navigation support for all interactive elements — **DONE** (scrollable `.table-responsive` containers focusable with `tabindex="0"` for Safari/WebKit; Quill toolbar interactive names)
- Proper semantic HTML and ARIA labels where required — **DONE** (ARIA region landmark for cookie banner, accessible command names for rich text toolbars, correct heading hierarchy `<h1>` on `/login`)
- Sufficient colour contrast ratios (4.5:1 for normal text) — **DONE** (custom component variables overriding Bootstrap defaults for `.btn-outline-secondary`, `.btn-outline-primary`, `.btn-outline-danger`, inline `code`, and cookie privacy link)
- Alt text on all images — **DONE**
- Accessible form labels and error messaging — **DONE**
- Screen reader testing (automated via axe-core) — **DONE**
- Automated accessibility testing in CI/CD pipeline — **DONE** (integrated via Playwright `@axe-core/playwright` in `tests/a11y/axe-scan.spec.ts` in CI)

---

## Phase 7: Legal & Compliance

### 7.1 Privacy & Consent
- Privacy policy page — **DONE**
- Cookie consent banner (dismissible, 1-year persistence) — **DONE**
- Terms & conditions page — *not started*

### 7.2 GDPR Operational Requirements
- Data breach notification procedure (internal runbook) — *not started*
- Documented data inventory (what is collected, why, retention) — *not started*

---

## Phase 8: Infrastructure & Deployment

### 8.1 CI/CD
- GitHub Actions pipeline (lint, security scan, tests on push/PR) — **DONE** (Ruff, ty, djlint, pip-audit, gitleaks, bandit, semgrep, license validation, pytest unit tests with coverage, Playwright UI tests, and axe-core a11y tests)
- Automated deployment to production (scheduled nightly + manual dispatch via `deploy.yml`) — **DONE** *(nightly midnight deploy pulls latest `main`, runs migrations, and restarts `oxcross` systemd service)*

### 8.2 Production Server
- Production WSGI/ASGI server (Gunicorn or similar) — **DONE** (Uvicorn managed by systemd under service `oxcross` behind Nginx reverse proxy)
- Nginx reverse proxy upload configuration — **DONE** (25 MB client max body size configured to support 20 MB administrative uploads)
- Environment parity (dev / staging / production) — **DONE** (documented in `docs/environments.md`)
- Rollback procedure documented — *not started*

### 8.3 Hosting
- fasthosts VPS hosting — **DONE**
- HTTPS / SSL certificate (Let's Encrypt / Certbot) — **DONE**
- Domain registration and DNS configuration — **DONE**
- Auto-renewal on domain — *not started*

### 8.4 Database & Backups
- Automated DB backups to off-site storage (S3 / B2) — *not started*
- Test restore from backup (documented and verified) — *not started*

---

## Phase 9: Email

Email hosting and mailboxes are handled directly as a managed email service provided by Fasthosts (`mail.livemail.co.uk`), with DNS records and mailbox migration covered. The website backend does not send transactional emails, so no custom email service integration (Resend/Postmark) or website development work is required now or planned for the future.

- Managed email service via Fasthosts — **DONE**
- Mailbox migration tooling from legacy cPanel host (`scripts/imapsync-sync.ps1`) — **DONE**
- DNS records (MX, SPF, DKIM, autodiscover) configured for Fasthosts mail — **DONE**
- Website-side transactional email integration — *(out of scope / not needed; email handled entirely via managed Fasthosts mailboxes)*

---

## Phase 10: Monitoring & Reliability

### 10.1 Logging
- Structured JSON logging — *not started*
- Ship logs to centralised location — *not started*
- Never log passwords, tokens, or PII — **DONE** *(policy enforced in code)*

### 10.2 Error Tracking & Uptime
- Sentry (or equivalent) for unhandled exception tracking — *not started*
- Uptime monitoring (UptimeRobot / Better Uptime) — *not started*

### 10.3 Bot & Abuse Protection
- Bot restriction / Cloudflare challenge — *not started*
- Login rate limiting already covers brute force — **DONE**

### 10.4 Dependency & Vulnerability Management
- `pip-audit` / Dependabot for known CVEs — **DONE**
- Bandit SAST scan (zero findings required) — **DONE**
- License validation script (`scripts/validate-licenses.py`) — **DONE**

---

## Phase 11: Performance

### 11.1 Asset Optimisation
- Minify CSS/JS, compress images, use modern formats (WebP/AVIF) — *not started*
- gzip/brotli response compression — *not started*
- All static assets self-hosted (no CDN leaking user IPs) — **DONE**

### 11.2 Caching
- Server-side caching for expensive queries (Redis / in-memory) — *not started*

### 11.3 Load Testing
- Establish baseline concurrent-user capacity (`locust` / `k6`) — *not started*

---

## Phase 12: External Integrations, APIs & Embeds

### 12.1 Embeddable Website Widgets
- Embeddable widgets / components for member clubs and external sites (e.g. embeddable standings tables, next fixture card, latest league news via `<iframe>` or lightweight web component) — *planned*
- Appropriate CSP `frame-ancestors` policies and embed parameters to allow member clubs to embed league sections safely — *planned*

### 12.2 Public Developer APIs
- Public read-only JSON REST APIs for external developers and clubs (fixtures, results, standings, member clubs) — *planned*
- Interactive API documentation (OpenAPI / Swagger UI / Redoc) explicitly exposed and documented for programmatic consumption — *planned*
- Rate limiting and API versioning for public endpoints — *planned*
