# OXL Website Constitution

> A living document defining the team's non-negotiable development standards for the FastAPI + HTMX web platform.

## Core Principles

### I. Test-Driven Quality

Unit and UI testing are not optional. All public functions and critical user journeys MUST have automated test coverage.

**Requirements:**
- **Coverage Target**: 85% unit test coverage (pytest)
- **Scope**: Every public function requires unit tests
- **UI Testing**: Critical journeys + representative HTMX component tests (Playwright)
- **Accessibility**: WCAG 2.1 AA verified via Playwright + automated axe checks
- **Definition of Done**: PR MUST include unit tests + UI tests (coverage report optional but appreciated)
- **Database Testing**: Use `:memory:` DuckDB for test isolation, no production DB access in CI

**Rationale**: Quality is built-in, not added later. Automated tests catch regressions and provide living documentation of expected behavior.

---

### II. Code Style & Type Safety

Consistency enables speed. Type hints prevent entire categories of bugs before code review.

**Naming Conventions:**
- Functions, variables, modules: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private module members: Prefix with `_` (Python convention)
- Class names: `PascalCase`

**Type Hints:**
- **MUST** appear on every function signature (return type + all parameters)
- Examples:
  ```python
  def get_user_by_id(user_id: int) -> User:
      """Fetch a user from the database."""
      return db.query(User).filter(User.id == user_id).first()

  def validate_email(email: str) -> bool:
      """Return True if email format is valid."""
      return "@" in email and "." in email
  ```

**Comments:**
- Write comments only for **complex logic, non-obvious design decisions, or business rules**
- Avoid repeating what the code says; explain **why**
- Bad: `x = x + 1  # add 1 to x` → Good: `attempts_remaining = attempts_remaining - 1  # enforce rate limit`
- Use docstrings on public functions (one-liner minimum; detail if complex)

**Rationale**: Type hints catch errors at development time. Selective comments keep code readable without noise.

---

### III. Security First

Security validation happens in layers: automated, human, and third-party audits.

**Automated Checks (CI/CD):**
- `bandit` scans Python code for common vulnerabilities
- All checks MUST pass before merge
- Configuration: `.bandit.yaml` (if custom rules needed)

**Manual Review:**
- All PRs require owner/maintainer approval
- Reviewers MUST verify:
  - No SQL injection (use parameterised queries only)
  - No hardcoded secrets or credentials
  - CSRF validation enabled on all state-changing endpoints
  - XSS prevention via Jinja2 autoescaping

**Production Security:**
- Third-party security audit required before first production deployment
- Ongoing: Annual audit or after major feature releases

**Technology Standards:**
- Passwords: Hashed via `bcrypt` (no plaintext storage)
- CSRF: Double-submit cookie pattern on all forms
- XSS: Jinja2 autoescape=true (default)
- Database: Parameterised queries only (FastAPI SQLAlchemy ORM enforces this)
- Headers: CSP, X-Frame-Options, X-Content-Type-Options set
- External Resources: No CDN; all assets self-hosted

**Rationale**: Layered security (automation + humans + experts) catches what single approaches miss.

---

### IV. Collaborative Development

Clear commit messages and code review discipline reduce friction and prevent misunderstandings.

**Commit Messages:**
- Format: `<verb> <what was done>`
- Verbs: add, fix, refactor, docs, test, chore, security, perf
- Examples:
  ```
  add user registration endpoint
  fix race condition in session cleanup
  refactor auth middleware to use dependency injection
  docs: update README with setup instructions
  test: add coverage for email validation
  security: implement CSRF token rotation
  perf: cache user permissions for 5 minutes
  ```
- One logical change per commit (no squashing related fixes into a single commit)

**Code Review Process:**
- Every PR requires:
  1. Owner/maintainer approval (at least 1)
  2. All automated checks passing (tests, linting, security)
- Approval flow: Reviewer approves → Author merges
- No self-approval except for documentation-only changes

