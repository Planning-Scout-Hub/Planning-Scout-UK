"""
LeadRepository — read-only domain interface over the MAPlanning Google Sheet.

This module is the ONLY place gspread, column indices, or sheet-tab knowledge
is allowed to live. Callers (API handlers, MCP tools) see typed `Lead`
objects through three methods:

    repo = LeadRepository()
    repo.list_leads(LeadFilters(min_score=80))
    repo.get_lead(council="Leeds", ref="24/01234/FUL")
    repo.list_councils()

Caching strategy (see CLAUDE.md "gspread read latency"):
- Full Leads tab fetched in one call, parsed into a list of `Lead` objects.
- TTL between 4 and 6 minutes (random jitter avoids thundering herd when
  multiple API workers expire simultaneously).
- Single-flight: concurrent cache misses are coalesced under a single lock.
- Stale-while-revalidate: when the upstream gspread call fails after TTL
  expiry, the last successful fetch is returned instead of raising — so a
  transient Google Sheets outage degrades freshness, not availability.

Read-only by design. Write methods are deliberately absent; the engine remains
the only writer to the sheet, preserving the Data Integrity Rules in CLAUDE.md
(notably: Mark's Comments in col 17 is human-edited and must never be
overwritten by an API).
"""

from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from dataclasses import asdict, dataclass
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials as SACredentials


__all__ = ["Lead", "LeadFilters", "LeadRepository"]


logger = logging.getLogger(__name__)


# ── Configuration ───────────────────────────────────────────────────────────
# Default sheet ID mirrors engine.py:27. Override via SHEET_ID env var.
_DEFAULT_SHEET_ID = "172bpv-b2_nK5ENE1XPk5rWeokvnr1sjHvLBfVzHWh6c"
_LEADS_TAB = "Leads"

# Jittered TTL band — first call picks a random point in [min, max).
_TTL_MIN_SEC = 240   # 4 min
_TTL_MAX_SEC = 360   # 6 min


# ── Domain types ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Lead:
    """One qualified planning lead. Read-only view of a Leads tab row."""

    council: str
    ref: str
    address: str
    description: str
    app_type: str
    applicant: str
    agent: str
    date_received: str            # free-text — format varies per council
    date_decided: str             # free-text
    decision: str                 # "REFUSED" or "APPROVED — ..."
    triggers: tuple[str, ...]     # parsed from the comma-joined sheet string
    score: int                    # 0-100
    keyword: str
    portal_url: str
    decision_doc_url: str
    date_found: str               # "YYYY-MM-DD HH:MM"
    marks_comments: str           # human-edited in the sheet (read-only here)
    ai_evaluation: str
    winability: str               # HIGH / MEDIUM / LOW / ""
    recommended_action: str
    top_trigger: str
    est_work_time: str
    days_to_appeal: Optional[int]      # None when sheet has "Unknown" / blank
    appeal_urgency: Optional[int]
    est_project_value: str
    developer: str
    architect: str
    impact_probability: Optional[int]  # parsed from "85%" → 85
    ch_number: str
    registered_address: str
    contact_link: str
    is_enforcement: bool

    def to_dict(self) -> dict:
        d = asdict(self)
        d["triggers"] = list(self.triggers)
        return d


@dataclass
class LeadFilters:
    """Optional filters for `list_leads`. All set fields are AND-combined."""

    council: Optional[str] = None              # exact match, case-insensitive
    councils: Optional[list[str]] = None       # OR over multiple councils
    min_score: Optional[int] = None
    max_score: Optional[int] = None
    decision: Optional[str] = None             # substring match (e.g. "REFUSED")
    winability: Optional[str] = None           # HIGH / MEDIUM / LOW
    text_contains: Optional[str] = None        # substring across address/description/triggers
    enforcement_only: bool = False
    limit: Optional[int] = None                # cap result size after filtering


# ── Cache ───────────────────────────────────────────────────────────────────

class _TTLCache:
    """Jittered TTL cache with single-flight refresh + stale-while-revalidate."""

    def __init__(self, ttl_min: int = _TTL_MIN_SEC, ttl_max: int = _TTL_MAX_SEC):
        self._ttl_min = ttl_min
        self._ttl_max = ttl_max
        self._data: Optional[object] = None
        self._fetched_at = 0.0
        self._current_ttl = float(ttl_min)
        self._lock = threading.Lock()

    def _is_fresh(self) -> bool:
        if self._data is None:
            return False
        return (time.monotonic() - self._fetched_at) < self._current_ttl

    def get(self, fetch_fn) -> object:
        """Return cached data if fresh; otherwise fetch under single-flight."""
        if self._is_fresh():
            return self._data

        with self._lock:
            # Double-check: another thread may have refreshed while we waited.
            if self._is_fresh():
                return self._data

            try:
                new_data = fetch_fn()
            except Exception as e:
                if self._data is not None:
                    age = time.monotonic() - self._fetched_at
                    logger.warning(
                        "Upstream fetch failed (%s); serving stale cache (age %.0fs)",
                        e, age,
                    )
                    return self._data
                raise  # no stale fallback available — propagate

            self._data = new_data
            self._fetched_at = time.monotonic()
            self._current_ttl = random.uniform(self._ttl_min, self._ttl_max)
            return self._data


# ── Auth + row parsing (private) ────────────────────────────────────────────

def _gspread_client():
    """Build an authorised read-only gspread client."""
    sa_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON", "").strip()
    if not sa_json:
        raise RuntimeError(
            "GCP_SERVICE_ACCOUNT_JSON env var not set — needed to read the sheet"
        )
    info = json.loads(sa_json)
    creds = SACredentials.from_service_account_info(info, scopes=[
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ])
    return gspread.authorize(creds)


