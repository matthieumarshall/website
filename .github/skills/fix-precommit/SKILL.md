# Skill: Fix Pre-commit Hook Failures

## Purpose
Run all pre-commit hooks against the full codebase, diagnose every failure, and apply the correct fix. The skill ends when `pre-commit run --all-files` exits with code 0.

## When to use
- Before committing after adding new files or dependencies
- After updating `.pre-commit-config.yaml`
- When a `git commit` is rejected by a pre-commit hook

## Step-by-step workflow

### 1. Run hooks and capture output
```
uv run pre-commit run --all-files 2>&1
```
Read the **full** output before touching any file.

### 2. Categorise each failure

| Hook | Failure type | Fix strategy |
|------|-------------|--------------|
| `trailing-whitespace` / `end-of-file-fixer` | Auto-fixed by hook | Nothing — re-stage the modified files, then re-run |
| `check-merge-conflict` | Leftover conflict markers | Edit the flagged files and remove `<<<<<<<` / `=======` / `>>>>>>>` blocks |
| `check-added-large-files` | File too big | Remove the file from the commit; add to `.gitignore` if appropriate |
| `no-commit-to-branch` | Direct commit to a protected branch | Work on a feature branch instead |
| `ruff` | Lint errors | `uv run ruff check --fix .` then `uv run ruff format .` |
| `ruff-format` | Formatting issues | `uv run ruff format .` |
| `bandit` | SAST finding | Understand the finding. If it's a real issue, fix the code. If it's a confirmed false positive, add `# nosec B<code>  # reason` on the flagged line. **Never suppress without a written reason.** |
| `bandit` — `unrecognized arguments` error | Hook passes filenames but args include `-r <dir>` | Add `pass_filenames: false` to the bandit hook in `.pre-commit-config.yaml` |
| `ty` | Type error | Fix the type issue. If it's a known limitation of the type checker against a third-party signature, add `# type: ignore[<code>]` with a comment explaining why |
| `html-validate` | Invalid HTML | Fix the template; common causes: unclosed tags, missing `alt` attributes, invalid nesting |

### 3. Apply fixes
- Auto-fixes (whitespace, formatting): re-stage only — the hook already wrote them.
- Code fixes: edit the file, then re-run hooks to confirm.
- Config fixes (`pass_filenames`, skip args): edit `.pre-commit-config.yaml`.

### 4. Re-run to verify
```
uv run pre-commit run --all-files 2>&1
```
Every hook must show `Passed`. If a hook shows `Failed` after your fix, read the new error — don't repeat the same fix.

### 5. Completion check
- [ ] Exit code is 0
- [ ] No hook shows `Failed`
- [ ] No `# nosec` added without an explanation comment
- [ ] No `# type: ignore` added without an explanation comment
- [ ] Unit tests still pass: `uv run pytest tests/unit/ --tb=short`

## Common `bandit` findings in this codebase

| Code | Description | Typical fix |
|------|-------------|-------------|
| B101 | Use of `assert` | Already skipped (`--skip B101`) — safe in this project |
| B105 | Hardcoded password string | Rename the variable so it doesn't look like a credential, or add `# nosec B105` with justification if it's a fallback token for dev only |
| B311 | `random` for security | Switch to `secrets` module |
| B608 | SQL injection risk | Use parameterised queries |

## Notes
- The `bandit` hook must always have `pass_filenames: false` when `args` includes an explicit `-r <directory>` to avoid conflicting arguments.
- The `ty` type checker may flag `add_middleware` calls with custom `BaseHTTPMiddleware` subclasses — `# type: ignore[arg-type]` is the accepted pattern in this project (see `main.py`).
