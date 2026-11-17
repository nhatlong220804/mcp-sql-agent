# mcp-sql-agent

An MCP server that lets a language model look at a SQLite database and a set of policy
documents, without letting it break anything.

The model gets five tools: list the tables, describe one table, run a single bounded
SELECT, search the document index, and list what is in the index. It never gets write
access. If it tries, the statement is rejected before it reaches SQLite.

I built this because the hard part of putting an agent on a real database is not the
prompt. It is convincing yourself the agent cannot drop a table at 3am.

## Why two guards instead of one

Most examples of this pattern validate the SQL string and stop there. That is not
enough, because a regex is easy to fool.

So the statement is checked twice:

1. `guard.validate` rejects anything that is not a single `SELECT`/`WITH`, blocks a
   keyword list, refuses stacked statements, and attaches a `LIMIT`.
2. The SQLite connection itself is opened with `mode=ro`. Even if the first check
   missed something, the database file refuses the write.

The first guard is convenience. The second is the one that actually holds.

## Tools

| Tool | What it returns |
|---|---|
| `list_tables` | tables and views with row counts, excludes the internal `rag_*` tables |
| `describe_table` | columns, types, primary keys, foreign keys, index list, three sample values per column |
| `query` | columns plus rows, capped at 200, with the rewritten SQL echoed back so you can see the LIMIT that was applied |
| `search_documents` | top-k passages with title, document id, chunk number and score |
| `list_documents` | what is in the index, useful when a search returns nothing |

The rewritten SQL in the `query` response matters more than it looks. When the model
writes something wrong, you can see exactly what was executed rather than guessing.

## Retrieval

Documents are chunked into overlapping word windows, optionally cut at a sentence
boundary near the end of the window, then scored with TF-IDF over cosine similarity.

There is no embedding model and no API call. That is a deliberate tradeoff: the server
has to run on a laptop with no network and no key. For a few hundred paragraphs of
policy text, lexical matching is good enough to prove the pipeline works, and swapping
in a real embedding model later only means replacing `rag/embedder.py` while keeping
`search(query, k)`.

Chunks are stored in the same SQLite file as the business tables, in `rag_documents`
and `rag_chunks`. One file to copy, no second service.

## Chunking benchmark

`scripts/bench_retrieval.py` indexes the same eight documents at several chunk sizes
and scores them against 26 hand-labelled questions. Recall@5 is useless here (eight
documents, top five always contains the answer), so it reports recall@1, recall@3 and
MRR.

```
 chunk  overlap  chunks    R@1    R@3    MRR
   128        0      24   81%   96%  0.894
   128       32      31   73%   96%  0.843
   256        0      16   85%   96%  0.907
   256       64      16   81%   96%  0.886
   512        0       8   85%  100%  0.910
   512       64       8   85%  100%  0.910
   512      128       8   85%  100%  0.910
  1024       64       8   85%  100%  0.910
```

Two things stood out.

**Overlap makes it worse at small chunk sizes.** 128/0 beats 128/32 by eight points of
recall@1. With TF-IDF, overlapping text repeats terms across chunks, so the duplicated
chunk competes with the original and sometimes wins. The usual advice to always use
overlap assumes embeddings, where duplicated context is usually harmless. Here it is
not.

**Bigger is better up to a point.** Every configuration at 512 words or more lands at
the same 0.910, because each document fits in one or two chunks and chunking stops
doing anything. The gain from 256 to 512 is the gain from not splitting a policy section
in half.

None of this generalises. Eight documents is eight documents.

## Install and run

```
pip install -e .
python scripts/seed_demo.py --db demo.db --docs docs
```

That builds a four-table retail database (500 customers, 120 products, 3,000 orders,
7.6k line items) and writes eight policy documents into `docs/`.

Point an MCP client at it:

```json
{
  "mcpServers": {
    "retail-db": {
      "command": "python",
      "args": ["-m", "mcp_sql_agent.server"],
      "env": {
        "MCP_SQL_DB": "/absolute/path/to/demo.db",
        "MCP_SQL_MAX_ROWS": "200"
      }
    }
  }
}
```

Environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `MCP_SQL_DB` | `./demo.db` | SQLite file to expose |
| `MCP_SQL_MAX_ROWS` | `200` | hard cap on rows per query |

## Tests

```
python tests/test_guard.py
python tests/smoke_server.py
```

The guard tests cover twelve statements that must be rejected, including stacked
statements, `PRAGMA`, `ATTACH`, `SELECT INTO`, and a keyword hidden inside a string
literal. The smoke test runs every tool against the demo database and asserts that a
`DELETE` comes back rejected rather than executed.

## What this does not do

- **The guard is regex, not a parser.** It blanks comments and string literals before
  keyword matching, which stops the obvious tricks, but a real SQL parser is the correct
  answer. Do not point this at a database where a mistake costs money without replacing
  `guard.py` first.
- **TF-IDF is not semantic search.** Ask "what if my shoes fall apart" and it will not
  find "sole separation" unless the words happen to overlap. An embedding model fixes
  this and nothing else in the design has to change.
- **SQLite only.** The `mode=ro` trick does not map to PostgreSQL. There you would use a
  read-only role plus `statement_timeout`, and the connection layer needs rewriting.
- **No reranking.** Top-k by cosine, no cross-encoder pass. On eight documents that is
  fine; on eight thousand it would not be.
- **No multi-tenant isolation.** One file, one schema. There is no notion of which
  tables a given caller is allowed to see.
- **No query cost control.** `LIMIT` caps rows returned, not work done. A cross join on
  large tables will still run for as long as it wants.
- **The demo data is synthetic.** Names, prices and orders are generated. The documents
  are written to exercise retrieval, not copied from a real business.

## Layout

```
src/mcp_sql_agent/
  server.py        tool definitions and MCP wiring
  guard.py         read-only SQL validation
  db.py            connection, schema introspection, bounded execution
  rag/
    chunker.py     word windows with sentence-boundary cut
    embedder.py    TF-IDF index in numpy
    store.py       chunk storage and search
scripts/
  seed_demo.py     demo database and documents
  bench_retrieval.py
tests/
  test_guard.py
  smoke_server.py
```

MIT licensed.
