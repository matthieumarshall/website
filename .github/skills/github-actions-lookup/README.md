# GitHub Actions Lookup Skill (Workspace)

A VS Code Copilot skill for investigating GitHub Actions workflow failures in the **login-page** repository.

## Quick Start

This skill is now part of the repository and will be available to all team members.

### Usage

**In VS Code Copilot Chat:**
```
/github-actions-lookup PR #18
```

Or:
```
/github-actions-lookup 23480036479
```

### Setup

Ensure you have `GITHUB_TOKEN` environment variable set:

```powershell
$env:GITHUB_TOKEN = "ghp_your_token"
```

## Features

- ✅ Look up any GitHub Actions run by PR number or run ID
- ✅ Get summary with status, branch, duration, trigger event
- ✅ View detailed job information and step-by-step execution
- ✅ Formatty error messages for quick troubleshooting
- ✅ Direct links to GitHub Actions pages

## Workspace-Specific

This skill is customized for:
- Repository: `matthieumarshall/login-page`
- Branches: `main`, `add_security_standards`
- Common workflows: CI Pipeline, Security Scans, UI Tests, Unit Tests

## For Team Members

This skill is tracked in `.github/skills/github-actions-lookup/` and will be available whenever you work in this repository.

---

**Last Updated**: 2026-03-24
