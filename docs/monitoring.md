# Website health monitoring

The website exposes `/health` for automated checks and `/status` for current
availability and resource pressure. The status page is hosted by the website,
so it cannot report an outage when the website or VPS is unreachable.

Configure an independent HTTP monitor to check `https://oxfordshirexcleague.uk/health`
every 60 seconds with a five-second timeout and alert the operator after three
consecutive failed checks. Treat a connection failure, timeout, or non-200
response as a failed check. Recovery is a successful HTTP 200. The endpoint
returns 200 for degraded resource pressure; inspect the status page for details.

The status page shows current readings, not historical uptime. CPU and load are
sampled periodically, so a brief spike may be missed. The admin view shows exact
measurements, including database and write-ahead-log sizes. Disk capacity refers
to the filesystems used by the site; DuckDB does not have a separate fixed size
limit. Configure external monitoring and its notification destination separately.

`/health` remains public and returns coarse indicators only. Detailed figures on
`/status` and `/status/summary` require an administrator's existing signed-in
session; neither endpoint accepts a username or password in a URL or query.

Health requests are limited to 120 per minute per client and 3,600 per minute
across all clients. The two status routes share a separate budget of 120 per
minute per client and 1,800 per minute across all clients. When a budget is
exhausted, the server returns HTTP 429 with a `Retry-After` header in seconds;
clients should wait at least that long before retrying. The server uses fixed
one-minute windows, not exponential delays. The status page pauses automatic
refreshes until the retry period expires. Health and status have separate
budgets so status-page traffic cannot exhaust the health-check budget. A
monitor must treat persistent 429s as a failed check, as for other non-200s.

Limits are stored in process memory and reset on restart; with multiple workers
they apply independently to each worker. The documented production deployment
uses one worker. They use the client address supplied by the ASGI server, not a
client-provided forwarding header. Behind Cloudflare and nginx, verify that
trusted-proxy and nginx real-IP configuration resolve visitor addresses safely;
otherwise many visitors may share a proxy address and its per-client budget.
Trust forwarded addresses only from known proxies, never from arbitrary clients.

Deployment checks `/health` after starting the service. Automatic rollback
retains database migrations; an incompatible migration may require manual
recovery. When rolling back to a version without `/health`, the deployment
workflow falls back to the older root-page check only for HTTP 404.
