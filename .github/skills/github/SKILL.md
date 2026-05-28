---
name: github
description: 'Interact with the GitHub repository matthieumarshall/website. Use when: creating, listing, reviewing, merging, or closing pull requests; creating, switching, listing, or deleting branches; checking PR status, review state, or comments; viewing open/merged PRs; managing draft PRs; fetching CI check results for a PR.'
argument-hint: 'Action and target, e.g. "list open PRs", "create PR from main to feature-x", "delete branch old-feature"'
user-invocable: true
---

# GitHub Skill

## Repository

- **Owner**: matthieumarshall
- **Repo**: website
- **URL**: https://github.com/matthieumarshall/website/

## When to Use

- "List all open / merged PRs"
- "Create a PR from branch X into main"
- "Review what's in PR #42"
- "Merge / close PR #42"
- "Create a branch called feature-foo from main"
- "List all branches"
- "Delete branch old-feature"
- "What checks are failing on this PR?"

## Tool

All operations use the **`gh` CLI** (GitHub CLI), which is authenticated via `gh auth login` or the `GH_TOKEN` environment variable.
Run commands in a terminal with `gh`.

---

## Procedures

### Pull Requests

#### List PRs
```powershell
# Open PRs (default)
gh pr list --repo matthieumarshall/website

# Include merged and closed
gh pr list --repo matthieumarshall/website --state all

# Filter by label or author
gh pr list --repo matthieumarshall/website --label bug --author "@me"
```

#### View a PR
```powershell
gh pr view <number> --repo matthieumarshall/website
```

#### Create a PR
```powershell
gh pr create --repo matthieumarshall/website \
  --base main \
  --head <branch> \
  --title "<title>" \
  --body "<description>"

# Create as draft
gh pr create --repo matthieumarshall/website --draft \
  --base main --head <branch> --title "<title>" --body "<description>"
```

#### Merge a PR
```powershell
# Merge commit (default)
gh pr merge <number> --repo matthieumarshall/website --merge

# Squash merge
gh pr merge <number> --repo matthieumarshall/website --squash

# Rebase merge
gh pr merge <number> --repo matthieumarshall/website --rebase
```

#### Close a PR (without merging)
```powershell
gh pr close <number> --repo matthieumarshall/website
```

#### Review / approve a PR
```powershell
gh pr review <number> --repo matthieumarshall/website --approve
gh pr review <number> --repo matthieumarshall/website --request-changes --body "<feedback>"
gh pr review <number> --repo matthieumarshall/website --comment --body "<comment>"
```

#### Check PR CI status
```powershell
gh pr checks <number> --repo matthieumarshall/website
```

---

### Branches

#### List branches
```powershell
# Remote branches
gh api repos/matthieumarshall/website/branches --jq '.[].name'

# Or with git (local + remote)
git branch -a
```

#### Create a branch
```powershell
# Create locally and push
git checkout -b <new-branch>
git push -u origin <new-branch>
```

#### Switch to a branch
```powershell
git checkout <branch>
# or
git switch <branch>
```

#### Delete a branch

```powershell
# Delete remote branch via gh
gh api -X DELETE repos/matthieumarshall/website/git/refs/heads/<branch>

# Delete local branch
git branch -d <branch>

# Force-delete local branch
git branch -D <branch>
```

#### Rename a branch
```powershell
git branch -m <old-name> <new-name>
git push origin --delete <old-name>
git push -u origin <new-name>
```

---

## Step-by-step: Typical PR Workflow

1. **Create feature branch**
   ```powershell
   git checkout -b feature/<name> main
   git push -u origin feature/<name>
   ```

2. **Make commits** (normal dev work)

3. **Open a PR**
   ```powershell
   gh pr create --repo matthieumarshall/website \
     --base main --head feature/<name> \
     --title "feat: <description>" \
     --body "Closes #<issue>"
   ```

4. **Check CI**
   ```powershell
   gh pr checks <number> --repo matthieumarshall/website --watch
   ```

5. **Merge when green**
   ```powershell
   gh pr merge <number> --repo matthieumarshall/website --squash --delete-branch
   ```

---

## Checking Auth

```powershell
gh auth status
```

If not authenticated:
```powershell
gh auth login
```
