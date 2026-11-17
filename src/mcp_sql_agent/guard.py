"""Read-only SQL validation.

The whole point of this module is that the LLM never gets to write. It can propose
any statement it likes; everything that is not a plain read gets rejected before it
reaches the database.
"""

from __future__ import annotations

import re

# keywords that must never appear outside a string literal
FORBIDDEN = (
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "truncate",
    "replace",
    "attach",
    "detach",
    "pragma",
    "vacuum",
    "reindex",
    "grant",
    "revoke",
    "exec",
    "execute",
    "call",
    "load_extension",
)

STRING_LITERAL = re.compile(r"'(?:''|[^'])*'")
LINE_COMMENT = re.compile(r"--[^\n]*")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


class UnsafeQuery(ValueError):
    """Raised when a statement is not a read-only SELECT."""


def _strip_literals(sql: str) -> str:
    """Blank out comments and string literals so keyword checks can't be fooled."""
    out = BLOCK_COMMENT.sub(" ", sql)
    out = LINE_COMMENT.sub(" ", out)
    out = STRING_LITERAL.sub("''", out)
    return out


def normalise(sql: str) -> str:
    """Collapse whitespace and drop a single trailing semicolon."""
    text = sql.strip()
    while text.endswith(";"):
        text = text[:-1].rstrip()
    return re.sub(r"\s+", " ", text)


def validate(sql: str, max_rows: int = 200) -> str:
    """Return a safe statement with a LIMIT attached.

    Raises UnsafeQuery if the statement is not a read.
    """
    if not sql or not sql.strip():
        raise UnsafeQuery("empty statement")

    cleaned = normalise(sql)
    bare = _strip_literals(cleaned).lower()

    # exactly one statement allowed
    if ";" in bare:
        raise UnsafeQuery("only one statement per call")

    first = bare.split()[0] if bare.split() else ""
    if first not in ("select", "with"):
        raise UnsafeQuery(f"statement must start with SELECT or WITH, got {first!r}")

    for word in FORBIDDEN:
        if re.search(rf"\b{word}\b", bare):
            raise UnsafeQuery(f"{word.upper()} is not allowed")

    if re.search(r"\binto\b", bare):
        raise UnsafeQuery("SELECT INTO is not allowed")

    # cap the result set. an existing LIMIT is left alone but clamped
    match = re.search(r"\blimit\s+(\d+)\b", bare)
    if match:
        limit = int(match.group(1))
        if limit > max_rows:
            cleaned = re.sub(
                rf"\blimit\s+{limit}\b",
                f"LIMIT {max_rows}",
                cleaned,
                flags=re.I,
            )
    else:
        cleaned = f"{cleaned} LIMIT {max_rows}"

    return cleaned


def explain_rejection(sql: str, max_rows: int = 200) -> str | None:
    """Return the rejection reason, or None if the statement is fine."""
    try:
        validate(sql, max_rows=max_rows)
        return None
    except UnsafeQuery as exc:
        return str(exc)
