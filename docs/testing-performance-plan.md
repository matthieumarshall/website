# Testing performance improvement plan

Date: 2026-11-22

Status: implementation in progress; performance targets require repeated comparable measurements

## Aim

Speed up local feedback and CI by reducing repeated fixture setup, browser
startup, unnecessary waits, and sequential browser-suite execution. Preserve the
existing test coverage and independently runnable unit and browser suites.

The earlier workflow improvements are already present:

- Default pytest and `just test` run the unit suite.
- The pre-push hook selects impacted unit tests against `origin/main`.
- CI runs the full unit suite with coverage.
- Unit and UI CI jobs run independently.
- `just test-ui` runs both Python UI and Node accessibility/mobile tests.

## Baseline measurements

Inspected checkout: `feat/editable-info-and-health`, commit `eb175e5`.

### Local

Command:

```powershell
uv run --no-sync pytest tests/unit -q --durations=20
```

- Python: 3.14.3 on Windows.
- Result: 714 passed, 4 integration tests deselected, 16 warnings.
- Wall time: 218.55 seconds (3 minutes 39 seconds).
- Pytest-reported time: 212.46 seconds.
- Coverage was not collected for this run.
- Nineteen of the twenty slowest reported phases were test setup, commonly for
  authenticated route tests.

Small local probes identified these setup costs:

| Operation | Median time |
| --- | ---: |
| Create, migrate, and close a fresh in-memory database | 200 ms |
| Copy a closed migrated database template, open, query, and close it | 61 ms |
| Hash and verify a password using the current implementation | 658 ms |
| Launch Chromium, create a context and page, then close everything | 527 ms |
| Create a fresh context and page in an existing browser, then close the context | 127 ms |

Database probes used eight samples, password probes three, and browser probes
five. These diagnostic probes ran while the unit benchmark was active, so they
are indicative rather than isolated before/after performance results. Database
cloning still needs validation against actual test workloads.

### CI

