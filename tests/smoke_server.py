"""End-to-end smoke test against the demo database.

    set MCP_SQL_DB=demo.db
    python tests/smoke_server.py

Calls the tool functions directly, which is what the MCP transport ends up doing.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("MCP_SQL_DB", str(ROOT / "demo.db"))

from mcp_sql_agent import server  # noqa: E402


def show(label: str, payload) -> None:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    print(f"\n### {label}\n{text[:700]}")


tables = server.list_tables()
show("list_tables", tables)
assert tables["count"] == 4, tables

schema = server.describe_table("orders")
show("describe_table(orders)", {k: schema[k] for k in ("table", "rows")})
assert schema["rows"] == 3000

q = server.query(
    "SELECT status, COUNT(*) AS n FROM orders GROUP BY status ORDER BY n DESC"
)
show("query: orders by status", q)
assert "rows" in q and len(q["rows"]) == 4

bad = server.query("DELETE FROM orders")
show("query: rejected write", bad)
assert "error" in bad and "rejected" in bad["error"]

bad2 = server.query("SELECT * FROM orders; DROP TABLE orders")
show("query: stacked statements", bad2)
assert "error" in bad2

docs = server.list_documents()
show("list_documents", {"count": docs["count"]})
assert docs["count"] == 8

hits = server.search_documents("how long do I have to return an item", k=3)
show("search_documents", {"count": hits["count"], "titles": [r["title"] for r in hits["results"]]})
assert hits["count"] > 0
assert hits["results"][0]["doc_id"] == "return-policy", hits["results"][0]

print("\nsmoke: all checks passed")
