---
name: vps
description: 'Interact with the production VPS: deploy code, check service status, view logs, manage the database, and run maintenance tasks. Use when: deploying a new version, debugging a production issue, checking logs, restarting the service, or transferring files to/from the server.'
argument-hint: 'Describe what you want to do on the VPS (e.g. "deploy latest main", "check logs", "restart service")'
user-invocable: true
disable-model-invocation: false
---

# VPS Interaction Skill

## Server Details

| Property | Value |
|---|---|
| **Provider** | Fasthosts |
| **IP** | `217.174.244.229` |
| **User** | `manager` |
| **SSH alias** | `vps` (via `~/.ssh/config`) |
| **App directory** | `/home/manager/website` |
| **Data directory** | `/home/manager/website/data/` |
| **Backups directory** | `/home/manager/backups/` |
| **systemd service** | `oxcross` |
| **OS** | Ubuntu (Debian-based) |

## SSH Access

SSH key-based auth is configured. From Windows PowerShell:

```powershell
ssh vps          # connect using alias
ssh manager@217.174.244.229  # or directly
```

`~/.ssh/config` entry:
```
Host vps
    HostName 217.174.244.229
    User manager
    IdentityFile ~/.ssh/id_ed25519
```

## Common Tasks

### Deploy latest code

```bash
ssh vps
cd ~/website
git pull origin main
uv sync --no-dev
sudo systemctl restart oxcross
sudo systemctl status oxcross
```

### Check service status and logs

```bash
sudo systemctl status oxcross
sudo journalctl -u oxcross -n 50 --no-pager   # last 50 log lines
sudo journalctl -u oxcross -f                  # follow live logs
```

### Restart / reload the service

```bash
sudo systemctl restart oxcross   # full restart
sudo systemctl reload oxcross    # graceful reload (if supported)
```

### Apply database migrations

```bash
ssh vps
cd ~/website
uv run python scripts/_apply_migrations.py
```

### Copy database backup locally (run on Windows)

```powershell
scp vps:/home/manager/backups/app.duckdb.<date> .\data\
```

### Upload a file to the server (run on Windows)

```powershell
scp .\local-file.txt vps:/home/manager/website/
```

### Check nginx status

```bash
sudo systemctl status nginx
sudo nginx -t            # test config
sudo systemctl reload nginx
```

### View nginx access/error logs

```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Check disk / memory usage

```bash
df -h        # disk
free -h      # memory
```

## Environment

The app reads from `/home/manager/website/.env`. To edit:

```bash
sudo nano /home/manager/website/.env
sudo systemctl restart oxcross   # pick up new values
```

Key env vars: `SECRET_KEY`, `PRODUCTION=true`.

## Firewall (ufw)

```bash
sudo ufw status numbered    # current rules
```

Allowed: OpenSSH (rate-limited), 80/tcp, 443/tcp. All other inbound denied.

## Backups

A cron job runs nightly:
- **02:00** — copies `data/app.duckdb` to `/home/manager/backups/app.duckdb.<YYYY-MM-DD>`
- **03:00** — deletes backups older than 30 days

To list backups:
```bash
ls -lh ~/backups/
```
