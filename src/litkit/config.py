"""Project configuration (``litkit.toml``) and user secrets.

A *project* is one literature search: a folder holding ``litkit.toml``, the SQLite database,
the HTTP cache, exports and graph outputs. Projects are found from ``--project``, the
``LITKIT_PROJECT`` environment variable, or by walking up from the current directory.

Secrets (API keys, contact email) are NOT stored in ``litkit.toml``. They live in a user-level
``secrets.toml`` (default: ``%APPDATA%/litkit/secrets.toml`` on Windows, ``~/.config/litkit/secrets.toml``
elsewhere; override with ``LITKIT_SECRETS``). Environment variables ``LITKIT_OPENALEX_API_KEY``,
``LITKIT_S2_API_KEY`` and ``LITKIT_CONTACT_EMAIL`` override the file.
"""

from __future__ import annotations

import copy
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli_w

CONFIG_NAME = "litkit.toml"

# Every default lives here and is written into a new litkit.toml by ``litkit init`` so the
# user (or an LLM agent) can read and edit the full configuration as plain text.
DEFAULT_CONFIG: dict[str, Any] = {
    "project": {
        "name": "unnamed",
        "description": "",
        "db": "litkit.db",
        "cache_dir": "cache",
        "export_dir": "exports",
        "dump_dir": "dump",
        "graph_dir": "graph",
        "raw_dir": "raw",
        "text_dir": "raw/text",
    },
    "http": {
        "timeout_s": 30.0,
        "max_retries": 4,
        "min_interval_s": {  # polite per-host spacing between requests
            "api.openalex.org": 0.12,
            "api.semanticscholar.org": 1.1,
            "api.opencitations.net": 0.3,
            "api.crossref.org": 0.1,
            "api.unpaywall.org": 0.1,
            "www.ebi.ac.uk": 0.2,
            "export.arxiv.org": 3.0,
            "www.scimagojr.com": 2.0,
        },
        "cache_ttl_days": 30,
    },
    "sources": {
        "enabled": ["openalex"],  # Other provider adapters are not implemented yet.
        "s2_contexts_per_work": 100,
    },
    "snowball": {
        "max_citing_per_work": 200,  # cap of citing works fetched per corpus work (sorted by citations)
        "max_new_works_per_run": 5000,
    },
    "novelty": {
        "cd_window_years": 5,  # CD_5
        "cd_max_references": 100,  # OpenAlex OR-filter limit; larger reference lists are truncated + flagged
    },
    "graph": {
        "louvain_resolution": 1.0,
        "louvain_seed": 42,
        "include_candidates": True,
        "html_max_nodes": 1500,
    },
    "frontier": {
        "provisional": True,
        "weights": {
            "cited_by_corpus": 0.35,
            "cites_corpus": 0.20,
            "coupling": 0.15,
            "relevance": 0.15,
            "quality_prior": 0.15,
        },
        "caps": {"cited_by_corpus": 10, "cites_corpus": 10, "coupling": 30},
        "keywords": [],
    },
    "quality": {
        "rule_version": "q1-provisional",
        "provisional": True,
        "low_coverage_threshold": 0.5,
        "non_peer_reviewed_multiplier": 0.5,
        "retracted_multiplier": 0.0,
        # Source composite: each indicator -> fixed transform to [0,1] -> weight.
        "source": {
            "fwci": {"weight": 0.20, "transform": "linear_cap", "cap": 2.0},  # min(FWCI/2, 1)
            "citation_percentile": {"weight": 0.20, "transform": "identity01"},
            "influential_share": {"weight": 0.10, "transform": "identity01"},
            "cited_by_corpus": {"weight": 0.15, "transform": "log_cap", "cap": 20.0},
            "venue_2yr_citedness": {"weight": 0.10, "transform": "log_cap", "cap": 20.0},
            "venue_h_index": {"weight": 0.05, "transform": "log_cap", "cap": 1000.0},
            "citation_contexts": {"weight": 0.10, "transform": "log_cap", "cap": 50.0},
            "non_self_citation_share": {"weight": 0.05, "transform": "identity01"},
            "recent_citation_share": {"weight": 0.05, "transform": "identity01"},
        },
        # Quote evidence composite (kept separate from the inherited source score).
        "quote": {
            "evidence_class": {"weight": 0.30},
            "chain_depth": {"weight": 0.15},
            "verbatim": {"weight": 0.15},
            "uncertainty": {"weight": 0.15},
            "condition_match": {"weight": 0.15},
            "replication": {"weight": 0.10, "cap": 5.0},
        },
        "class_scores": {"measured": 1.0, "derived": 0.6, "cited": 0.3, "vendor": 0.2, "assumed": 0.0},
        "uncertainty_scores": {"ci": 1.0, "sd": 0.8, "sem": 0.8, "range": 0.5, "stated": 0.4, "none": 0.0},
        "replication_factor": 2.0,  # values within x/÷ this factor count as agreeing
    },
    # Optional research-question specific target conditions for quote condition-match.
    "experiment": {
        "pH": None,
        "T_C": None,
        "cation": None,  # e.g. "Na", "K"
        "pH_scale": 0.5,
        "T_scale_C": 5.0,
    },
    "secrets": {
        # Where the user-level secrets file is; empty = platform default.
        "file": "",
    },
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _strip_none(d: Any) -> Any:
    """TOML has no null: drop None values when writing."""
    if isinstance(d, dict):
        return {k: _strip_none(v) for k, v in d.items() if v is not None}
    return d


@dataclass
class Project:
    root: Path
    config: dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_CONFIG))

    def path(self, key: str) -> Path:
        p = Path(self.config["project"][key])
        return p if p.is_absolute() else self.root / p

    @property
    def db_path(self) -> Path:
        return self.path("db")

    @property
    def config_path(self) -> Path:
        return self.root / CONFIG_NAME

    def get(self, dotted: str, default: Any = None) -> Any:
        cur: Any = self.config
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def save(self) -> None:
        self.config_path.write_bytes(tomli_w.dumps(_strip_none(self.config)).encode("utf-8"))