**Dependency Management:**
- Add high-quality packages freely with clear rationale in PR description
- For production deps, prefer well-maintained libraries with active communities
- Lock file (`uv.lock`) MUST be committed alongside dependency changes

**Rationale**: Simple messages scale; code review prevents bad decisions from landing alone; trust + automation replaces micromanagement.

---

### V. Modular Design & Dependency Injection

Each module has a single responsibility. Testability is built-in via dependency injection.

**Requirements:**
- Functions and classes MUST have clear, narrow responsibilities
- Dependencies injected via FastAPI's `Depends()` mechanism (not global state)
- No module-level global variables (use environment variables for config)
- Modules MUST be independently testable without side effects

**Example:**
```python
# ✓ GOOD: Dependency injection
from fastapi import Depends
from src.db import get_db

async def get_user_by_id(user_id: int, db: Session = Depends(get_db)) -> User:
    return db.query(User).filter(User.id == user_id).first()

# ✗ BAD: Hidden global dependency
db = Session()  # global!
def get_user_by_id(user_id: int) -> User:
    return db.query(User).filter(User.id == user_id).first()
```

**Rationale**: Dependency injection makes functions testable and reduces coupling; SOLID design prevents architecture from collapsing as codebase grows.

---

## Technology Stack

Technology decisions are preserved from prior work. This section documents what's already in place and why.

**Backend:**
- FastAPI (async Python web framework, type hints built-in)
- DuckDB (analytical SQL, lightweight, in-process)
- SQLAlchemy ORM (type-safe database access)
- Pydantic (data validation, JSON serialization)

**Frontend:**
- Jinja2 templates (server-side rendering)
- HTMX (progressive enhancement, minimal JS)
- Minimal CSS (inline or scoped, no bloat)
- Islands architecture (independent interactive regions)
- WCAG 2.1 AA accessibility (testable, auditable)
- Mobile-first responsive design

**Configuration:**
- All config from environment variables (`.env`, not hardcoded)
- No magic globals; explicit dependency injection

**Testing:**
- Unit tests: pytest with fixtures
- UI tests: Playwright (cross-browser, headless)
- Database: `:memory:` DuckDB for test isolation

**Tools & CI:**
- Dependency management: `uv` (fast, lock-based)
- Linting: `ruff` (all Python code)
- Security scanning: `bandit` (pre-commit hook)
- YAML validation: `yamllint` (configs)
- Git hooks: Pre-commit framework (ruff, bandit, yamllint)

**Database Migrations:**
- All schema changes in `migrations/` directory
- Version control for every migration
- Never modify production without migration script
- Test migrations in CI before production run

**Rationale**: This stack is lean, type-safe, and accessibility-first. Each choice serves developer velocity and user experience.

---

## Development Workflow

### Local Development

1. Clone repo and create feature branch (auto-named by `speckit.git.feature`)
2. Set up: `uv venv && source .venv/bin/activate && uv pip install -r requirements.txt`
3. Configure: Copy `.env.example` to `.env`, fill in local values
4. Run tests: `pytest` (includes coverage report)
5. Run server: `python -m uvicorn src.main:app --reload`
6. Before commit: `pre-commit run --all-files` (auto-fixes what it can)

### Before Pushing a PR

- [ ] All tests pass (`pytest` + `pytest --cov`)
- [ ] UI tests pass (`playwright test`)
- [ ] Pre-commit hooks pass (`pre-commit run --all-files`)
- [ ] Coverage report shows ≥85% (or target for new code)
- [ ] No hardcoded secrets, credentials, or TODO comments
- [ ] Commit message follows the standard format (verb + what was done)

### PR Template Checklist

Every PR description MUST include:
- What problem does this solve?
- How was it tested?
- Any new dependencies added? (List + rationale)
- Breaking changes? (None expected for new features, required for API changes)

---

## Quality Gates & Definition of Done

### Unit Tests (pytest)

