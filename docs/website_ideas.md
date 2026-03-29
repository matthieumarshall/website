# Website Development & Hosting Considerations

## 1. Security

| Area | What to Think About |
|---|---|
| **HTTPS everywhere** | SSL/TLS certificates (free via Let's Encrypt or Cloudflare). Never serve login forms or payments over HTTP. |
| **Authentication** | Hash passwords properly (bcrypt/argon2, never MD5/SHA1). Session management, CSRF tokens, secure cookies. |
| **Input validation** | Sanitize all user input. Protect against SQL injection, XSS, command injection. |
| **Secrets management** | API keys, database credentials, and Flask secret keys should be in environment variables — never committed to Git. |
| **Dependencies** | Keep packages updated. Use `pip audit` or Dependabot to catch known vulnerabilities. |
| **Headers** | Set security headers: `Content-Security-Policy`, `X-Frame-Options`, `Strict-Transport-Security`, etc. |

## 2. Database

| Area | Details |
|---|---|
| **Choice** | SQLite works for small sites but doesn't handle concurrent writes well. PostgreSQL is the standard for production. |
| **Backups** | Automated, regular backups. Test restoring them. A backup you've never tested is not a backup. |
| **Migrations** | Use a migration tool (Alembic for SQLAlchemy) so schema changes are versioned and repeatable. |
| **Connection pooling** | In production, use connection pooling (PgBouncer or SQLAlchemy's built-in pool) to avoid exhausting connections. |

## 3. Deployment & Infrastructure

| Area | Details |
|---|---|
| **WSGI server** | Never use Flask's dev server in production. Use **Gunicorn** or **uWSGI** behind a reverse proxy. |
| **Containerization** | A Dockerfile makes deployments reproducible across environments. |
| **CI/CD** | Automate testing and deployment. GitHub Actions → run tests → deploy to Fly.io on merge. |
| **Environment parity** | Dev, staging, and production should be as similar as possible. |
| **Rollbacks** | Have a plan to revert to a previous version quickly if a deploy breaks things. |

## 4. Performance

| Area | Details |
|---|---|
| **Caching** | Cache static assets aggressively (CDN). Consider server-side caching (Redis) for expensive queries. |
| **Compression** | Enable gzip/brotli for responses. |
| **Asset optimization** | Minify CSS/JS. Compress images. Use modern formats (WebP, AVIF). |
| **Load testing** | Know how many concurrent users your setup handles before real traffic arrives. Tools: `locust`, `k6`, `wrk`. |

## 5. Monitoring & Logging

| Area | Details |
|---|---|
| **Uptime monitoring** | Use a service (UptimeRobot, Better Uptime — free tiers exist) to alert you if the site goes down. |
| **Application logging** | Structured logs (JSON). Ship to a centralized location. Don't log sensitive data (passwords, tokens). |
| **Error tracking** | Sentry (free tier) catches unhandled exceptions and gives you stack traces from production. |
| **Metrics** | Track response times, error rates, CPU/memory. Fly.io provides basic metrics out of the box. |

## 6. Legal & Compliance

| Area | Details |
|---|---|
| **Privacy policy** | Required if you collect any personal data. Legally required in EU (GDPR), California (CCPA), and increasingly everywhere. |
| **Cookie consent** | If you use cookies beyond strictly necessary ones (analytics, tracking), you need a consent banner in the EU. |
| **Terms of service** | Define acceptable use, liability limits, dispute resolution. |
| **GDPR** | If you have EU users: right to access data, right to deletion, data breach notification within 72 hours, lawful basis for processing. |
| **PCI DSS** | If handling payments — use tokenized payment forms (Stripe Elements) to stay out of scope. |
| **Accessibility (a11y)** | WCAG 2.1 compliance — semantic HTML, alt text, keyboard navigation, color contrast. Increasingly a legal requirement. |

## 7. Email

| Area | Details |
|---|---|
| **Transactional email** | Password resets, confirmations, receipts. Use a service: Resend, Postmark, SendGrid, Mailgun. Don't send from your own server (you'll land in spam). |
| **SPF/DKIM/DMARC** | DNS records that prove your emails are legitimate. Required for deliverability. |

## 8. Backups & Disaster Recovery

| Area | Details |
|---|---|
| **Code** | Git. |
| **Data** | Automated DB backups to a separate location (S3, B2). |
| **Recovery plan** | Document how to restore from scratch: provision server, restore DB, deploy code, update DNS. Test it once. |

## 9. Domain & DNS

| Area | Details |
|---|---|
| **Registrar** | Keep domain registration separate from hosting. Cloudflare Registrar charges at cost (no markup). |
| **DNS TTL** | Set low TTLs (300s) before making changes, raise them after. |
| **Email records** | MX records if you want email on your domain. |
| **Renewal** | Enable auto-renewal. Expired domains get sniped fast. |

## 10. Cost Awareness

| Item | Typical Range |
|---|---|
| **Domain** | $10–15/year |
| **Hosting (Fly.io)** | Free tier for small apps, ~$5–20/month for production |
| **Database (managed)** | $0–15/month (Fly Postgres, Supabase, Neon have free tiers) |
| **Email service** | Free tier usually covers low volume |
| **Cloudflare** | Free for basic CDN/DNS/DDoS |
| **Monitoring/Sentry** | Free tiers available |
| **Payment processor** | ~2.9% + 30¢ per transaction |

## Priority Order (Local → Production)

1. **Secrets out of code** → environment variables
2. **Production WSGI server** → Gunicorn + Dockerfile
3. **HTTPS** → handled by Fly.io + Cloudflare
4. **CI/CD** → GitHub Actions to run tests on push
5. **Database backups** → automated, off-site
6. **Monitoring** → uptime check + Sentry
7. **Legal pages** → privacy policy, terms
8. **Everything else** → iterate as you grow
