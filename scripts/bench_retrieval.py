"""Chunking sweep.

Indexes the same eight documents at several chunk sizes and measures retrieval against
a hand-labelled query set. Run it after seeding:

    python scripts/bench_retrieval.py --db demo.db

With only eight documents, recall@5 is always 100 percent and tells you nothing. So
this reports recall@1 and MRR instead, which do move when the chunking changes.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_sql_agent.rag import store  # noqa: E402

# question -> the document a human would say answers it
QUERIES: list[tuple[str, str]] = [
    ("how long do I have to return an item", "return-policy"),
    ("is clearance final sale", "return-policy"),
    ("do I pay a fee when I return something", "return-policy"),
    ("what happens if the soles are scuffed", "return-policy"),
    ("same day delivery cutoff time", "shipping-sla"),
    ("how much is express shipping", "shipping-sla"),
    ("free shipping threshold", "shipping-sla"),
    ("what happens after two failed delivery attempts", "shipping-sla"),
    ("can I stack two discount codes", "discount-rules"),
    ("does my gold discount combine with a promo", "discount-rules"),
    ("do loyalty points pay for shipping", "discount-rules"),
    ("how much do I need to spend to reach gold", "customer-tiers"),
    ("how is tier recalculated and when", "customer-tiers"),
    ("are wholesale accounts in the tier programme", "customer-tiers"),
    ("what is net revenue versus gross revenue", "data-dictionary"),
    ("do cancelled orders count in revenue", "data-dictionary"),
    ("how is average order value calculated", "data-dictionary"),
    ("warranty period for shoes", "warranty"),
    ("does warranty cover water damage on leather", "warranty"),
    ("who pays for repair after accidental damage", "warranty"),
    ("payment terms for wholesale accounts", "b2b-payment-terms"),
    ("when does an overdue account get frozen", "b2b-payment-terms"),
    ("does price protection apply to wholesale", "b2b-payment-terms"),
    ("when does a complaint go to a team lead", "complaint-escalation"),
    ("who can approve a large refund", "complaint-escalation"),
    ("what happens with privacy complaints", "complaint-escalation"),
]

CONFIGS = [
    (128, 0),
    (128, 32),
    (256, 0),
    (256, 64),
    (512, 0),
    (512, 64),
    (512, 128),
    (1024, 64),
]


def reset_index(conn: sqlite3.Connection) -> None:
    store.ensure_schema(conn)
    conn.execute("DELETE FROM rag_chunks")
    conn.execute("DELETE FROM rag_documents")
    conn.commit()


def index(conn: sqlite3.Connection, docs: dict[str, str], size: int, overlap: int) -> int:
    reset_index(conn)
    for doc_id, text in docs.items():
        title = text.splitlines()[0].lstrip("# ").strip() or doc_id
        store.add_document(
            conn,
            doc_id,
            title,
            text,
            chunk_size=size,
            overlap=overlap,
        )
    return conn.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0]


def evaluate(conn: sqlite3.Connection) -> tuple[float, float, float]:
    recall1 = 0
    recall3 = 0
    reciprocal = 0.0
    for question, expected in QUERIES:
        results = store.search(conn, question, k=5)
        ranks = [i + 1 for i, r in enumerate(results) if r.doc_id == expected]
        if ranks:
            rank = ranks[0]
            reciprocal += 1.0 / rank
            if rank == 1:
                recall1 += 1
            if rank <= 3:
                recall3 += 1
    n = len(QUERIES)
    return recall1 / n, recall3 / n, reciprocal / n


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="demo.db")
    parser.add_argument("--docs", default="docs")
    args = parser.parse_args()

    docs_dir = Path(args.docs)
    docs = {p.stem: p.read_text(encoding="utf-8") for p in sorted(docs_dir.glob("*.md"))}
    if not docs:
        raise SystemExit(f"no documents in {docs_dir}, run seed_demo.py first")

    conn = sqlite3.connect(Path(args.db))
    print(f"{len(docs)} documents, {len(QUERIES)} labelled queries\n")
    print(f"{'chunk':>6} {'overlap':>8} {'chunks':>7} {'R@1':>6} {'R@3':>6} {'MRR':>6}")
    print("-" * 44)

    rows = []
    for size, overlap in CONFIGS:
        n_chunks = index(conn, docs, size, overlap)
        r1, r3, mrr = evaluate(conn)
        rows.append((size, overlap, n_chunks, r1, r3, mrr))
        print(f"{size:>6} {overlap:>8} {n_chunks:>7} {r1:>5.0%} {r3:>5.0%} {mrr:>6.3f}")

    # leave the index at the default configuration
    index(conn, docs, 512, 64)
    conn.close()

    best = max(rows, key=lambda r: (r[5], -r[0]))
    print(f"\nbest MRR: {best[5]:.3f} at size={best[0]} overlap={best[1]} ({best[2]} chunks)")


if __name__ == "__main__":
    main()
