"""
Read-only FastAPI for MAPlanning leads.

The only data dependency is `LeadRepository` — this module is forbidden from
importing gspread, touching sheet column names, or knowing about the
Leads-tab structure. That keeps the storage backend swappable (e.g. when we
later move to a Postgres sync; see the recommendation in CLAUDE.md).

All endpoints are read-only. Writes still go through the engine pipeline so
the Data Integrity Rules in CLAUDE.md (Mark's Comments, Status) are preserved.

Cache: a process-wide LeadRepository singleton. A lifespan startup hook
pre-warms the cache before uvicorn accepts traffic, so even the first
user-facing request is sub-second. Subsequent requests are cache hits
(< 50 ms) until the jittered 4-6 min TTL expires.

Run locally:
    GCP_SERVICE_ACCOUNT_JSON="$(cat path/to/service-account.json)" \
        uvicorn core.api:app --reload --port 8000

Visit http://localhost:8000/docs for the auto-generated OpenAPI UI.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Optional

# Allow `uvicorn core.api:app` to work whether invoked from the repo root
# or via a packaged install — same trick as scripts/test_repository.py.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from core.repository import Lead, LeadFilters, LeadRepository


logger = logging.getLogger(__name__)


# ── Process-wide repository ─────────────────────────────────────────────────
_repo = LeadRepository()


# ── Response models ─────────────────────────────────────────────────────────

class LeadOut(BaseModel):
    """All 32 fields of a Leads-tab row, typed where the sheet allows it."""

    council: str
    ref: str
    address: str
    description: str
    app_type: str
    applicant: str
    agent: str
    date_received: str
    date_decided: str
    decision: str
    triggers: list[str]
    score: int
    keyword: str
    portal_url: str
    decision_doc_url: str
    date_found: str
    marks_comments: str
    ai_evaluation: str
    winability: str
    recommended_action: str
    top_trigger: str
    est_work_time: str
    days_to_appeal: Optional[int]
    appeal_urgency: Optional[int]
    est_project_value: str
    developer: str
    architect: str
    impact_probability: Optional[int]
    ch_number: str
    registered_address: str
    contact_link: str
    is_enforcement: bool

    @classmethod
    def from_domain(cls, lead: Lead) -> "LeadOut":
        return cls(**lead.to_dict())


class SearchResponse(BaseModel):
    count: int = Field(..., description="Number of leads returned (may be capped by `limit`).")
    leads: list[LeadOut]


class HealthResponse(BaseModel):
    status: str


# ── Lifespan: pre-warm the cache so the first request is fast ───────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        leads = _repo.list_leads()
        logger.info("Repository cache pre-warmed (%d leads)", len(leads))
    except Exception as e:
        # Don't block startup — /health still serves while we wait for
        # upstream to recover. First /leads call will retry the fetch.
        logger.warning("Cache pre-warm failed: %s — first request will retry", e)
    yield


app = FastAPI(
    title="MAPlanning Leads API",
    description=(
        "Read-only API over the MAPlanning Google Sheet. All requests go "
        "through LeadRepository (4–6 min jittered cache, "
        "stale-while-revalidate on upstream failure)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


# ── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Liveness check. Always sub-millisecond, never touches upstream."""
    return HealthResponse(status="ok")


@app.get("/councils", response_model=list[str], tags=["leads"])
def list_councils() -> list[str]:
    """Distinct councils that have at least one lead in the sheet."""
    return _repo.list_councils()


@app.get("/leads", response_model=SearchResponse, tags=["leads"])
def search_leads(
    council: Optional[str] = Query(
        None, description="Exact council name (case-insensitive).",
    ),
    app_type: Optional[str] = Query(
        None, description="Substring match on App Type (e.g. 'Full', 'Outline').",
    ),
    decision: Optional[str] = Query(
        None, description="Substring match on Decision (e.g. 'REFUSED').",
    ),
    winability: Optional[str] = Query(
        None, description="HIGH / MEDIUM / LOW.",
    ),
    min_score: Optional[int] = Query(
        None, ge=0, le=100, description="Only leads scoring at least this.",
    ),
    max_days_to_appeal: Optional[int] = Query(
        None, ge=0,
        description="Only leads whose Days to Appeal is known and ≤ N days remaining.",
    ),
    enforcement_only: bool = Query(
        False, description="Restrict to enforcement-notice appeals.",
    ),
    limit: Optional[int] = Query(
        None, ge=1, le=1000, description="Cap on result count.",
    ),
) -> SearchResponse:
    """Search leads with the documented filters. Filters AND-combine."""
    flt = LeadFilters(
        council=council,
        app_type=app_type,
        decision=decision,
        winability=winability,
        min_score=min_score,
        max_days_to_appeal=max_days_to_appeal,
        enforcement_only=enforcement_only,
        limit=limit,
    )
    leads = _repo.list_leads(flt)
    return SearchResponse(
        count=len(leads),
        leads=[LeadOut.from_domain(l) for l in leads],
    )


@app.get("/leads/{council}/{ref:path}", response_model=LeadOut, tags=["leads"])
def get_lead(council: str, ref: str) -> LeadOut:
    """Look up one lead by (council, ref). Returns all 32 fields. 404 if missing.

    The ref can contain forward slashes (e.g. `24/01234/FUL`) — pass it
    literally; the route uses a path-converter so the URL is browser-friendly.
    """
    lead = _repo.get_lead(council=council, ref=ref)
    if lead is None:
        raise HTTPException(
            status_code=404,
            detail=f"No lead found for council={council!r} ref={ref!r}",
        )
    return LeadOut.from_domain(lead)
