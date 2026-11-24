---
file: brain/wiki/hindsight-sync.md
produced_by_model: gpt-6-astra
produced_by_agent: brain-bootstrap
created: 2026-11-24T15:21:15+01:00
last_updated: 2026-11-24T15:21:15+01:00
---

# Memory and vault integration

## Hindsight
- Bank ID: `litkit`; project selector `.hindsight/config.toml`.
- Created through the live OpenAPI-discovered `PUT /v1/default/banks/{bank_id}` at http://127.0.0.1:1235 . Port 1236 returned 404 for openapi.json.
- Verified by `GET /v1/default/banks?q=litkit`: exact bank litkit exists with litkit-specific mission. Initial fact_count was zero; no claim of seeded memories or automatic sync.
- Bank setup is complete; decision ingestion and runtime trust-registration/automatic recall remain unverified. No global Hermes profile configuration was changed.

## Obsidian
- `brain/.obsidian/app.json` configures relative wikilinks and unsupported-file visibility.
- Main-vault junction `E:/plalandelg/obsidian/plalandelg/plalandelg/Projects/litkit-brain` targets `E:/plalandelg/litkit/brain`.
- Verified Windows junction and INDEX.md same-file identity. No existing folder overwritten.
- Open in main vault: obsidian://open?vault=plalandelg&file=Projects%2Flitkit-brain%2FINDEX . Standalone application vault registration was not changed.

## gbrain — blocked
Local CLI discovery worked, but `gbrain sources list --json` failed `pglite_busy`: the live shared serve owns the datastore (PID 9108 at verification). No process stopped and no lock removed. Available MCP catalog exposes no source administration/sync tools. Source registration and sync therefore remain pending, not successful. Resume through an authorized source-admin surface or a coordinated maintenance window; scope ingestion to the public brain and never import secrets/corpus.

## Protected instruction files — blocked
Writing root AGENTS.md, root CLAUDE.md and brain/config/AGENTS.md triggered protected-file approval timeouts. Do not bypass or retry without explicit runtime approval. The generated HERMES pointer links only existing files and reports the missing canonical instructions. Canonical CLAUDE instructions also remain pending. Bootstrap is partial for this reason.
