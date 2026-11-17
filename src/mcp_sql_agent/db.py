"""SQLite access. Read-only connection, schema introspection, bounded queries."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from . import guard

MAX_ROWS = 200
SAMPLE_VALUES = 3


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open the database read-only.

    mode=ro is the real guardrail here. Even if guard.validate missed something,
    SQLite itself refuses to write.
    """
    path = Path(db_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def list_tables(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT name, type
        FROM sqlite_master
        WHERE type IN ('table', 'view')
          AND name NOT LIKE 'sqlite_%'
          AND name NOT LIKE 'rag_%'
        ORDER BY name
        """
    ).fetchall()

    out = []
    for row in rows:
        name = row["name"]
        try:
            count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        except sqlite3.Error:
            count = None
        out.append({"name": name, "type": row["type"], "rows": count})
    return out


def describe_table(conn: sqlite3.Connection, table: str) -> dict[str, Any]:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name = ? AND type IN ('table','view')",
        (table,),
    ).fetchone()
    if not exists:
        raise ValueError(f"unknown table: {table}")

    columns = []
    for col in conn.execute(f'PRAGMA table_info("{table}")').fetchall():
        samples = []
        try:
            for r in conn.execute(
                f'SELECT DISTINCT "{col["name"]}" FROM "{table}" '
                f'WHERE "{col["name"]}" IS NOT NULL LIMIT {SAMPLE_VALUES}'
            ):
                samples.append(r[0])
        except sqlite3.Error:
            pass
        columns.append(
            {
                "name": col["name"],
                "type": col["type"] or "TEXT",
                "not_null": bool(col["notnull"]),
                "primary_key": bool(col["pk"]),
                "samples": samples,
            }
        )

    indexes = [
        {"name": r["name"], "unique": bool(r["unique"])}
        for r in conn.execute(f'PRAGMA index_list("{table}")').fetchall()
    ]

    foreign_keys = [
        {"from": r["from"], "to_table": r["table"], "to_column": r["to"]}
        for r in conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
    ]

    try:
        rows = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    except sqlite3.Error:
        rows = None

    return {
        "table": table,
        "rows": rows,
        "columns": columns,
        "indexes": indexes,
        "foreign_keys": foreign_keys,
    }


def run_select(conn: sqlite3.Connection, sql: str, max_rows: int = MAX_ROWS) -> dict[str, Any]:
    """Validate, execute and return rows. Raises guard.UnsafeQuery on writes."""
    safe_sql = guard.validate(sql, max_rows=max_rows)
    cursor = conn.execute(safe_sql)
    rows = cursor.fetchmany(max_rows)
    columns = [d[0] for d in cursor.description] if cursor.description else []
    return {
        "sql": safe_sql,
        "columns": columns,
        "rows": [dict(r) for r in rows],
        "row_count": len(rows),
        "truncated": len(rows) == max_rows,
    }
