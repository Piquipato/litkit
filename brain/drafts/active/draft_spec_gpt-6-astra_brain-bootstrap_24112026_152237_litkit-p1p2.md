---
file: brain/drafts/active/draft_spec_gpt-6-astra_brain-bootstrap_24112026_152237_litkit-p1p2.md
produced_by_model: gpt-6-astra
produced_by_agent: brain-bootstrap
created: 2026-11-24T15:21:15+01:00
last_updated: 2026-11-24T15:21:15+01:00
---

# Approved P1/P2 implementation boundary

kind: spec; status: approved-scope; audience: implementing agents. Source: [[wiki/decisions]] and archived round-1 form. This scoped brief supersedes conflicting parts of the historical nanovalve proposal; it does not certify implementation completion.

## Deliverables
- P1: Click init, legacy import, multi-provider enrichment, transparent source/quote quality components, SQLite truth and JSON-first export.
- P2: capped depth-1 forward/backward snowball, Louvain communities, ranked frontier with individual components, selectable GraphML/offline HTML/PNG.
- General research configuration, separate corpus directories, portable conda-forge environment, docs/src/tests layout. SJR CSV fetch/update helper with provenance and manual-import fallback if blocked.
- Deterministic core, optional LLM quote extraction disabled by default; all proposals must be verified against source text. LLM formatting is downstream of JSON exports.

## Verification contract
Run offline fixture tests for adapters/cache, import losslessness, scoring transforms/missingness/veto/coverage, component persistence, graph round-trip, stable CLI and JSON exports. Confirm secrets and contact email never enter DB/cache keys/logs/exports. Distinguish fixture tests from live provider validation. Verify legacy counts against the external source rather than inventing migration success. Preserve source files and report mismatches. Check no network in offline mode. Publish no corpus text or JSON automatically.

## Remaining decisions
Final weights, GUI, live-run budgets, replication judgment and public-data policy are open in [[actions/ACTIONS]]. Implement approved independent branches now; keep unresolved defaults explicitly provisional. Acquisition P3 and later P4 are not silently included in the current scope.