Source: [successful CI run 45035980156](https://github.com/matthieumarshall/website/actions/runs/45035980156),
for the same branch commit, on 2026-11-22.

| CI measurement | Time |
| --- | ---: |
| Unit job, including setup and reporting | 190 seconds |
| Unit tests and coverage step | 177 seconds |
| UI job, including setup and reporting | 504 seconds |
| Browser installation | 89 seconds |
| Python UI test step | 150 seconds |
| Accessibility/mobile test step | 242 seconds |
| Code quality job | 22 seconds |
| Security and compliance job | 40 seconds |

The UI job is the critical path: browser installation and the two browser suites
run sequentially. The run passed 112 Python UI tests and 140 Node
accessibility/device cases. Node used one worker across four device projects.

These are single-run observations. Runner setup and download times vary, and the
local run without coverage is not directly comparable to CI with coverage.

## Proposed changes

### 1. Reduce unit fixture setup costs

Primary file: [tests/unit/conftest.py](../tests/unit/conftest.py).

- Build and close a fully migrated database template once per test session.
- Copy it into a separate temporary database for each test, preserving isolated
  data, schema, sequences, and transaction state.
- Build the template afresh on each invocation so migration changes are included.
- Keep migration-specific tests exercising real creation and upgrade paths.
- Reuse password/hash pairs in general user fixtures while retaining separate
  users and per-test database isolation.
- Keep real hashing, verification, and login coverage in authentication tests;
  leave production password hashing settings unchanged.

Validate copied databases against the current suite, including transaction and
rollback tests, sequence-generated IDs, and a direct check that one test's
mutations cannot affect another test.

### 2. Reduce browser execution overhead

Primary files:

- [tests/ui/conftest.py](../tests/ui/conftest.py)
- [tests/ui/test_information_status.py](../tests/ui/test_information_status.py)
- [tests/a11y/axe-scan.spec.ts](../tests/a11y/axe-scan.spec.ts)

Changes:

- Reuse a session-scoped browser process while creating a fresh context and page
  for every test. Retain existing role-specific authentication state.
- Replace the status test's 30.5-second polling wait with a controlled browser
  clock, retaining the assertion that the polling request occurs.
- Replace blanket `networkidle` waits with assertions for the content or network
  response required by each test. Ensure editors and dynamic content are ready
  before interaction or accessibility scans.
- Reuse authenticated storage state in Node accessibility tests instead of
  logging in before every staff or manager page check.
- Replace the server's fixed five-second startup sleep with bounded readiness
  polling that also detects early server failure.

Fresh browser contexts isolate cookies and browser storage, but do not isolate
server-side data. Keep the existing mutation-sensitive tests serial until their
server/database isolation has been addressed.

References: [Playwright pytest fixtures](https://playwright.dev/python/docs/test-runners),
[browser context isolation](https://playwright.dev/python/docs/browser-contexts),
[clock control](https://playwright.dev/python/docs/clock), and
[authentication state](https://playwright.dev/python/docs/auth).

### 3. Shorten the CI critical path

Primary files: [CI workflow](../.github/workflows/ci-cd.yml),
[Justfile](../Justfile), and [Playwright configuration](../playwright.config.ts).

- Split Python UI tests and Node accessibility/mobile tests into independent CI
  jobs. Each runner gets its own server, database, and artifacts.
- Install Chromium through the locked Python Playwright CLI for Python UI tests.
- Install Chromium and WebKit through the locked Node Playwright CLI for the
  accessibility/device suite. Retain all four existing device projects; Firefox
  is not used by the current configuration.
- Add `just test-ui-python` and `just test-ui-a11y`. Keep `just test-ui` as the
  aggregate command, running both sequentially locally to avoid the current
  shared-port conflict.
- Update the pipeline summary dependencies and artifact references for the new
  jobs, and preserve required check coverage when changing job names.
- Cancel superseded runs for the same pull request using a PR-specific
  concurrency group. Preserve main-branch CI needed by the deployment gate.

Reference: [Playwright browser download recommendations](https://playwright.dev/docs/best-practices#optimize-browser-downloads-on-ci).

## Delivery and acceptance

Deliver three focused commits: unit fixture optimisation, browser execution
optimisation, then CI job changes and local command documentation.

After each change, compare repeated runs under equivalent conditions. Record
medians from at least three runs and distinguish warm/cold setup, test execution,
artifact generation, and runner queue time.

Preserve:

- The full CI unit suite and existing integration-test selection policy.
- The 90% total coverage threshold and 90% changed-line coverage threshold.
- All 112 current Python UI tests and 140 current accessibility/device cases.
- All four device projects and existing assertions.
- Impacted unit selection in the pre-push hook, without a separate smoke tier.
- Independent unit and browser commands.

Provisional performance targets, to validate rather than promise:

- Reduce local full-unit wall time by 25-40% from the 218.55-second baseline.
- Reduce overall CI execution below five minutes under comparable runner
  conditions.
- Avoid increased flakes, retries, or order dependence. Repeat both browser
  suites and verify representative authenticated and mutation-sensitive flows.

## Follow-up ideas

- Benchmark two unit-test workers after fixture changes, locally and on hosted
  Linux, including coverage collection. Adopt parallelism only if the complete
  suite improves after startup and resource costs are included.
- Consider browser sharding if accessibility/device execution remains the
  critical path. First isolate databases, ports, seed-ID files, and mutable data.
- Keep full device coverage while evaluating parallel execution; do not shorten
  CI by silently dropping projects or assertions.
- Consider browser caching or a prepared image only after measuring installation
  costs again. Playwright notes that cache restoration can cost as much as a
  download and does not cache Linux system dependencies; see its
  [CI guidance](https://playwright.dev/docs/ci#caching-browsers).
- Revisit broad dependency installation only if profiling shows it becoming
  significant. Python dependency installation currently takes only a few
  seconds, and quality/security jobs are already well below the critical path.

## Implementation notes (2026-11-24)

The fixture, browser reuse, authentication state, controlled clock, readiness
polling, and CI job split are implemented. The existing UI check now aggregates
both browser jobs so either failure still fails that check. Browser contexts stay
serial against each suite's shared seeded database.

Some Python UI tests still use `networkidle` where their dynamic interactions
have not yet been converted to explicit readiness checks. The accessibility
suite uses content-specific readiness, retaining `networkidle` for the dynamic
team-results view. These remaining waits are follow-up work.

An initial local run passed 714 unit tests (4 deselected) in 206.01 seconds,
and the Python UI run passed 110 tests (2 skipped) in 130.56 seconds. Other
processes ran concurrently, so neither is an isolated benchmark and neither
establishes a performance improvement. Hosted CI timings and repeated
comparable before/after medians remain to be measured.
