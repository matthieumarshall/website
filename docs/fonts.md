# Font Setup for Oxfordshire Cross Country League

The website uses a single self-hosted font to avoid CDN dependencies:

- **DM Sans** (variable font) — all text including headings, body, and UI

DM Sans provides a clean, modern, professional appearance suitable for a cross country running league.

## Status

✅ **Fonts are now installed and active!**

Font file in use:
- `static/fonts/dm-sans.ttf` (239 KB — variable font supporting all weights, used for all text)

## How We Set Up the Fonts

1. Downloaded DM Sans from Google Fonts (variable font version)
2. Copied TTF file to `static/fonts/dm-sans.ttf`
3. Updated `static/style.css` with @font-face rule
4. Applied DM Sans to all headings (h1–h6), body text, and navbar brand
5. Font is now serving correctly (HTTP 200)

## Verification

The website is using the font via the `@font-face` rule in `static/style.css`:

```css
@font-face {
  font-family: 'DM Sans';
  src: url('/static/fonts/dm-sans.ttf') format('truetype');
  font-weight: 100 900;  /* Variable font — supports all weights */
  font-display: swap;
}

/* Applied to all text */
h1, h2, h3, h4, h5, h6 {
  font-family: 'DM Sans', sans-serif;
  font-weight: 700;
}

body {
  font-family: 'DM Sans', sans-serif;
}

.navbar-brand {
  font-family: 'DM Sans', sans-serif;
  font-weight: 700;
}
```

To visually confirm the font is active:
1. Run the dev server: `uv run uvicorn website.main:app --reload`
2. Open http://localhost:8000 in your browser
3. Open DevTools (F12) → Elements/Inspector
4. All text (headings, body, navbar) will show `font-family: 'DM Sans'`
5. Headings and navbar brand will use `font-weight: 700` (bold) for visual hierarchy
6. Check Network tab → filter for "fonts/" to confirm dm-sans.ttf loads (200 OK)

## Browser Compatibility

TrueType (TTF) fonts are supported in all modern browsers:
- Chrome/Edge: ✅
- Firefox: ✅
- Safari: ✅
- Mobile browsers: ✅

Variable fonts (dm-sans.ttf) provide a single file that works for any weight (400, 500, 700, etc.), reducing HTTP requests and file size.
