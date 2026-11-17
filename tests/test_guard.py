"""Guard tests. Run with: python -m pytest tests/ -q  (or python tests/test_guard.py)"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_sql_agent import guard  # noqa: E402

ALLOWED = [
    "SELECT * FROM customers",
    "select customer_id from customers where tier = 'gold'",
    "WITH totals AS (SELECT customer_id, COUNT(*) c FROM orders GROUP BY customer_id) "
    "SELECT * FROM totals ORDER BY c DESC",
    "SELECT * FROM orders WHERE status = 'cancelled'",
    "SELECT * FROM customers -- trailing comment",
]

REJECTED = [
    "DROP TABLE customers",
    "DELETE FROM orders",
    "UPDATE customers SET tier = 'gold'",
    "INSERT INTO customers VALUES (1,'x','y','z','gold','2025-01-01')",
    "CREATE TABLE x (a int)",
    "PRAGMA table_info(customers)",
    "ATTACH DATABASE 'other.db' AS other",
    "SELECT * FROM customers; DROP TABLE customers",
    "select * from customers where 1=1; delete from orders",
    "SELECT * INTO backup FROM customers",
    "",
    "   ",
]


def test_allowed() -> None:
    for sql in ALLOWED:
        result = guard.validate(sql)
        assert result.lower().startswith(("select", "with")), result
        assert "limit" in result.lower(), f"no limit added: {result}"


def test_rejected() -> None:
    for sql in REJECTED:
        try:
            guard.validate(sql)
        except guard.UnsafeQuery:
            continue
        raise AssertionError(f"should have been rejected: {sql!r}")


def test_keyword_inside_literal_is_fine() -> None:
    sql = "SELECT * FROM orders WHERE status = 'delete'"
    assert guard.validate(sql)


def test_limit_is_clamped() -> None:
    out = guard.validate("SELECT * FROM orders LIMIT 9999", max_rows=50)
    assert "limit 50" in out.lower(), out


def test_limit_is_added_when_missing() -> None:
    out = guard.validate("SELECT * FROM orders", max_rows=75)
    assert out.lower().endswith("limit 75"), out


def test_trailing_semicolon_removed() -> None:
    out = guard.validate("SELECT 1;")
    assert ";" not in out, out


if __name__ == "__main__":
    test_allowed()
    test_rejected()
    test_keyword_inside_literal_is_fine()
    test_limit_is_clamped()
    test_limit_is_added_when_missing()
    test_trailing_semicolon_removed()
    print("guard: all checks passed")
