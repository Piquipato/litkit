# Data and scoring contract

`import-legacy ROOT` reads `raw/_staging/consolidated-evidence.json` (`sources`, `quotes`, `excluded`) and `measurements.json` (`measurements`). Unknown keys are retained. Source keys, quotation IDs and measurement IDs are stable. Reimporting identical ledgers is idempotent; changed documents, conflicting records or distinct legacy sources sharing an identifier are rejected instead of silently overwritten. The SQLite transaction rolls back on error. Original JSON bytes are kept in `legacy_documents`; source attachments stay at their original paths, with recorded SHA-256/size. This is record preservation, not an attachment backup operation.

OpenAlex enrichments never replace curated title/year or legacy JSON. Provider response snapshots and metric provenance are additive. Peer review is tri-state and not inferred from article type, DOI, venue or indexing. Retraction uses the provider's explicit `is_retracted` signal. Cache identities exclude credentials and contact email; only sanitized response payloads and timestamps are stored. Network errors do not print request URLs or response bodies. Offline cache misses fail explicitly. Default retries and per-host delay are configured under `[http]`.

## Source quality

For each configured indicator, transform a finite nonnegative raw value to [0,1] (`identity01`, `linear_cap`, or `log_cap`). Missing/unusable values are null, not zero. Each available component receives effective weight `weight / sum(available weights)`. Coverage is `sum(available weights) / sum(all weights)`. No available values gives a null score. Explicit non-peer-reviewed sources multiply by the configured 0.5 default; explicit retraction is a hard zero even with no other indicators. The original pre-multiplier value and full trace are retained.

OpenAlex currently supplies FWCI and citation percentile quality inputs, plus citation count metadata. Other configured quality indicators remain missing until supplied explicitly; no fabricated venue metrics or citation-context counts are used.

## Quote quality

Quote evidence quality is separate from inherited source quality, never silently multiplied together. The trace keeps original class/depth/check observations as well as numeric transform inputs. Recognized explicit classes map through `quality.class_scores`. Explicit nonnegative `chain_depth` maps to `1/(1+depth)`. `quote_checks` with method `verbatim` and result `pass`/`fail` supplies the verification component; a legacy `check: p1` is not such a verification. Structured legacy `uncertainty_type`, `condition_match_score`, and `independent_replications` may supply the corresponding components. No extraction from ambiguous prose or automatic replication inference is performed. The replication component is linearly capped at the configured count.

Scores append to SQLite with timestamps and rule versions; complete calculation traces are in `components_json`. `quality.json` provides the latest explicit run output. Values and scores are provisional and do not authorize experimental priors.

## Graph/ranking

Directed edges mean citing → cited, deduplicated for graph computation. Louvain uses an undirected projection, fixed configurable seed and resolution. Isolated works get singleton communities; empty graphs are valid. Frontier features are observed corpus citation count, known references to the corpus, shared known references (coupling), optional title keyword fraction, and source quality. Missing outgoing reference lists, keyword lists or quality remain null. Graph-derived counts describe only the observed, capped graph and must not be mistaken for complete bibliographic measurements. Ranking weights/caps and quality weights are separately configurable in TOML.

## Outputs

- `litkit.db`: canonical records, identifiers, snapshots and traces.
- `exports/project.json`: all tables; `exports/TABLE.jsonl`: individual tables.
- `exports/quality.json`: separate source and quote traces.
- `exports/rank.json`: complete frontier, independent of terminal `--limit`.
- `graph/citations.graphml`, `graph/citations.html`, optionally `graph/citations.png`.

The local HTML contains no CDN, JavaScript dependency or external network request. Labels are HTML escaped. Exporting does not generate Markdown synthesis. Export files are snapshots, not an automatic import/restore format; retain the SQLite database and original attachments for backups.
