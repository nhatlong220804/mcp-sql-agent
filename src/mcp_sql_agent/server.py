"""MCP server exposing a read-only SQLite database plus a document retrieval layer.

Run it with the stdio transport so an MCP client can spawn it:

    MCP_SQL_DB=./demo.db python -m mcp_sql_agent.server

Tools are intentionally narrow. The model gets to look at the schema, run one bounded
SELECT, and search policy documents. It never gets write access, and it never sees
more than MAX_ROWS rows at a time.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from . import db, guard
from .rag import store

DEFAULT_DB = os.environ.get("MCP_SQL_DB", "./demo.db")
MAX_ROWS = int(os.environ.get("MCP_SQL_MAX_ROWS", "200"))

server = MCPServer(
    name="mcp-sql-agent",
    version="0.1.0",
    instructions=(
        "You are looking at a read-only SQLite database. Start with list_tables, then "
        "describe_table before writing any query. Only SELECT and WITH are accepted. "
        "Use search_documents for questions about policy or definitions rather than "
        "guessing from the schema."
    ),
)


def _db_path() -> Path:
    return Path(DEFAULT_DB).expanduser()


def _connect() -> sqlite3.Connection:
    return db.connect(_db_path())


@server.tool(
    description="List tables and views with their row counts. Start here.",
)
def list_tables() -> dict[str, Any]:
    try:
        with closing(_connect()) as conn:
            tables = db.list_tables(conn)
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    return {"database": str(_db_path()), "count": len(tables), "tables": tables}


@server.tool(
    description=(
        "Column names, types, primary keys, foreign keys and a few sample values for "
        "one table. Call this before writing a query."
    ),
)
def describe_table(table: str) -> dict[str, Any]:
    try:
        with closing(_connect()) as conn:
            return db.describe_table(conn, table)
    except (FileNotFoundError, ValueError) as exc:
        return {"error": str(exc)}


@server.tool(
    description=(
        "Run a single read-only SELECT or WITH statement. Results are capped, so add "
        "your own ORDER BY and aggregation. Writes are rejected before execution."
    ),
)
def query(sql: str, limit: int = MAX_ROWS) -> dict[str, Any]:
    limit = max(1, min(int(limit), MAX_ROWS))
    try:
        with closing(_connect()) as conn:
            return db.run_select(conn, sql, max_rows=limit)
    except guard.UnsafeQuery as exc:
        return {"error": f"rejected: {exc}", "sql": sql}
    except sqlite3.Error as exc:
        return {"error": f"sqlite: {exc}", "sql": sql}
    except FileNotFoundError as exc:
        return {"error": str(exc)}


@server.tool(
    description=(
        "Keyword search over indexed policy and definition documents. Returns the "
        "matching passages with their source, so answers can cite where they came from."
    ),
)
def search_documents(query_text: str, k: int = 5) -> dict[str, Any]:
    k = max(1, min(int(k), 20))
    try:
        with closing(_connect()) as conn:
            hits = store.search(conn, query_text, k=k)
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    return {
        "query": query_text,
        "count": len(hits),
        "results": [
            {
                "title": h.title,
                "doc_id": h.doc_id,
                "chunk": h.chunk_index,
                "score": round(h.score, 4),
                "text": h.text,
            }
            for h in hits
        ],
    }


@server.tool(
    description=(
        "List the documents in the retrieval index. Useful when a search returns "
        "nothing and you want to know what the knowledge base actually contains."
    ),
)
def list_documents() -> dict[str, Any]:
    try:
        with closing(_connect()) as conn:
            docs = store.list_documents(conn)
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    return {"count": len(docs), "documents": docs}


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
