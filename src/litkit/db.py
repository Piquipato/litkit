"""SQLite storage: stable local IDs, external-identifier map, append-only metric snapshots.

All imported legacy records are kept losslessly in ``legacy_json``. Metadata and metrics are
additive: API enrichments never overwrite user-curated evidence. Every score stores its inputs,
transforms and weights as JSON, so it is reproducible even if the rules change later.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1
SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS works (
    id TEXT PRIMARY KEY,
    local_key TEXT UNIQUE,
    doi TEXT,
    title TEXT,
    year INTEGER,
    venue_id TEXT,
    type TEXT,
    abstract TEXT,
    status TEXT NOT NULL DEFAULT 'candidate',
    flag TEXT,
    peer_reviewed INTEGER,             -- NULL = unknown; 0/1 = explicitly classified
    is_retracted INTEGER,
    bibtex TEXT,
    summary TEXT,
    topics_json TEXT,
    authors_json TEXT,
    oa_url TEXT,
    legacy_json TEXT,
    added_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS works_doi ON works(doi) WHERE doi IS NOT NULL;
CREATE TABLE IF NOT EXISTS identifiers (
    scheme TEXT NOT NULL, value TEXT NOT NULL, work_id TEXT NOT NULL REFERENCES works(id),
    PRIMARY KEY(scheme, value)
);
CREATE TABLE IF NOT EXISTS venues (
    id TEXT PRIMARY KEY, name TEXT, issn_l TEXT, type TEXT, publisher TEXT,
    is_in_doaj INTEGER, summary_json TEXT, raw_json TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS edges (
    citing TEXT NOT NULL REFERENCES works(id), cited TEXT NOT NULL REFERENCES works(id),
    source TEXT NOT NULL, first_seen TEXT NOT NULL,
    PRIMARY KEY(citing, cited, source), CHECK(citing <> cited)
);
CREATE TABLE IF NOT EXISTS enrichments (
    id INTEGER PRIMARY KEY, work_id TEXT NOT NULL REFERENCES works(id),
    source TEXT NOT NULL, at TEXT NOT NULL, outcome TEXT NOT NULL, note TEXT,
    cache_key TEXT, payload_json TEXT
);
CREATE TABLE IF NOT EXISTS metrics (
    work_id TEXT NOT NULL REFERENCES works(id), source TEXT NOT NULL, name TEXT NOT NULL,
    at TEXT NOT NULL, value_json TEXT, provenance_json TEXT,
    PRIMARY KEY(work_id, source, name, at)
);
CREATE TABLE IF NOT EXISTS citation_contexts (
    id TEXT PRIMARY KEY, cited TEXT NOT NULL REFERENCES works(id), citing_id TEXT,
    context TEXT NOT NULL, intents_json TEXT, is_influential INTEGER,
    source TEXT NOT NULL, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY, work_id TEXT NOT NULL REFERENCES works(id), path TEXT NOT NULL,
    kind TEXT, sha256 TEXT, bytes INTEGER, text_path TEXT, at TEXT NOT NULL,
    UNIQUE(work_id, path)
);
CREATE TABLE IF NOT EXISTS quotes (
    id TEXT PRIMARY KEY, work_id TEXT NOT NULL REFERENCES works(id),
    location TEXT, quote TEXT, parameter TEXT, value_json TEXT, model_value_json TEXT,
    unit TEXT, uncertainty TEXT, n_json TEXT, conditions_json TEXT,
    evidence_class TEXT, chain TEXT, chain_depth INTEGER,
    explanation TEXT, use_note TEXT, topic TEXT, origin TEXT,
    ocr_note TEXT, legacy_json TEXT, added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quote_checks (
    quote_id TEXT NOT NULL REFERENCES quotes(id), at TEXT NOT NULL, method TEXT NOT NULL,
    result TEXT NOT NULL, pages_json TEXT, note TEXT,
    PRIMARY KEY(quote_id, at, method)
);
CREATE TABLE IF NOT EXISTS measurements (
    id TEXT PRIMARY KEY, quote_id TEXT REFERENCES quotes(id), work_id TEXT REFERENCES works(id),
    parameter TEXT, value_json TEXT, unit TEXT, conditions_json TEXT, uncertainty_json TEXT,
    transferable INTEGER, note TEXT, legacy_json TEXT
);
CREATE TABLE IF NOT EXISTS excluded (
    id TEXT PRIMARY KEY, reason TEXT, record_json TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
    params_json TEXT, summary_json TEXT
);
CREATE TABLE IF NOT EXISTS search_hits (
    run_id INTEGER NOT NULL REFERENCES runs(id), work_id TEXT NOT NULL REFERENCES works(id),
    rank INTEGER, PRIMARY KEY(run_id, work_id)
);
CREATE TABLE IF NOT EXISTS scores (
    entity TEXT NOT NULL, entity_id TEXT NOT NULL, at TEXT NOT NULL,
    rule_version TEXT NOT NULL, score REAL, coverage REAL, components_json TEXT NOT NULL,
    PRIMARY KEY(entity, entity_id, at)
);
CREATE TABLE IF NOT EXISTS sjr (
    year INTEGER NOT NULL, source_id TEXT NOT NULL, title TEXT, issns_json TEXT,
    sjr REAL, quartile TEXT, raw_json TEXT, sha256 TEXT,
    PRIMARY KEY(year, source_id)
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def loads(s: str | None, default: Any = None) -> Any:
    return json.loads(s) if s is not None else default


def digest(data: str | bytes) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def connect(path: Path | str) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(SCHEMA)
    con.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
    con.commit()
    return con


@contextlib.contextmanager
def database(path: Path | str) -> Iterator[sqlite3.Connection]:
    con = connect(path)
    try:
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    d = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d if d.startswith("10.") else None


def short_oa(value: str | None) -> str | None:
    return value.rstrip("/").rsplit("/", 1)[-1] if value else None


def resolve(con: sqlite3.Connection, value: str) -> str | None:
    """Resolve a local key, DOI, OpenAlex id/URL or S2 id to the stable local work id."""
    row = con.execute("SELECT id FROM works WHERE id=? OR local_key=?", (value, value)).fetchone()
    if row:
        return row[0]
    doi = normalize_doi(value)
    vals = [value, short_oa(value)]
    if doi:
        vals.append(doi)
    for v in vals:
        row = con.execute("SELECT work_id FROM identifiers WHERE value=?", (v,)).fetchone()
        if row:
            return row[0]
    return None


def add_identifier(con: sqlite3.Connection, wid: str, scheme: str, value: str | None) -> None:
    if not value:
        return
    if scheme == "doi":
        value = normalize_doi(value)
    elif scheme == "openalex":
        value = short_oa(value)
    if not value:
        return
    old = con.execute("SELECT work_id FROM identifiers WHERE scheme=? AND value=?", (scheme, value)).fetchone()
    if old and old[0] != wid:
        raise ValueError(f"Identifier conflict: {scheme}:{value} belongs to {old[0]}, not {wid}")
    con.execute("INSERT OR IGNORE INTO identifiers VALUES (?,?,?)", (scheme, value, wid))


def ensure_work(con: sqlite3.Connection, *, doi: str | None = None, openalex: str | None = None,
                s2: str | None = None, local_key: str | None = None, title: str | None = None,
                year: int | None = None, status: str = "candidate") -> str:
    doi, openalex = normalize_doi(doi), short_oa(openalex)
    wid = None
    for val in (local_key, doi, openalex, s2):
        if val:
            wid = resolve(con, val)
            if wid:
                break
    if wid is None:
        wid = (local_key or (f"doi:{doi}" if doi else None)
               or (f"oa:{openalex}" if openalex else None) or (f"s2:{s2}" if s2 else None))
        if wid is None:
            raise ValueError("A work needs at least one identifier")
        now = utcnow()
        con.execute(
            "INSERT INTO works(id,local_key,doi,title,year,status,added_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (wid, local_key, doi, title, year, status, now, now),
        )
    else:
        con.execute(
            "UPDATE works SET title=COALESCE(title,?), year=COALESCE(year,?), doi=COALESCE(doi,?), "
            "local_key=COALESCE(local_key,?), updated_at=? WHERE id=?",
            (title, year, doi, local_key, utcnow(), wid),
        )
        if status == "corpus":
            con.execute("UPDATE works SET status='corpus' WHERE id=?", (wid,))
    for scheme, val in (("doi", doi), ("openalex", openalex), ("s2", s2)):
        add_identifier(con, wid, scheme, val)
    return wid


def edge(con: sqlite3.Connection, citing: str, cited: str, source: str) -> None:
    if citing == cited:
        return
    con.execute("INSERT OR IGNORE INTO edges VALUES (?,?,?,?)", (citing, cited, source, utcnow()))


def metric(con: sqlite3.Connection, wid: str, source: str, name: str, value: Any,
           *, at: str | None = None, provenance: Any = None) -> None:
    con.execute("INSERT OR REPLACE INTO metrics VALUES (?,?,?,?,?,?)",
                (wid, source, name, at or utcnow(), dumps(value), dumps(provenance)))


def latest_metrics(con: sqlite3.Connection, wid: str) -> dict[str, dict[str, Any]]:
    rows = con.execute("SELECT source,name,value_json,at,provenance_json FROM metrics WHERE work_id=? ORDER BY at", (wid,))
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        out.setdefault(r["source"], {})[r["name"]] = {
            "value": loads(r["value_json"]), "at": r["at"], "provenance": loads(r["provenance_json"]),
        }
    return out


def latest_score(con: sqlite3.Connection, entity: str, eid: str) -> dict | None:
    row = con.execute("SELECT * FROM scores WHERE entity=? AND entity_id=? ORDER BY at DESC LIMIT 1", (entity, eid)).fetchone()
    return dict(row) if row else None


def select_works(con: sqlite3.Connection, ids: tuple[str, ...] | list[str] | None = None,
                 status: str | None = "corpus", limit: int | None = None) -> list[sqlite3.Row]:
    if ids:
        wids = []
        for i in ids:
            wid = resolve(con, i)
            if wid is None:
                raise ValueError(f"Unknown work: {i}")
            wids.append(wid)
        q = "SELECT * FROM works WHERE id IN (" + ",".join("?" * len(wids)) + ") ORDER BY id"
        return con.execute(q, wids).fetchall()
    q, args = "SELECT * FROM works", []
    if status and status != "all":
        q += " WHERE status=?"
        args.append(status)
    q += " ORDER BY id"
    if limit:
        q += " LIMIT ?"
        args.append(limit)
    return con.execute(q, args).fetchall()


def start_run(con: sqlite3.Connection, kind: str, params: Any) -> int:
    cur = con.execute("INSERT INTO runs(kind,started_at,params_json) VALUES (?,?,?)", (kind, utcnow(), dumps(params)))
    return cur.lastrowid


def finish_run(con: sqlite3.Connection, rid: int, summary: Any) -> None:
    con.execute("UPDATE runs SET finished_at=?,summary_json=? WHERE id=?", (utcnow(), dumps(summary), rid))
    con.commit()


def counts(con: sqlite3.Connection) -> dict:
    tables = ("works", "quotes", "measurements", "edges", "venues", "metrics", "citation_contexts", "enrichments", "scores")
    out = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    out["works_by_status"] = dict(con.execute("SELECT status,COUNT(*) FROM works GROUP BY status").fetchall())
    out["flags"] = dict(con.execute("SELECT flag,COUNT(*) FROM works WHERE status='corpus' GROUP BY flag").fetchall())
    return out