def _parse_int_or_none(v: object) -> Optional[int]:
    if v is None:
        return None
    s = str(v).strip().rstrip("%")
    if not s or s.lower() == "unknown":
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _parse_int(v: object, default: int = 0) -> int:
    r = _parse_int_or_none(v)
    return default if r is None else r


def _parse_triggers(raw: str) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(t.strip() for t in raw.split(",") if t.strip())


def _row_to_lead(row: dict) -> Lead:
    """Convert one gspread row (string-typed dict) into a typed Lead."""
    return Lead(
        council=str(row.get("Council", "")),
        ref=str(row.get("Reference", "")),
        address=str(row.get("Address", "")),
        description=str(row.get("Description", "")),
        app_type=str(row.get("App Type", "")),
        applicant=str(row.get("Applicant", "")),
        agent=str(row.get("Agent", "")),
        date_received=str(row.get("Date Received", "")),
        date_decided=str(row.get("Date Decided", "")),
        decision=str(row.get("Decision", "")),
        triggers=_parse_triggers(str(row.get("Trigger Words", ""))),
        score=_parse_int(row.get("Score"), default=0),
        keyword=str(row.get("Keyword", "")),
        portal_url=str(row.get("Portal Link", "")),
        decision_doc_url=str(row.get("Decision Doc URL", "")),
        date_found=str(row.get("Date Found", "")),
        marks_comments=str(row.get("Mark's Comments", "")),
        ai_evaluation=str(row.get("AI Evaluation", "")),
        winability=str(row.get("Winability", "")),
        recommended_action=str(row.get("Recommended Action", "")),
        top_trigger=str(row.get("Top Trigger", "")),
        est_work_time=str(row.get("Est. Work Time", "")),
        days_to_appeal=_parse_int_or_none(row.get("Days to Appeal")),
        appeal_urgency=_parse_int_or_none(row.get("Appeal Urgency")),
        est_project_value=str(row.get("Est. Project Value", "")),
        developer=str(row.get("Developer", "")),
        architect=str(row.get("Architect", "")),
        impact_probability=_parse_int_or_none(row.get("Impact Probability")),
        ch_number=str(row.get("CH Number", "")),
        registered_address=str(row.get("Registered Address", "")),
        contact_link=str(row.get("Contact Link", "")),
        is_enforcement=str(row.get("Is Enforcement", "")).strip().upper() == "YES",
    )


# ── Public API ──────────────────────────────────────────────────────────────

class LeadRepository:
    """
    Read-only repository over the MAPlanning Leads tab.

    The three public methods are the entire surface area. Nothing about
    gspread, sheet structure, or column indices is allowed to leak through
    them. Designed so the storage backend can be swapped (e.g. for a
    Postgres sync later) without API consumers noticing.

    Reads are cached for 4–6 minutes with jitter, single-flight on misses,
    and stale-while-revalidate on upstream failure.
    """

    def __init__(self,
                 sheet_id: Optional[str] = None,
                 cache: Optional[_TTLCache] = None):
        self._sheet_id = sheet_id or os.environ.get("SHEET_ID") or _DEFAULT_SHEET_ID
        self._cache = cache or _TTLCache()
        self._client = None  # lazy — only built on first cache miss

    # ── Public read methods ───────────────────────────────────────

    def list_leads(self, filters: Optional[LeadFilters] = None) -> list[Lead]:
        leads = self._all_leads()
        if filters is None:
            return list(leads)
        return self._apply_filters(leads, filters)

    def get_lead(self, council: str, ref: str) -> Optional[Lead]:
        c = council.strip().lower()
        r = ref.strip()
        for lead in self._all_leads():
            if lead.council.strip().lower() == c and lead.ref.strip() == r:
                return lead
        return None

    def list_councils(self) -> list[str]:
        seen = set()
        out: list[str] = []
        for lead in self._all_leads():
            name = lead.council.strip()
            if name and name not in seen:
                seen.add(name)
                out.append(name)
        return sorted(out)

    # ── Internals ─────────────────────────────────────────────────

    def _all_leads(self) -> list[Lead]:
        return self._cache.get(self._fetch_all_leads)  # type: ignore[return-value]

    def _fetch_all_leads(self) -> list[Lead]:
        if self._client is None:
            self._client = _gspread_client()
        ws = self._client.open_by_key(self._sheet_id).worksheet(_LEADS_TAB)
        rows = ws.get_all_records()
        return [_row_to_lead(r) for r in rows]

    @staticmethod
    def _apply_filters(leads: list[Lead], f: LeadFilters) -> list[Lead]:
        wanted_councils: Optional[set[str]] = None
        if f.councils:
            wanted_councils = {c.strip().lower() for c in f.councils}
        if f.council:
            wanted_councils = wanted_councils or set()
            wanted_councils.add(f.council.strip().lower())

        text = f.text_contains.lower() if f.text_contains else None
        decision_substr = f.decision.upper() if f.decision else None
        winability = f.winability.upper() if f.winability else None

        out: list[Lead] = []
        for lead in leads:
            if wanted_councils and lead.council.strip().lower() not in wanted_councils:
                continue
            if f.min_score is not None and lead.score < f.min_score:
                continue
            if f.max_score is not None and lead.score > f.max_score:
                continue
            if decision_substr and decision_substr not in lead.decision.upper():
                continue
            if winability and lead.winability.upper() != winability:
                continue
            if f.enforcement_only and not lead.is_enforcement:
                continue
            if text:
                hay = " ".join((
                    lead.address, lead.description, " ".join(lead.triggers),
                )).lower()
                if text not in hay:
                    continue
            out.append(lead)
            if f.limit is not None and len(out) >= f.limit:
                break
        return out
