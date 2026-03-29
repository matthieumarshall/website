---
name: github-actions-lookup
description: 'Look up GitHub Actions run results for login-page CI/CD pipeline and collect failure details including logs, job outcomes, and diagnostics. Use when: investigating CI failures on main or add_security_standards branches, debugging workflow issues, checking latest PR build status, or collecting build logs for troubleshooting.'
argument-hint: 'PR number (e.g., #42) or GitHub Actions run ID'
user-invocable: true
disable-model-invocation: false
---

# GitHub Actions Run Lookup

## Purpose

Fetch GitHub Actions workflow run results for the **login-page** repository with full failure diagnostics. Returns both summary and detailed logs to help debug CI/CD failures quickly.

## Repository Context

- **Owner**: matthieumarshall
- **Repo**: login-page
- **Current Branch**: add_security_standards
- **Main Workflows**: CI Pipeline, Security & Compliance Scans, UI Tests, Unit Tests

## When to Use

- **CI failure investigation**: "Why did my PR checks fail?"
- **Workflow debugging**: "Show me the full logs from that failed run"
- **Status checking**: "What's the latest build status for this PR?"
- **Log collection**: Gather detailed error traces and job output
- **Build troubleshooting**: Understand which steps failed and why

## What It Returns

### Basic Summary
- Workflow name and status
- Run ID and attempt number
- Trigger event and branch
- Direct link to GitHub Actions page

### Detailed Logs (if available)
- Failed job names and conclusions
- Step-by-step output from failed jobs
- Full error messages and stack traces
- Job artifacts (if applicable)

## How to Use

### Option 1: Invoke Directly (Slash Command)
1. Type `/github-actions-lookup` in Copilot chat
2. Provide either:
   - **PR number**: `18` or `#18`
   - **Run ID**: `23480036479` (visible in GitHub Actions URL)
3. The skill fetches the latest run for that PR, or the specific run if ID provided

### Option 2: Auto-triggered in Relevant Contexts
The skill auto-loads when discussing:
- CI failures or build errors in this workspace
- GitHub Actions workflows
- GitHub check runs
- Pull request status
- Pipeline troubleshooting

## Procedure

1. **Identify the run**: Extract PR number or run ID from user input
2. **Fetch basic info**: Call GitHub API to get workflow run summary
3. **Get run details**: Retrieve job list and status for the run
4. **Collect logs**: For failed jobs, fetch full step logs
5. **Format report**: Compile summary + detailed logs in readable markdown

## Resources

- [Lookup script](./scripts/github-actions-lookup.js) — Fetches Actions data via GitHub GraphQL/REST API
- [Helper utilities](./scripts/utils.js) — JSON parsing, markdown formatting, error handling

## Example Prompts

- "Check the GitHub Actions for PR #18"
- "Why did the code quality checks fail on main?"
- "Show me the logs from run 23480036479"
- "What's the latest build status?"
- "Debug the security scan failure"

## Requirements

- **GitHub token**: Must be configured (`GITHUB_TOKEN` env var or VS Code GitHub extension)
- **Network access**: Requires connection to api.github.com
- **Repository context**: Works best when run from within this repository workspace

## Common Workflow Checks

The login-page CI pipeline includes:
- ✅ **Code Quality Checks**: Ruff formatting and linting
- ✅ **Security & Compliance Scans**: gitleaks, pip-audit, vulnerability scanning
- ✅ **UI Tests**: Playwright end-to-end tests
- ✅ **Unit Tests**: pytest with coverage
- ✅ **Publish Pipeline Summary**: Final validation step

## Troubleshooting

**"Ruff format check" failed**
- Run: `uv run ruff format .`
- Then commit and push

**"gitleaks - Scan for secrets" failed**
- Check the GitHub Actions page for flagged files
- Remove sensitive data or move to environment variables

**"Code Quality Checks" failed**
- Run: `uv run ruff check . --fix`

**"Security & Compliance Scans" failed**
- Run: `uv run pip-audit` to check dependencies
- Run: `just lint` to run full pre-commit checks
