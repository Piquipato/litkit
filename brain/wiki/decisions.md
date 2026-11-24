---
file: brain/wiki/decisions.md
produced_by_model: gpt-6-astra
produced_by_agent: brain-bootstrap
created: 2026-11-24T15:21:15+01:00
last_updated: 2026-11-24T15:21:15+01:00
---

# Approved decisions — round 1

Authority: saved round-1 answers at 14:49:19 on 2026-11-24, plus the current delegation. Free-text notes override conflicting option labels. Original nanovalve form is untouched; the public archival HTML preserves both response snapshots with personal email redacted. This is the authoritative distilled decision record, not a second answer store.

| ID | Approved direction |
|---|---|
| D0 | Click CLI, importable library, humans and agents supported. |
| D1 | All work/venue indicators plus explicit documented weighted composite. |
| D1a | Fixed documented transforms to [0,1]; percentile unchanged, count log transforms with caps, FWCI min(FWCI/2,1), flags 0/1. |
| D1b | Drop missing terms, renormalize available weights, retain coverage; flag coverage <0.5. |
| D1c | Retraction veto gives composite zero; non-peer-reviewed multiplier 0.5, separately visible. |
| D1d | Quotes inherit source score unchanged AND separate quote-evidence score; every input and derived value traceable. |
| D1e | PROVISIONAL: build with proposed weights; revisit after seeing corpus metrics. Not final approval of weights. |
| D2 | OpenAlex, Semantic Scholar, OpenCitations, Crossref, Unpaywall, Europe PMC/PMC and arXiv. |
| D3 | OpenAlex venue metrics + SJR CSV; provide a user-runnable CSV fetch/update script, not merely manual instructions. Respect access restrictions. |
| D4 | CD/disruption on demand, corpus only, capped at 200 citers; recency/growth available. General structured literature exploration, not physical-constants-only. |
| D5 | Verbatim/visual checks, evidence class, chain, uncertainty, condition match, replication, citation contexts, source/venue indicators. Judgment details remain open. |
| D6 | Depth-1 refs AND citers with caps; Louvain communities and explainable ranked frontier. |
| D7 | SQLite truth, DB/cache ignored, reviewable JSON/JSONL exports. Publishing full data needs privacy/copyright review (round 2). |
| D8 | Standalone public Piquipato/litkit; src/, tests/, docs/, README; conda-forge and cross-platform environment. New brain, Hindsight bank and main Obsidian link. |
| D9 | Text TOML/YAML configuration; deterministic core, optional off-default LLM quote proposals always rechecked verbatim. |
| D10 | GraphML, offline HTML and PNG, selectable. A future GUI is a discussion, not approved implementation. |
| D11 | SQLite is authoritative after import; initial exports JSON. LLMs may arrange exports into Markdown; no requirement to regenerate old Markdown byte-for-byte. |
| D12 | Build P1+P2 now. P3/P4 later; follow-up questions do not block independent approved work. |
| K1 | Copy OpenAlex key into ignored litkit secrets (parent handles it). |
| K2 | Store contact email in ignored secrets; note explicitly overrides the selected committed-config option. Never publish it. |
| T1 | Existing key located/verified in the original session; no credential values copied into brain. |

## Provisional source weights
FWCI .20; field/year percentile .20; influential-citation share .10; local corpus citations .15; venue two-year citedness .10; venue h-index .05; citation-context support .10; low self-citation .05; recency/growth .05. Preserve raw values, transforms, caps, weights, coverage, multipliers, rule version and timestamp for each computed score. A missing/unsupported context judgment must remain missing, not fabricated.

## Why
The research workflow needs persistent reproducible searching, local indexing, text extraction, quotations and quality provenance rather than inconsistent ad-hoc LLM steps. Optional LLM analysis benefits from compact structured exports. Impact is not truth, and venue metrics do not verify a claim.

## Open frontier
D1e-review: calibration protocol; D5a: replication adjudication; D10a: future GUI; D6a: per-run API budgets; D7a: public exports/copyright/privacy. See [[actions/ACTIONS]].
