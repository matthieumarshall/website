---
name: migrate-old-website
description: "Assess and migrate content from the old PHP website (data/original_website/) to the new FastAPI site. Use when: planning what to migrate, uploading course maps or results PDFs, deciding what to discard, mapping old URLs to new routes."
argument-hint: "Optional: specific category to focus on (e.g. 'course maps', 'results PDFs', 'news posts', 'images')"
---

# Migrating Content from the Old Website

The old website (`data/original_website/`) was a PHP + MySQL site (circa 2007–2022).
The new site is FastAPI + DuckDB. This skill guides what to keep, what to discard, and how to migrate each category.

## Quick Reference: Keep vs Discard

| Category | Decision | Destination in new site |
|---|---|---|
| `files/results/` PDFs | **KEEP** | Serve as static downloads; link from fixtures/results pages |
| `files/courses/` PDFs & PNGs | **KEEP** | Upload as fixture images via admin → fixture detail |
| `files/maps/` venue maps | **KEEP** | Upload as fixture images (venue location context) |
| `favicon.ico` | **KEEP** | Copy to `static/favicon.ico` |
| `images/` venue photos | **KEEP (selective)** | Upload as fixture images; see list below |
| Sponsor logos in `images/` | **KEEP (if current)** | Upload to `data/uploads/` or embed in a post |
| `images/shields/` club shields | **KEEP** | Reserve for future club pages feature |
| `files/memfees/2022/`, `2023/`, `2024/` | **KEEP** | Link from a news/post or entries page |
| `files/occchamps/archives/` | **KEEP** | Historical reference; link from a post if needed |
| `files/racenos/blank race number.pdf` | **KEEP** | Link from administration / entries page |
| `files/tminfo/2022-23/` CSV templates | **KEEP (if still current)** | Link from administration page |
| `sitemap.xml` | **KEEP as reference** | Use to plan URL redirects (old → new) |
| `robots.txt` | **KEEP as reference** | Update for new site and serve at `/robots.txt` |
| All `.php` source files | **DISCARD** | Functionality replaced by FastAPI routes |
| `css/` directory | **DISCARD** | Replaced by Bootstrap + `static/style.css` |
| `js/` directory | **DISCARD** | Old GA tracking + cookie control replaced |
| `jquery-1.3.js` | **DISCARD** | Ancient (2008); replaced by HTMX + vanilla JS |
| `.htaccess`, `.htpasswd` | **DISCARD** | Apache config; site now runs on uvicorn |
| `error_log` files | **DISCARD** | Server logs, no value |
| `news/` PHP system | **DISCARD** | Replaced by Posts in the new site |
| `events/` PHP system | **DISCARD** | Replaced by Fixtures in the new site |
| `admin/` PHP system | **DISCARD** | Replaced by new `/administration` route |
| `oxl-lists/phplist-3.3.3/` | **DISCARD** | Old mailing list software (not used) |
| `oaaDropbox/` | **DISCARD** | Empty folder |
| `rss/oxonxc.xml` | **DISCARD** | Old RSS; build a new feed if required |
| `cgi-bin/` | **DISCARD** | Old CGI scripts |
| `googlea084da83e6342305.html` | **DISCARD** | Re-verify Google Search Console with new site |
| `156CC7B739A1C84AAB661BEB57D19CF7.txt` | **DISCARD** | Old domain verification token |
| `.well-known/` | **DISCARD** | Re-verify with new hosting |
| Year-specific event banners in `images/` | **DISCARD** | Old branding; superseded each year |
| UI chrome images (header.gif, spacer.gif, bands.gif etc.) | **DISCARD** | Old PHP template graphics |
| `images/online-entries/` | **DISCARD** | Screenshots of old online-entry system |
| `images/buttons/` | **DISCARD** | Old UI button images; replaced by Bootstrap |
| `images/download-icon-*.png`, `images/route-map-icon-*.png`, `images/MapPinIcon.png` | **DISCARD** | Old icon set; replaced by Bootstrap Icons |
| `files/entries/2007entry.pdf` | **DISCARD** | 2007 entry form; no longer relevant |
| `files/uka/` | **DISCARD** | 2015 UKA age-group consultation docs; very old |
| `files/scantest/` | **DISCARD** | Ad-hoc scan test photos |
| `files/ctntmp/` | **DISCARD** | Old temporary team sheet (2017-18) |
| `news/archive/` `.orig` files | **DISCARD** | Backup copies of old PHP files |
| `info.php` | **DISCARD** | PHP server info page; never expose publicly |

