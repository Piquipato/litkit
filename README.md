# litkit

A general-purpose Click CLI for literature evidence projects. SQLite is the source of truth; TOML controls provisional scoring and budgets. Exports are JSON/JSONL, **not generated Markdown synthesis**. No LLM is called.

Requires Python 3.11+. Install with `python -m pip install -e '.[test,plot]'` (plot is optional). Run `python -m litkit --help` or `litkit --help`.

```sh
litkit init /path/to/search --name my-review
litkit --project /path/to/search import-legacy /path/to/legacy
litkit --project /path/to/search status
litkit --project /path/to/search --max-calls 10 enrich --limit 10
litkit --project /path/to/search --offline enrich source-key
litkit --project /path/to/search --max-calls 5 snowball source-key --max-new 100 --max-citing 20
litkit --project /path/to/search graph --png
litkit --project /path/to/search quality
litkit --project /path/to/search rank --limit 20
litkit --project /path/to/search export
```

Global options precede the subcommand. `--max-calls` counts HTTP attempts, including retries, across one invocation; cache hits do not spend the budget. `--offline` never makes HTTP requests and allows stale cache entries. Provider errors return JSON summaries and nonzero exit status; successful items remain stored.

Projects are found through `--project`, `LITKIT_PROJECT`, or ancestor `litkit.toml`. Secrets use `%APPDATA%/litkit/secrets.toml` on Windows or `~/.config/litkit/secrets.toml` elsewhere, with `openalex_api_key` and optional `contact_email`. Environment overrides are `LITKIT_OPENALEX_API_KEY` and `LITKIT_CONTACT_EMAIL`. Do not put credentials in project TOML or commit caches/databases.

## Implemented

- Transactional, repeatable import of consolidated legacy sources, quotations, measurements, exclusions. Unknown fields remain in `legacy_json`; original ledger bytes and SHA-256 hashes remain in SQLite. File records reference existing files and record hashes; import does not duplicate PDFs.
- OpenAlex DOI/ID enrichment, bounded reference/citation expansion, TTL cache, offline replay, redacted payload cache and sanitized network diagnostics.
- Seeded Louvain communities over an undirected projection, directed GraphML, standalone SVG-in-HTML graph, optional PNG.
- Explainable candidate ranking and separate source/quote quality with raw values, transforms, original/effective weights, coverage and provisional flags. Missing metrics stay null and available weights renormalize. Retraction vetoes source/rank scores. Only explicitly false peer review receives the 0.5 penalty; venue does not imply peer review.
- Full SQLite table JSON/JSONL exports, including original ledger bytes encoded as base64. Export JSON columns are decoded to native JSON values.

## Limits and interpretation

This is a bounded P1/P2 implementation, not full acquisition. Only OpenAlex is implemented. Semantic Scholar, Crossref, COCI, Unpaywall, Europe PMC, arXiv, SJR ingestion, citation contexts, disruption/novelty metrics, full-text/PDF downloading and automatic quote verification remain unimplemented. Existing config placeholders for these are not provider support. No PDF extraction, OCR or LLM synthesis occurs.

Reference expansion creates ID-only candidates; enrich their IDs explicitly for metadata. Caps intentionally truncate exploration, so graph absence is not proof of no citation. Candidate outgoing-citation and coupling components remain missing until a provider reference list is available. Observed incoming-corpus counts are lower bounds, not complete global counts. HTML/PNG show at most `graph.html_max_nodes`; GraphML retains the full graph.

Quote class is imported from explicit legacy provenance. Free-text uncertainty, page-check labels, chain prose and numerical agreement do **not** automatically establish uncertainty type, verbatim verification, chain depth, matching conditions or independent replication. Those components remain missing unless explicit structured evidence/checks exist. Quality is a provisional prioritization aid, not a validity verdict or statistical confidence interval.

See [data and scoring](docs/data-and-scoring.md). Test offline with `python -m pytest`.
