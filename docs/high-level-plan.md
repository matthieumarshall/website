# Project Plan

---

## Architecture

This project uses an **Islands Architecture** on the frontend: pages are server-rendered (FastAPI + Jinja2) with HTMX handling partial updates. JavaScript is introduced only as isolated islands where HTMX is insufficient — each island lives in its own `static/<feature>.js` file.

Existing islands:
- `static/post-editor.js` — Quill rich-text editor (Phase 2)
- `static/timetable-editor.js` — timetable drag/edit UI (Phase 3)

Planned islands:
- `static/entry-payment.js` — Stripe.js payment widget (Phase 5); note Stripe.js must be loaded from `js.stripe.com` (PCI DSS requirement — documented exception to the self-hosting rule)

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

---

## Phase 2: Content & News

### 2.1 Posts / News CRUD
- News listing page with pagination — **DONE**
- Post detail view — **DONE**
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
- Divisions — **DONE** (season-linked, admin-managed assignments)
- Past individual and team winners — **DONE** (standings-derived with admin overrides)
- Links — **DONE** (structured admin-managed external links)
  - to national athletics organisations, local clubs, other cross country leagues
- Member clubs — **DONE** (public directory with admin-managed metadata)

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
- Map of location (embedded map from address) — **DONE**
- What3Words location support. User provides three words in separate small text boxes and we convert that ourselves to a what3words style clickable url — **DONE**
- Course map image uploads (support multiple images per fixture) — **DONE**

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
- Publish historical standings (static data for past seasons) — **DONE**

### 4.3 Live / External Data
- Integrate results dynamically from Tempo Events API — *not started*

---

## Phase 5: Entries

**Status**: Fully built (all tasks in `specs/002-team-entries/tasks.md` complete) but currently **hidden from navigation** — the `/entries` route renders a "work in progress" placeholder pending a reliable EA API authentication fix (see `fix/ea-api-integration` branch). Once that's resolved, re-add the nav link and flip the route back to the real flow. Also still in need of full testing of stripe integration. Still work in progress.

### 5.1 Athlete & Category Management
- `club_manager` role — **DONE**
- Fetch club athletes from England Athletics TRAPI API, compute age category — **** (`src/website/entries.py`) — *blocked on production auth reliability*
- Add athletes to a season as an entry batch — **DONE**
- Assign competition (race) numbers — **DONE** (`assign_race_numbers`)
- Admin clubs / club-managers management UI — **DONE**
- Admin pricing & season entry config UI — **DONE**
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
- Website must be mobile-friendly and responsive across all device sizes (mobile, tablet, desktop) — *in progress*
- Test layout and usability on common mobile devices and screen sizes — *not started*
- Ensure touch-friendly interactive elements (sufficient tap target size) — *not started*

### 6.2 Web Content Accessibility Guidelines (WCAG) 2.1 AA
- Website must be WCAG 2.1 Level AA compliant — *in progress*
- Keyboard navigation support for all interactive elements — *not started*
- Proper semantic HTML and ARIA labels where required — *not started*
- Sufficient colour contrast ratios (4.5:1 for normal text) — **DONE**
- Alt text on all images — *started*
- Accessible form labels and error messaging — *not started*
- Screen reader testing (NVDA, JAWS) — *not started*
- Automated accessibility testing in CI/CD pipeline — *not started*

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
- GitHub Actions pipeline (lint, security scan, tests on push/PR) — **DONE**
- Automated deployment to production (scheduled nightly + manual dispatch via `deploy.yml`) — **DONE** *(not yet triggered directly on merge to `main`)*

### 8.2 Production Server
- Production WSGI/ASGI server (Gunicorn or similar) — **DONE**
- Environment parity (dev / staging / production) — *not started*
- Rollback procedure documented — *not started*

### 8.3 Hosting
- fasthosts VPS hosting — **DONE**
- HTTPS / SSL certificate (Let's Encrypt via Fly.io or Cloudflare) — **DONE**
- Domain registration and DNS configuration — **DONE**
- Auto-renewal on domain — *not started*

### 8.4 Database & Backups
- Automated DB backups to off-site storage (S3 / B2) — *not started*
- Test restore from backup (documented and verified) — *not started*

---

## Phase 9: Email

### 9.1 Transactional Email
- Password reset emails — *not started*
- Account confirmation emails — *not started*
- Use a managed email service (Resend / Postmark / SendGrid) — *not started*

### 9.2 Email Deliverability
- SPF / DKIM / DMARC DNS records — *not started*

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
