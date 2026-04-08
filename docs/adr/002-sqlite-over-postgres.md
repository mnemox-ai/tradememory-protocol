# ADR 002: SQLite Over PostgreSQL

**Status:** Accepted  
**Date:** 2025-11-20  
**Authors:** Sean Peng  
**Supersedes:** None

## Context

TradeMemory requires persistent storage for multiple data types:

- Trade records (episodic memory)
- Semantic beliefs (Bayesian priors per strategy/regime)
- Procedural memory (running behavioral averages)
- Affective state (confidence, streaks, equity curve)
- Trading Decision Records (audit trail with SHA-256 hashes)

The storage layer must support the primary deployment model: a single AI agent running a local MCP server on the trader's machine.

We evaluated:

| Storage | Setup Cost | Concurrency | Portability | Performance (n < 100K) |
|---------|-----------|-------------|-------------|----------------------|
| **SQLite** | **Zero** | **Single-writer** | **File copy** | **Fastest (no network)** |
| PostgreSQL | Docker/service | Multi-writer | Server-dependent | Overhead from TCP |
| DuckDB | Pip install | Single-writer | File copy | Optimized for analytics |
| JSON files | Zero | None (corruption risk) | File copy | O(n) reads |

## Decision

SQLite as the primary and default storage engine. PostgreSQL exists as an optional upgrade path via `database.py` (SQLAlchemy-backed) for dashboard and multi-agent deployments.

### Rationale

**Zero-configuration install.** The entire setup is `pip install tradememory-protocol`. No Docker, no database server, no connection strings, no port conflicts. This is critical for adoption -- every additional setup step loses users. The MCP ecosystem expects tools that "just work."

**Perfect fit for the access pattern.** TradeMemory's primary use case is one agent, one database, on one machine. SQLite is purpose-built for this: embedded, serverless, zero-latency. There is no network hop between the MCP server and its data.

**File-based operations.** Backup is `cp tradememory.db tradememory.db.bak`. Migration testing is `cp prod.db test.db`. Distribution is attaching a `.db` file. This simplicity compounds -- every operational task that would require `pg_dump`/`pg_restore` is instead a file copy.

**Performance at our scale.** A retail trader generates maybe 500-2,000 trades per year. Even a high-frequency prop desk might generate 50K trades annually. At n < 100K rows, SQLite consistently outperforms PostgreSQL because there is no TCP overhead, no connection setup, no query planning for a remote server. Benchmarks show 2-5x faster reads for simple queries at this scale.

**WAL mode for read concurrency.** SQLite's Write-Ahead Logging mode allows concurrent reads while a write is in progress. This is sufficient for the dashboard polling trade data while the MCP server writes new entries.

## PostgreSQL Upgrade Path

The codebase maintains `database.py` alongside `db.py` specifically for scenarios where SQLite's limitations matter:

| Trigger | Why PostgreSQL |
|---------|---------------|
| Multi-agent concurrent writes | SQLite serializes all writes behind a single lock |
| n > 100K trades with complex analytical queries | PostgreSQL's query planner and indexing outperform at scale |
| Hosted multi-tenant SaaS deployment | Connection pooling, row-level security, replication |
| Real-time dashboard with WebSocket updates | `LISTEN`/`NOTIFY` for push-based updates |

Migration path: `db.py` and `database.py` share identical table schemas. A migration script reads from SQLite and bulk-inserts into PostgreSQL. No application code changes are needed beyond swapping the connection string.

## Consequences

### Positive

- Zero-friction install: `pip install` and go
- Portable: database travels with the project directory
- Testable: each test gets a fresh `:memory:` or temp-file database
- Fast: no network overhead for the primary use case
- Backup: `cp` instead of `pg_dump`

### Negative

- **Single-writer limitation.** Only one process can write at a time. If two MCP servers point at the same `.db` file, one will get `SQLITE_BUSY`. Mitigated by the single-agent deployment model and documented in setup guides.
- **No built-in connection pooling.** Not needed for single-agent use, but becomes a bottleneck under concurrent dashboard + sync + MCP access. WAL mode helps but does not fully solve this.
- **Foreign key enforcement is opt-in.** `PRAGMA foreign_keys = ON` must be set per connection. Missed in early development, now enforced in `db.py`'s connection factory.
- **No `LISTEN`/`NOTIFY`.** Dashboard must poll for updates rather than receiving push notifications. Acceptable at current scale; becomes inefficient with sub-second update requirements.

### Monitoring

If users report `SQLITE_BUSY` errors or dashboard latency exceeds 2 seconds, that is the signal to recommend the PostgreSQL upgrade path.
