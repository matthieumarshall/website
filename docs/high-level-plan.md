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
- Account registration (self-service signup) — *not started*
- Password reset via email — *not started*

### 1.3 Roles & Permissions
- `fastapi-permissions` integration — **DONE**
- `admin` and `content_creator` roles — **DONE**
- Account page (shows username + role badge) — **DONE**
- `team_manager` role — *not started (needed for Entries phase)*

---

## Phase 2: Content & News

### 2.1 Posts / News CRUD
- News listing page with pagination — **DONE**
- Post detail view — **DONE**
- Create / edit / delete posts (content creator / admin only) — **DONE**
- Rich-text editor (Quill) — **DONE**
- Image upload (MIME allowlist, 5 MB cap, staff only) — **DONE**
- HTML sanitisation with `nh3` before DB write — **DONE**
- Publish / draft toggle (column exists in DB, no UI yet) — *not started*

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
- What3Words location support — *not started*
- Course map image uploads (support multiple images per fixture) — **DONE**

---

## Phase 4: Results & Standings

### 4.1 Results History
- Results page (currently a "coming soon" placeholder) — **DONE**
- Display all historical results in web page — **DONE**
- Export results to CSV — **DONE**
- Export results to PDF — **DONE**

### 4.2 Standings
- Calculate standings dynamically per season — *not started*
- Publish historical standings (static data for past seasons) — *not started*

### 4.3 Live / External Data
- Integrate results dynamically from Tempo Events API — *not started*

---

## Phase 5: Entries

### 5.1 Athlete & Category Management
- Team manager role — *not started*
- Add athletes to categories and seasons — *not started*
- Assign competition numbers — *not started*
- Link athletes to their results — *not started*

### 5.3 Payments
- Stripe integration (server-side PaymentIntent via Python `stripe` SDK) — *not started*
- `static/entry-payment.js` island — mounts Stripe Elements widget, submits payment — *not started*
- Post-payment confirmation page (server redirect, no JS) — *not started*
- Webhook handler for async payment events (`/webhooks/stripe`) — *not started*
- Update CSP to allow `js.stripe.com` and `api.stripe.com` (PCI DSS requirement) — *not started*
- Document Stripe cookie / data collection in `templates/privacy.html` — *not started*

### 5.3 GDPR Compliance for Athlete Data
- Lawful basis for processing personal data — *not started*
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
- Sufficient colour contrast ratios (4.5:1 for normal text) — *not started*
- Alt text on all images — *not started*
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
- Automated deployment to production on merge to `main` — *not started*

### 8.2 Production Server
- Production WSGI/ASGI server (Gunicorn or similar) — *not started*
- Dockerfile for reproducible deployments — *not started*
- Environment parity (dev / staging / production) — *not started*
- Rollback procedure documented — *not started*

### 8.3 Hosting
- Fly.io (or equivalent) hosting — *not started*
- HTTPS / SSL certificate (Let's Encrypt via Fly.io or Cloudflare) — *not started*
- Domain registration and DNS configuration — *not started*
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
- `pip-audit` / Dependabot for known CVEs — *not started*
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
