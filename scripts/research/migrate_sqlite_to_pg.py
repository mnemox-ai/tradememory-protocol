"""
One-time migration: SQLite (data/tradememory.db) → PostgreSQL.

Usage:
    python scripts/research/migrate_sqlite_to_pg.py
    python scripts/research/migrate_sqlite_to_pg.py --sqlite data/tradememory.db --pg postgresql://tradememory:tradememory@localhost:5432/tradememory

Prerequisites:
    1. docker-compose up -d  (PostgreSQL running)
    2. alembic upgrade head   (tables created)
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime

import psycopg2
from psycopg2.extras import execute_values

# Tables and their column definitions (order matters for FK constraints)
TABLES = [
    "trade_records",
    "session_state",
    "patterns",
    "strategy_adjustments",
    "episodic_memory",
    "semantic_memory",
    "procedural_memory",
    "affective_state",
    "prospective_memory",
]

# Columns that store JSON as TEXT in SQLite → need to be parsed to dict/list for JSONB
JSON_COLUMNS = {
    "trade_records": {"market_context", "trade_references", "tags"},
    "session_state": {"warm_memory", "active_positions", "risk_constraints"},
    "patterns": {"metrics"},
    "episodic_memory": {"context_json", "tags"},
    "affective_state": {"history_json"},
    "prospective_memory": {"source_episodic_ids", "source_semantic_ids"},
}

# Columns that store TEXT timestamps in SQLite → need to be parsed for TIMESTAMPTZ
TIMESTAMP_COLUMNS = {
    "trade_records": {"timestamp", "exit_timestamp"},
    "session_state": {"last_active"},
    "patterns": {"discovered_at"},
    "strategy_adjustments": {"created_at", "applied_at"},
    "episodic_memory": {"timestamp", "last_retrieved", "created_at"},
    "semantic_memory": {"last_confirmed", "last_contradicted", "created_at", "updated_at"},
    "procedural_memory": {"created_at", "updated_at"},
    "affective_state": {"last_updated"},
    "prospective_memory": {"expiry", "triggered_at", "created_at"},
}


def parse_json_value(val: str | None) -> dict | list | None:
    """Parse a JSON string from SQLite TEXT column."""
    if val is None:
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val  # return as-is if not valid JSON


def parse_timestamp(val: str | None) -> datetime | None:
    """Parse an ISO timestamp string from SQLite TEXT column."""
    if val is None or val == "":
        return None
    # Try common formats
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    # Last resort: return string as-is (psycopg2 might handle it)
    return val


def migrate_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn,
    table_name: str,
) -> int:
    """Migrate a single table from SQLite to PostgreSQL. Returns row count."""
    cursor = sqlite_conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name}")  # noqa: S608
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    if not rows:
        print(f"  {table_name}: 0 rows (empty)")
        return 0

    json_cols = JSON_COLUMNS.get(table_name, set())
    ts_cols = TIMESTAMP_COLUMNS.get(table_name, set())

    # Transform rows
    transformed = []
    for row in rows:
        new_row = []
        for col, val in zip(columns, row):
            if col in json_cols:
                val = parse_json_value(val)
                # psycopg2 needs json.dumps for JSONB
                val = json.dumps(val) if val is not None else None
            elif col in ts_cols:
                val = parse_timestamp(val)
            new_row.append(val)
        transformed.append(tuple(new_row))

    # Bulk insert with ON CONFLICT DO NOTHING (idempotent re-runs)
    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    pg_cursor = pg_conn.cursor()

    insert_sql = f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"  # noqa: S608
    for row in transformed:
        try:
            pg_cursor.execute(insert_sql, row)
        except Exception as e:
            print(f"  WARNING: Failed to insert row in {table_name}: {e}")
            pg_conn.rollback()
            continue

    pg_conn.commit()
    count = len(transformed)
    print(f"  {table_name}: {count} rows migrated")
    return count


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite → PostgreSQL")
    parser.add_argument(
        "--sqlite",
        default="data/tradememory.db",
        help="Path to SQLite database (default: data/tradememory.db)",
    )
    parser.add_argument(
        "--pg",
        default="postgresql://tradememory:tradememory@localhost:5432/tradememory",
        help="PostgreSQL connection string",
    )
    args = parser.parse_args()

    # Connect SQLite
    try:
        sqlite_conn = sqlite3.connect(args.sqlite)
        sqlite_conn.row_factory = None  # plain tuples
    except Exception as e:
        print(f"ERROR: Cannot open SQLite DB at {args.sqlite}: {e}")
        sys.exit(1)

    # Connect PostgreSQL
    try:
        pg_conn = psycopg2.connect(args.pg)
    except Exception as e:
        print(f"ERROR: Cannot connect to PostgreSQL: {e}")
        print("Make sure PostgreSQL is running (docker-compose up -d) and alembic upgrade head was run.")
        sys.exit(1)

    print(f"Migrating: {args.sqlite} → PostgreSQL")
    print("=" * 50)

    total = 0
    for table in TABLES:
        try:
            count = migrate_table(sqlite_conn, pg_conn, table)
            total += count
        except Exception as e:
            print(f"  ERROR migrating {table}: {e}")

    print("=" * 50)
    print(f"Total: {total} rows migrated across {len(TABLES)} tables")

    sqlite_conn.close()
    pg_conn.close()


if __name__ == "__main__":
    main()