def find_project_root(start: Path | None = None) -> Path | None:
    env = os.environ.get("LITKIT_PROJECT")
    if env:
        return Path(env)
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / CONFIG_NAME).exists():
            return p
    return None


def load_project(root: Path | str | None = None) -> Project:
    r = Path(root) if root else find_project_root()
    if r is None:
        raise FileNotFoundError(
            f"No {CONFIG_NAME} found (use --project PATH, set LITKIT_PROJECT, or run `litkit init`)."
        )
    cfg_path = r / CONFIG_NAME
    if not cfg_path.exists():
        raise FileNotFoundError(f"{cfg_path} does not exist; run `litkit init {r}` first.")
    user = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    return Project(root=r, config=_deep_merge(DEFAULT_CONFIG, user))


def init_project(root: Path, name: str | None = None) -> Project:
    root.mkdir(parents=True, exist_ok=True)
    proj = Project(root=root)
    proj.config["project"]["name"] = name or root.name
    if not proj.config_path.exists():
        proj.save()
    else:
        proj = load_project(root)
    for key in ("cache_dir", "export_dir", "dump_dir", "graph_dir"):
        proj.path(key).mkdir(parents=True, exist_ok=True)
    return proj


# ---------------------------------------------------------------- secrets

SECRET_KEYS = {
    "openalex_api_key": "LITKIT_OPENALEX_API_KEY",
    "s2_api_key": "LITKIT_S2_API_KEY",
    "contact_email": "LITKIT_CONTACT_EMAIL",
}


def secrets_path(project: Project | None = None) -> Path:
    env = os.environ.get("LITKIT_SECRETS")
    if env:
        return Path(env)
    if project is not None and project.get("secrets.file"):
        return Path(project.get("secrets.file"))
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "litkit" / "secrets.toml"


def load_secrets(project: Project | None = None) -> dict[str, str]:
    p = secrets_path(project)
    data: dict[str, str] = {}
    if p.exists():
        data = {k: str(v) for k, v in tomllib.loads(p.read_text(encoding="utf-8")).items()}
    for key, env in SECRET_KEYS.items():
        if os.environ.get(env):
            data[key] = os.environ[env]
    return data


def set_secret(key: str, value: str, project: Project | None = None) -> Path:
    if key not in SECRET_KEYS:
        raise KeyError(f"unknown secret {key!r}; known: {', '.join(SECRET_KEYS)}")
    p = secrets_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    cur = tomllib.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    cur[key] = value
    p.write_bytes(tomli_w.dumps(cur).encode("utf-8"))
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return p


def mask(value: str | None) -> str:
    if not value:
        return "(unset)"
    if "@" in value:
        user, _, dom = value.partition("@")
        return f"{user[:2]}…@{dom}"
    return f"{value[:3]}…({len(value)} chars)"