- **Coverage**: 85% minimum for overall repo; 100% for new/modified code blocks
- **Execution**: `pytest` (verbose output, fail fast on first error)
- **Fixtures**: Use `conftest.py` for reusable setup (db sessions, mock users, etc.)
- **Database**: Always use `:memory:` for test isolation
- **Example test**:
  ```python
  def test_get_user_returns_user_by_id(db_session: Session):
      user = create_test_user(db_session, id=1, name="Alice")
      result = get_user_by_id(user_id=1, db=db_session)
      assert result.id == 1
      assert result.name == "Alice"
  ```

### UI Tests (Playwright)

- **Scope**: Critical user journeys + representative HTMX interactions
- **Examples**: Login flow, form submission with HTMX response, error handling
- **Execution**: `playwright test` (headless)
- **Accessibility**: Include axe checks in critical pages
- **Example test**:
  ```typescript
  test('login successful redirects to dashboard', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[name="email"]', 'user@example.com');
    await page.fill('input[name="password"]', 'test-password');
    await page.click('button[type="submit"]');
    await page.waitForURL('/dashboard');
    expect(page.url()).toContain('/dashboard');
  });
  ```

### Code Style Checks (Ruff + Bandit)

- **Ruff**: Format + linting (fixes automatically with `ruff format`)
- **Bandit**: Security scan (must pass; no exceptions)
- **Run locally**: `ruff format src/ && ruff check src/ && bandit -r src/`
- **CI**: Pre-commit and GitHub Actions enforce these

### Definition of Done (Acceptance Criteria)

A feature is "done" when **all** of the following are true:

1. ✅ Code changes complete (feature works as spec'd)
2. ✅ Unit tests written + passing (≥85% coverage for new code)
3. ✅ UI tests written for critical journeys (Playwright)
4. ✅ Accessibility checks pass (WCAG 2.1 AA)
5. ✅ Code style checks pass (ruff, bandit)
6. ✅ PR approved by owner/maintainer
7. ✅ All CI checks green
8. ✅ Commit message follows standard format
9. ✅ No known bugs or edge cases left unaddressed

---

## Governance

### How This Constitution Works

- **Supersedes all other practices**: If this constitution conflicts with a wiki, Slack message, or verbal agreement, the constitution wins.
- **Applies to all code**: Backend (Python), frontend (HTML/JS/CSS), tests, docs, scripts.
- **Living document**: Reflects current team decisions; changes require explicit team vote + documented amendment.

### Amendment Process

1. **Proposal**: Identify what needs to change and why
2. **Discussion**: Team reviews; clarify trade-offs
3. **Vote**: Unanimous consent preferred; majority (50%+1) if needed
4. **Documentation**: Record amendment in this file
5. **Propagation**: Update dependent artifacts (templates, CI rules, etc.)
6. **Version bump**: Update version per semantic versioning rules

**Version Bumping Rules:**
- **PATCH** (1.0.0 → 1.0.1): Clarifications, wording fixes, non-semantic refinements
- **MINOR** (1.0.0 → 1.1.0): New principle added, existing principle expanded, new quality gate
- **MAJOR** (1.0.0 → 2.0.0): Backward-incompatible principle change or removal

### Compliance & Review

- **Code review**: Reviewers MUST verify PR compliance with this constitution
- **Questions during review?** Reference the section that applies (e.g., "See Section II: Code Style & Type Safety")
- **Exceptions**: None allowed without explicit amendment to this document
- **Audit**: Constitution compliance reviewed at sprint retro or quarterly

### Reference & Runtime Guidance

For day-to-day development questions not covered here, see:
- **Setup & tooling**: `README.md`
- **Architecture**: `docs/architecture.md`
- **Testing patterns**: `tests/README.md`
- **Deployment**: `docs/deployment.md`

---

**Version**: 1.0.0 | **Ratified**: 2025-01-08 | **Last Amended**: 2025-01-08
