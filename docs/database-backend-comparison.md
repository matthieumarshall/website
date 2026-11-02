# DuckDB and SQLite WAL for the website

## Summary

SQLite in write-ahead logging (WAL) mode is a good candidate for the website's
long-term transactional database. It is embedded, has no separate database
server, and supports multiple local processes accessing the same database.
DuckDB remains a reasonable short-term choice: its current concurrency model
does not mean that only one request can use the database at a time.

This is an assessment, not a migration decision or a benchmark. The VPS is
documented as having 1 GB of RAM and 1 vCPU, and the application as running one
Uvicorn worker; see [hosting setup](setup.md). Actual production settings,
memory headroom, response times, and backup procedures should be checked before
making a change.

## Concurrency

In its normal embedded read-write mode, DuckDB allows one **process** to open
the database for writing. That process can perform concurrent reads and writes
using separate connections or cursors. Concurrent transactions updating the
same rows can conflict and may need to be retried. See the
[DuckDB concurrency documentation](https://duckdb.org/docs/1.5/connect/concurrency.html).

The website opens a shared DuckDB connection at startup and supplies a
separate cursor to each request. The results-sync background task also uses its
own cursor. Consequently, simultaneous HTMX requests are not inherently limited
to one database operation at a time. However, the embedded model makes
independent writable application workers and external maintenance processes
less straightforward.

SQLite WAL permits multiple local processes and readers to access the database.
Readers and a writer can normally proceed concurrently, but SQLite still allows
only one writer at a time. Long writes can therefore delay other writes, and
long-lived readers can delay WAL checkpointing. WAL requires processes to be on
the same host, not on separate machines sharing a network filesystem. See the
[SQLite WAL documentation](https://www.sqlite.org/wal.html).

## Comparison

| Concern | DuckDB | SQLite with WAL |
| --- | --- | --- |
| Memory and operations | Embedded; no separate server. Designed primarily for analytical workloads. | Embedded; no separate server. A natural fit for small transactional applications. |
| Concurrency | Multiple readers and writers within one writable process; conflicting updates can fail. | Multiple local processes and readers; one writer at a time. |
| Website queries | Supports the current application without migration. | Indexed lookups and small transactions suit the site's typical requests. |
| Analytics | Strong for scanning and analysing larger datasets. | Suitable for ordinary website queries; less focused on large analytical scans. |
| Migration | No database migration required. | Requires schema, data access, tests, and operational changes. |
| Backups | Use a consistent DuckDB-aware procedure and test restores. | Use the SQLite online backup API or another SQLite-supported consistent backup procedure and test restores. |

Neither option guarantees faster HTMX responses. End-to-end latency also depends
on Python and template processing, external services, query plans, and
contention. Memory and performance should be measured on representative data,
especially while results are being imported and standings recalculated.

## If migrating to SQLite

- Replace DuckDB-specific connection and exception handling, and adapt SQL
  migrations, including sequences and schema changes. Enable foreign-key
  enforcement on every SQLite connection.
- Configure and verify WAL, connection lifetimes, transaction boundaries, and a
  bounded busy timeout. Keep write transactions short and test concurrent
  readers and writers, particularly during results imports.
- Review inserts that select the newest matching row afterwards. Use
  `INSERT ... RETURNING` or another connection-specific mechanism so that a
  concurrent insert cannot be mistaken for the current one.
- Preserve and verify IDs, relationships, timestamps, payment and entry
  records, and future ID generation. Test row counts, foreign keys, payment
  webhooks, results, and restores using a protected production-like copy.
- Do not enable multiple application workers without also addressing the
  background results-sync loop, which currently starts in each application
  process.
- Plan a tested cutover and rollback, including a consistent backup of the
  source data.

## Immediate backup check

The [documented cron job](setup.md) copies the DuckDB database file while the
service may be running. A plain copy of the main file is not a reliable live
backup: committed changes can still be in the write-ahead log, and the copy
may not represent a consistent state. Verify the actual production backup
procedure and test restoring it regardless of whether the database changes.
For SQLite, use the [online backup API](https://www.sqlite.org/backup.html) or
another supported consistent method instead of copying only the main file
while it is active.

## Recommended next steps

1. Check actual VPS memory headroom and the production backup and restore
   procedure.
2. Measure representative page and HTMX response times, peak memory, and
   write contention, both when idle and during results synchronisation.
3. Prototype SQLite using a protected production-like copy and compare
   correctness, response times, import duration, and peak memory.
4. Migrate only if the prototype meets the site's needs; otherwise retain DuckDB
   and address measured bottlenecks.
