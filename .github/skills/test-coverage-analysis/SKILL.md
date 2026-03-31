---
name: test-coverage-analysis
description: "Run pytest unit tests with coverage analysis and identify gaps. Use when: checking test coverage, finding untested code, planning what to test next, evaluating test quality, improving unit test coverage."
argument-hint: "Optional: specific module or function to focus on (e.g. 'main.py' or 'repository functions')"
---

# Test Coverage Analysis

Run unit tests, parse coverage data, and produce a clear gap report showing which modules, functions, and lines lack test coverage.

## When to Use

- Before writing new tests, to know where gaps are
- After adding features, to verify new code is tested
- When asked to "improve coverage" or "check what needs tests"
- During code review to assess test completeness

## Procedure

### 1. Run Unit Tests with Coverage

Run the unit test suite and generate coverage reports:

```sh
uv run pytest tests/unit/ --tb=short -q
```

This produces three outputs configured in `pytest.ini`:
- Terminal summary with missing lines (`--cov-report=term-missing`)
- HTML report in `htmlcov/` (`--cov-report=html`)
- JSON report in `coverage.json` (`--cov-report=json`)

Coverage scope and exclusions are configured in `.coveragerc`:
- **Source**: `src/website/`
- **Omitted files**: `seed_user.py` (CLI script), venv/site-packages/tests directories
- **Excluded lines**: `pragma: no cover`, `__repr__`, `TYPE_CHECKING`, abstract/property decorators, `if __name__` guards

Files and lines that `.coveragerc` omits or excludes will **not appear** in `coverage.json` — do not report on them.

**If tests fail**: fix failing tests first before analysing coverage. Report failures to the user.

### 2. Parse Coverage JSON

Read and parse `coverage.json` in the workspace root. This file has the structure:

```
{
  "files": {
    "src\\website\\<module>.py": {
      "summary": { "percent_covered_display": "82", "num_statements": N, "missing_lines": M },
      "missing_lines": [line_numbers...],
      "functions": {
        "<function_name>": {
          "summary": { "percent_covered_display": "0", "num_statements": N },
          "missing_lines": [line_numbers...]
        }
      }
    }
  },
  "totals": { "percent_covered_display": "82", "num_statements": N, "missing_lines": M }
}
```

Only report on files that appear in this JSON. Anything absent has been excluded by `.coveragerc` and should be ignored.

### 3. Build the Gap Report

For each source file in the JSON, extract:

| Data Point | Source |
|---|---|
| File-level coverage % | `files.<path>.summary.percent_covered_display` |
| Total statements | `files.<path>.summary.num_statements` |
| Missing line count | `files.<path>.summary.missing_lines` |
| Missing line numbers | `files.<path>.missing_lines` |
| Per-function coverage | `files.<path>.functions.<name>.summary` |
| Uncovered functions | Functions where `percent_covered_display` is `"0"` |

Sort files by **number of missing statements** descending (not by percentage — a file with 100 missing lines at 74% matters more than one with 2 missing lines at 50%).

Skip files at 100% coverage — they don't need attention.

### 4. Produce the Summary

Present results in this format:

**Overall**: X% (Y of Z statements covered)

**Files ranked by uncovered statements** (skip 100% files):

| File | Coverage | Statements | Missing | Priority |
|---|---|---|---|---|
| main.py | 74% | 437 | 112 | HIGH |
| repository.py | 91% | 138 | 13 | MEDIUM |
| ... | ... | ... | ... | ... |

Priority thresholds: HIGH = 50+ missing, MEDIUM = 10–49 missing, LOW = 1–9 missing.

**Uncovered functions** (0% coverage):

List each fully uncovered function with its file and line range.

**Partially covered functions** (1–89% coverage):

List functions with their missing line numbers so the user can see exactly which branches/paths are untested.

### 5. Focused Analysis (Optional)

If the user specified a module or function:

1. Read the source file at the missing line numbers
2. Describe briefly _what_ those lines do (error path, auth guard, branch, etc.)
3. Do not write tests — just report what is untested and why

## Project-Specific Notes

- Test runner: `uv run pytest tests/unit/ --tb=short -q`
- Coverage config: [.coveragerc](./../../../.coveragerc) (source = `src/website`, omits `seed_user.py`)
- pytest config: `pytest.ini` (addopts includes `--cov=src/website --cov-report=json`)
- Tests use in-memory DuckDB (`:memory:`) — see `tests/unit/conftest.py`
- Existing test files: `test_auth.py`, `test_database.py`, `test_export.py`, `test_main.py`, `test_models.py`, `test_repository.py`, `test_results.py`
