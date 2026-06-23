# New Machine Setup Guide

Step-by-step instructions for getting a development environment up and running on a new computer.

---

## 1. Prerequisites

Install the following tools before cloning the repo:

| Tool | Install |
|---|---|
| **Git** | https://git-scm.com/downloads |
| **Python 3.10+** | https://www.python.org/downloads/ |
| **uv** (Python package manager) | `winget install astral-sh.uv` or https://docs.astral.sh/uv/getting-started/installation/ |
| **Node.js** (for Playwright / Quill) | https://nodejs.org/en/download (LTS) |
| **Just** (task runner) | `winget install casey.just` or https://github.com/casey/just#packages |

Verify installations:
```powershell
git --version
python --version
uv --version
node --version
just --version
```

---

## 2. Clone the Repository

```powershell
git clone https://github.com/matthieumarshall/website.git
cd website
```

The repo is public so no authentication is needed for cloning.

---

## 3. Install Dependencies

Run the sync command. This installs all Python and Node dependencies and sets up pre-commit hooks. It also creates a `.env` file from `.env.example` on first run.

```powershell
just sync
```

If `just` is not available yet, run the equivalent steps manually:
```powershell
uv sync --all-extras
npm install
uv run python -m pre_commit install
Copy-Item .env.example .env
```

---

## 4. Configure the `.env` File

Edit the `.env` file created in the previous step. For local development only `SECRET_KEY` is strictly required:

```
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
PRODUCTION=false
```

For Stripe and England Athletics API integration, fill in the corresponding keys. Leave them as placeholders if you don't need those features locally.

---

## 5. Set Up the Database

Apply all migrations to create the local DuckDB database:

```powershell
uv run python scripts/_apply_migrations.py
```

This creates `data/app.duckdb`. The `data/` directory is gitignored.

Optionally seed an admin user:

```powershell
just seed-user <username> <password> admin
```

---

## 6. Install Playwright Browsers (for UI tests)

```powershell
uv run playwright install
```

---

## 7. Start the Development Server

```powershell
just serve
```

The app will be available at http://localhost:8000.

---

## 8. Run Tests

```powershell
just test          # all tests
just test-unit     # unit tests only
just test-ui       # Playwright UI tests only
```

---

## 9. SSH to the Production VPS

### 9.1 Generate an SSH key pair (if you don't have one)

```powershell
ssh-keygen -t ed25519 -C "your-email@example.com"
# Accept the default path: C:\Users\<you>\.ssh\id_ed25519
```

### 9.2 Copy your public key to the server

The easiest method is to append your new public key to the server's `authorized_keys` from the **existing machine** that already has access:

```powershell
# On the existing machine — copy the new machine's public key to the server
$pubkey = Get-Content C:\Users\<new-user>\.ssh\id_ed25519.pub
ssh vps "echo '$pubkey' >> ~/.ssh/authorized_keys"
```

Alternatively, if you have password access to the server, use `ssh-copy-id` (Git Bash / WSL):

```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub manager@217.174.244.229
```

Or log in with a password and paste manually:
```bash
ssh manager@217.174.244.229   # password login
mkdir -p ~/.ssh && chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys    # paste your public key, save
chmod 600 ~/.ssh/authorized_keys
```

### 9.3 Configure the SSH alias

Create or edit `C:\Users\<you>\.ssh\config` and add:

```
Host vps
    HostName 217.174.244.229
    User manager
    IdentityFile ~/.ssh/id_ed25519
```

### 9.4 Verify access

```powershell
ssh vps
```

You should land in `/home/manager` on the server without being asked for a password.

---

## 10. Common VPS Tasks

```bash
# Deploy latest code
ssh vps
cd ~/website
git pull origin main
uv sync --no-dev
sudo systemctl restart oxcross
sudo systemctl status oxcross

# View live logs
sudo journalctl -u oxcross -f

# Apply database migrations
cd ~/website
uv run python scripts/_apply_migrations.py

# Check disk / memory
df -h
free -h
```

---

## 11. VS Code Extensions (recommended)

- **Python** (`ms-python.python`)
- **Ruff** (`charliermarsh.ruff`) — linting/formatting
- **Jinja** (`wholroyd.jinja`) — template syntax highlighting
- **DjLint** (`monosans.djlint`) — HTML/Jinja linting
- **Playwright Test for VS Code** (`ms-playwright.playwright`)

---

## Quick Reference

| Task | Command |
|---|---|
| Install deps | `just sync` |
| Start dev server | `just serve` |
| Lint | `just lint` |
| Run all tests | `just test` |
| Audit deps for CVEs | `just audit` |
| Connect to VPS | `ssh vps` |