---

## Selective Images to Keep from `images/`

Keep venue photos that are still accurate; discard dated banners and UI chrome:

| Keep | Reason |
|---|---|
| `culham1.jpg` – `culham12.jpg` | Culham venue photos; may be used on fixture detail pages |
| `cir2008.jpg`, `cir2008_sm.jpg` | Cirencester venue photo |
| `radley.gif`, `culham.gif` | Classic venue images |
| `CulhamPermit.jpg` | Permit document scan |
| `CarMap.pdf`, `culham-course2.pdf`, `RadleyLocations.pdf`, `RadleyPermit.pdf`, `RadleyCollege.pdf`, `RiskAssessment.pdf` | Venue operational documents |
| `Fit2Run_MailLogoMX.png`, `GazKazLogoMX_BlueBgnd.png`, `OxfordMail_WebLogo-sml.png` | Sponsor logos (if still current sponsors) |
| `OxonAA_Logo-WhiteOutline-sml.png` | Oxon AA logo; useful in footers or posts |

Discard:
- All `*Banner*` and `*MailBanner*` images (year-specific, old branding)
- `spacer.gif`, `w3cval.png`, `header.gif`, `header2.gif`, `bands.gif`, `oxmail.gif`
- `oxl_20XX*.jpg` event action photos (low-res, year-tagged; not needed in templates)

---

## How to Migrate Each Category

### Results PDFs (`files/results/`)

These are the primary historical archive (1987–2026). They are already organised by decade then season.

1. Decision: host as direct downloads from the new site, linked from the relevant fixture detail page.
2. Copy PDFs to `data/uploads/results/` (maintaining the season folder structure).
3. In the fixture admin, add a download link field, or create a static `/results/archive` page.
4. For seasons already on OpenTrack (2021-22 onwards), the PDF is a backup — prefer the live OpenTrack results.

### Course Maps (`files/courses/`)

One folder per venue, multiple PDFs/images per folder (one per season).

1. For each active venue, identify the **most recent** course map file.
2. Upload via admin: go to the fixture detail for that venue, use the fixture images upload.
3. Attach the PDF/image as a fixture image with an appropriate label (e.g. "Course Map 2024").
4. Older course maps from inactive venues can be kept as an archive but don't need to be linked.

### Venue Maps (`files/maps/`)

One image per venue showing the broader area/parking.

1. Upload to the relevant fixture detail as a fixture image (label: "Venue Map").
2. Some venues (e.g. Culham, Radley) also have PDF location guides in `images/` — upload those too.

### Favicon

```powershell
Copy-Item data\original_website\favicon.ico static\favicon.ico
```

Then add to `templates/base.html`:
```html
<link rel="icon" href="/static/favicon.ico">
```

### News / Posts

The old news content was stored in a **MySQL database** — the PHP files only contain the display logic, not the data. There is no data dump in `data/original_website/`.

Options:
- Contact the old hosting provider to export the MySQL `news` table.
- If an export is available, write a one-off import script in `scripts/` to INSERT rows into the DuckDB `posts` table.
- Otherwise, manually recreate important news items as posts in the new admin UI.

### Events / Fixtures

Similarly stored in MySQL. The fixture structure in the new site (seasons → fixtures → races) already covers this. Re-enter any needed upcoming fixtures via the admin UI.

### URL Redirects

The old site used URLs like `/news/index.php?viewnews=42` and `/files/results/…/result.pdf`.
Use `sitemap.xml` to identify all old public URLs and add FastAPI `RedirectResponse` routes or a catch-all redirect in `main.py` for legacy paths.

---

## File Counts (for planning)

| Path | Approx count |
|---|---|
| `files/results/` | ~70 PDFs across 8 decade folders |
| `files/courses/` | ~55 PDFs/images across 18 venue folders |
| `files/maps/` | ~30 images |
| `images/` (keep subset) | ~20 files |

---

## What NOT to Do

- Do not commit any files from `data/original_website/` to git (it is gitignored via `data/`).
- Do not copy old `.htaccess` rules into the FastAPI app — translate them to proper routes.
- Do not use the old PHP admin credentials — the `.htpasswd` file should be discarded.
- Do not serve `info.php` on the new site — it exposes server configuration.
