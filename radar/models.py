"""Core data types."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _norm(s: str) -> str:
    s = s.replace("İ", "i").lower().replace("̇", "")
    s = s.translate(str.maketrans("çğıöşüâîûéèàáíóúñäß", "cgiosuaiueeaaiounas"))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


@dataclass
class Job:
    source: str                 # linkedin | euraxess | greenhouse
    native_id: str              # id inside the source
    title: str
    company: str
    location: str
    url: str
    posted: str = ""            # ISO date if known
    description: str = ""       # snippet or full text
    extra: dict = field(default_factory=dict)  # source-specific facts (seniority, employment type ...)

    # ---- filled by the matcher (radar/match.py), optionally refined by Claude (radar/llm.py)
    first_seen: str = ""
    category: str = ""                  # dogrudan | uygun | stretch | dusuk
    category_reasons: list[str] = field(default_factory=list)
    score: int | None = None            # 0-100, for sorting inside a category
    scored_by: str = ""                 # "kural" | "claude"
    education: dict = field(default_factory=dict)   # {level, field, label}
    experience: dict = field(default_factory=dict)  # {min, max, level, label, fit}
    work_mode: str = ""                 # uzaktan | hibrit | ofiste | belirtilmemis
    requirements: list[dict] = field(default_factory=list)  # [{label, have}]
    matches: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    role_family: str = ""
    role_label: str = ""
    sectors: list[str] = field(default_factory=list)
    loc_tier: int = 5
    loc_label: str = ""
    is_internship: bool = False
    letter: dict | None = None          # {"subject", "cover_letter", "cv_highlights"}

    @property
    def id(self) -> str:
        return f"{self.source}:{self.native_id}"

    @property
    def dedupe_key(self) -> str:
        """Same role posted through several queries/sources collapses to one entry."""
        raw = f"{_norm(self.title)}|{_norm(self.company)}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})
