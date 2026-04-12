---
name: run-playwright-tests
description: 'Run and debug Playwright UI tests for the login-page project. Use when: executing the test suite, verifying frontend functionality, debugging test failures, checking test coverage.'
argument-hint: 'Optional: specific test file or test name to run'
---

# Running Playwright Tests

This skill provides a workflow for executing, debugging, and fixing Playwright UI tests in the login-page project.

## When to Use

- Running the full UI test suite or specific tests
- Debugging test failures (console errors, network issues, element visibility)
- Verifying CSS or JavaScript changes don't break existing behaviour
- Adding new UI tests for features or components
- Checking that authentication, HTMX swaps, and modal interactions work end-to-end

## Prerequisites

- Ensure all dependencies are installed: `uv sync`
- Backend application must be running on `http://localhost:8000` (tests start the server automatically)
- No conflicting processes on port 8000

## Test Organization

Tests are located in `tests/ui/`:
- `test_login_flow.py` — Login and authentication flow
- `test_rules_editor.py` — Quill editor integration
- `test_sidebar_navigation.py` — Navigation menu and routing
- `test_fixture_images.py` — Course map image gallery and modal (fixture-images.js)
- `conftest.py` — Shared fixtures: `browser`, `admin_browser`, `server_process`, `admin_auth_state`

## Quick Start: Run All Tests

```bash
uv run pytest tests/ui/ -v
```

Output shows pass/fail for each test and timing. A test session fixture starts the FastAPI server once per session.

## Run Specific Tests

By file:
```bash
uv run pytest tests/ui/test_fixture_images.py -v
```

By test name (includes substring):
```bash
uv run pytest tests/ui/ -k "modal" -v
```

By class:
```bash
uv run pytest tests/ui/test_fixture_images.py::TestFixtureImageModal -v
```

## Debugging Failures

### 1. Check Server Startup

If tests hang on `server_process`, the server may have failed to start:

```bash
# Run server manually to see startup errors
uv run uvicorn website.main:app --reload
```

Fix issues in `.github/copilot-instructions.md` or `pyproject.toml`, then retry.

### 2. Inspect Test Logs

Playwright captures console errors and page errors in the fixture:

```python
page_errors: list[str] = []
admin_browser.on("pageerror", lambda e: page_errors.append(str(e)))
admin_browser.goto(url)
assert not page_errors, f"Uncaught JS errors: {page_errors}"
```

Look for missing routes, failed asset loads, or script errors.

### 3. Debug Network Requests

```python
failed_requests: list[str] = []
admin_browser.on(
    "response",
    lambda r: failed_requests.append(f"{r.url} -> {r.status}")
    if r.status >= 400
    else None,
)
```

Check that XHR/fetch requests return 2xx, CSRF token validation passes, and HTMX routes return the correct HTML fragments.

### 4. Run with Screenshots

Add screenshots to diagnose visual issues:

```python
admin_browser.screenshot(path="debug.png")
```

Then review the image to see rendered HTML, CSS, and DOM state at the moment of failure.

### 5. Run Single Test with Headed Browser

By default, tests run headless (no GUI). To see browser interactions:

```bash
HEADED=1 uv run pytest tests/ui/test_fixture_images.py::TestFixtureImageModal::test_modal_closes_on_escape_key -v
```

(Note: Requires Playwright to be configured with headed support; check `pytest.ini` or `pyproject.toml`)

Alternatively, add `browser.new_context().new_page()` with explicit headless=False in a test fixture.

## Writing New Tests

### Structure

```python
class TestMyFeature:
    """Tests for <feature>."""

    def test_feature_loads(self, admin_browser: Page) -> None:
        """Brief description."""
        admin_browser.goto("http://localhost:8000/my-page")
        admin_browser.wait_for_load_state("networkidle")
        assert admin_browser.locator("h1").is_visible()
```

### Reuse Admin Authentication

The `admin_auth_state` fixture logs in once per session, and `admin_browser` injects those cookies into every test — avoiding rate-limit issues:

```python
def test_admin_only_route(self, admin_browser: Page) -> None:
    admin_browser.goto("http://localhost:8000/administration")
    # Already authenticated, no login request made
```

### Seed Test Data

Add fixtures to `conftest.py`'s `server_process` to create seasons, fixtures, or posts:

```python
season = repository.create_season(con, "Test Season")
repository.create_fixture(
    con,
    season_id=season.id,
    title="Test Fixture",
    date="2026-01-01",
    location_name="Test Venue",
    address="123 Test St",
    timetable=[],
    travel_instructions="",
)
```

Then reference it in tests:

```python
admin_browser.goto("http://localhost:8000/fixtures")
assert admin_browser.locator("text=Test Fixture").is_visible()
```

### Test HTMX Swaps and Modal Interactions

For HTMX:
```python
admin_browser.locator("button[hx-post]").click()
admin_browser.wait_for_selector("#updated-content")  # Wait for swap target
admin_browser.wait_for_load_state("networkidle")  # Wait for XHR complete
```

For modal/dialog:
```python
admin_browser.locator(".trigger").click()
modal = admin_browser.locator("dialog#my-modal")
assert modal.evaluate("el => el.open"), "Modal did not open"
modal.keyboard.press("Escape")
assert not modal.evaluate("el => el.open"), "Modal did not close"
```

## Common Assertions

| Pattern | Checks |
|---------|--------|
| `admin_browser.url.endswith("/path")` | Navigation |
| `admin_browser.locator("h1").is_visible()` | Element visibility |
| `admin_browser.locator(".error").count() == 0` | Zero matches |
| `modal.evaluate("el => el.open")` | Dialog open state |
| `page_errors` list is empty | No uncaught JS exceptions |
| `console_errors` list is empty | No console.error() calls |
| `failed_requests` list is empty | No 4xx/5xx HTTP responses |

## Clean Up After Tests

The `server_process` fixture automatically:
1. Terminates the FastAPI server after all tests
2. Removes the test database file (`test_ui.duckdb`)
3. Closes all Playwright browser contexts

No manual cleanup needed.

## Continuous Integration

Tests run on every CI pipeline via GitHub Actions. Check `.github/workflows/` for the runner configuration:

```yaml
- name: Run Playwright tests
  run: uv run pytest tests/ui/ -v
```

If CI tests fail but local tests pass, check:
- OS differences (Windows vs. Linux file paths)
- Environment variables (DATABASE_URL, PRODUCTION mode)
- Port availability (CI runners may have port 8000 in use)

## References

- Playwright Python docs: https://playwright.dev/python/
- pytest docs: https://docs.pytest.org/
- [Project architecture](../../../copilot-instructions.md) and [frontend guidelines](../.github/instructions/frontend.instructions.md)
