---
description: "Use when writing, reviewing, or refactoring HTML templates, CSS, or JavaScript files. Covers Jinja2 templating, HTMX patterns, vanilla JS conventions, accessibility, and XSS prevention for this project."
applyTo: "{templates/**/*.html,static/**/*.{js,css}}"
---

# Frontend Coding Standards

## Architecture: Islands Pattern

This project uses an **Islands Architecture**: pages are server-rendered Jinja2 HTML by default; JavaScript is only introduced as isolated "islands" of interactivity where HTMX alone is insufficient.

Existing islands:
- `static/post-editor.js` — mounts a Quill rich-text editor inside a server-rendered form
- `static/timetable-editor.js` — custom JS island for the timetable UI on fixtures

Each island:
- Lives in its own `static/<feature>.js` file
- Is initialised by finding a sentinel `<div id="...">` that the Jinja2 template renders
- Communicates with the server via a hidden `<input>` field (serialised JSON or plain value) submitted with the surrounding form, or via `fetch` for async operations
- Must not break the page if JavaScript is disabled (degrade gracefully)

**When to add a new island vs. use HTMX**: if the interaction requires a third-party JS SDK (e.g. Stripe.js for payments), client-side state across multiple steps, or rich drag-and-drop/canvas UI — create a new island file. For anything else (partial swaps, form submissions, tab switching) use HTMX.

## General Principles

- **HTMX first**: reach for `hx-*` attributes before writing any JavaScript. Only add a `.js` file when the interaction cannot be expressed with HTMX alone.
- **Semantic HTML**: use the right element for the job (`<button>`, `<nav>`, `<main>`, `<form>`, etc.) — do not use `<div>` for everything.
- **Accessibility**: every form control needs a `<label>`. Interactive elements must be keyboard-reachable. Maintain sufficient colour contrast (WCAG 2.1 AA).
- **Minimal frameworks**: avoid React, Vue, Alpine, or CSS-in-JS unless an island explicitly requires one. Keep the stack minimal.

## Jinja2 Templates

- Auto-escaping is always on — avoid `{{ value | safe }}` on user-supplied data. When rendering server-sanitised HTML (e.g. post content cleaned by `nh3`), `| safe` is acceptable — but never apply it to raw user input.
- Keep logic out of templates: use template variables and simple conditionals only. Complex decisions belong in the route handler or a helper.
- Extend `base.html` for every full-page template; use `{% block %}` for page-specific content.
- Pass only the data a template needs — avoid passing entire ORM objects or large dicts.

```html
{# Good — explicit variables #}
{{ username }}

{# OK — content was sanitised server-side by nh3 #}
{{ post.content | safe }}

{# Bad — bypasses XSS protection on raw user input #}
{{ raw_html | safe }}
```

## HTMX

Use HTMX attributes for all partial page updates:

| Attribute | Purpose |
|-----------|---------|
| `hx-get` / `hx-post` | Trigger a request |
| `hx-target` | CSS selector of the element to update |
| `hx-swap` | How to swap the response (`innerHTML`, `outerHTML`, `beforeend`, …) |
| `hx-indicator` | Show a loading spinner during the request |
| `hx-push-url` | Update the browser URL bar for navigable states |

- FastAPI endpoints that serve HTMX responses must return **HTML fragments**, not JSON.
- Always set `hx-target` explicitly; avoid relying on default same-element replacement for clarity.
- Use `hx-boost` on `<a>` tags to progressively enhance navigation without JS.

```html
<!-- Good — HTMX partial update -->
<button hx-post="/logout" hx-target="#user-status" hx-swap="outerHTML">
  Log out
</button>

<!-- Bad — unnecessary JS for something HTMX handles -->
<button onclick="fetch('/logout', {method:'POST'}).then(...)">Log out</button>
```

## JavaScript

Only write JS when HTMX cannot express the interaction (e.g. client-side validation feedback, focus management).

- Files live in `static/`. One file per feature; no bundler needed.
- Use `"use strict";` at the top of every JS file.
- Use `const` by default, `let` when reassignment is needed; never `var`.
- Use `addEventListener` — prefer this over inline `onclick` / `onsubmit` attributes. Simple confirmation dialogs (e.g. `onsubmit="return confirm(...)"`) are acceptable when they avoid adding a dedicated JS file.
- Prefer `textContent` over `innerHTML` for inserting server-provided data into the DOM. Exception: rich-text editors like Quill require `innerHTML` to function — this is acceptable when the content has been sanitised server-side.

```js
// Good — safe DOM insertion
el.textContent = serverProvidedValue;

// OK — Quill editor integration (content sanitised by nh3 on the server)
contentInput.value = quill.root.innerHTML;

// Bad — XSS risk with unsanitised data
el.innerHTML = serverProvidedValue;
```

## CSS (`static/style.css`)

- Keep it minimal — prefer browser defaults and semantic HTML over utility-class frameworks.
- Use CSS custom properties (`--color-primary`) for repeated values.
- Avoid `!important`; fix specificity issues by restructuring selectors.
- Mobile-first: base styles for small screens, `@media (min-width: …)` for larger.

## Security

- Never reflect user input back into the page without escaping — Jinja2 handles this automatically as long as `| safe` is not used.
- Set `Content-Security-Policy` in the backend to block inline scripts and restrict `src` origins.
- Form submissions that change state must include a CSRF token (rendered as a hidden field from the backend).

## GDPR & Privacy

- **No CDN resources**: all CSS, JavaScript, and fonts must be served from `/static/`. Loading resources from external domains (e.g. CDNs) sends user IP addresses to third parties without consent. Always self-host.
- **No tracking scripts**: do not add analytics, advertising, or telemetry scripts (e.g. Google Analytics, Hotjar) without first updating the privacy policy, adding a consent mechanism, and getting approval.
- **Cookie notice**: `base.html` renders a cookie notice banner controlled by the `show_cookie_notice` context variable. Do not remove this banner or suppress it without a justified reason.
- **Privacy policy link**: the footer of `base.html` must always link to `/privacy-policy`. Do not remove this link.
- **New cookies**: any new cookie set by the backend must be documented in `templates/privacy.html` with its purpose, duration, and legal basis before deployment.
