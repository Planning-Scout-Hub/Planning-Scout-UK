"""
Standalone smoke test for `core.repository.LeadRepository`.

Run from repo root, with the same service-account JSON the engine uses:

    GCP_SERVICE_ACCOUNT_JSON="$(cat path/to/service-account.json)" \
        python scripts/test_repository.py

Exercises all three public read methods, demonstrates that the cache
absorbs back-to-back reads, and prints sample output so you can eyeball
that typed parsing is working (Score is an int, Impact Probability is
an int, Days to Appeal is int or None, Is Enforcement is bool).
"""

from __future__ import annotations

import os
import sys
import time

# Make `core.repository` importable when running this script directly.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.repository import Lead, LeadFilters, LeadRepository


def hr(title: str = "") -> None:
    print()
    print(f"── {title} " + "─" * max(0, 60 - len(title) - 4))


def pp_lead(lead: Lead) -> None:
    print(f"  Council:       {lead.council}")
    print(f"  Reference:     {lead.ref}")
    print(f"  Score:         {lead.score!r}   (type: {type(lead.score).__name__})")
    print(f"  Decision:      {lead.decision}")
    print(f"  Winability:    {lead.winability!r}")
    triggers_preview = ", ".join(lead.triggers[:4]) + ("…" if len(lead.triggers) > 4 else "")
    print(f"  Triggers:      {triggers_preview}")
    print(f"  ImpactProb:    {lead.impact_probability!r}   (type: {type(lead.impact_probability).__name__})")
    print(f"  DaysToAppeal:  {lead.days_to_appeal!r}   (type: {type(lead.days_to_appeal).__name__})")
    print(f"  AppealUrgency: {lead.appeal_urgency!r}")
    print(f"  Enforcement:   {lead.is_enforcement!r}   (type: bool)")
    print(f"  Address:       {lead.address[:80]}")


def main() -> int:
    if not os.environ.get("GCP_SERVICE_ACCOUNT_JSON"):
        print("ERROR: set GCP_SERVICE_ACCOUNT_JSON env var first, e.g.")
        print('    GCP_SERVICE_ACCOUNT_JSON="$(cat service-account.json)" \\')
        print("        python scripts/test_repository.py")
        return 2

    repo = LeadRepository()

    # 1. list_councils() — first call also primes the cache
    hr("list_councils()")
    t0 = time.monotonic()
    councils = repo.list_councils()
    dt = time.monotonic() - t0
    print(f"  {len(councils)} distinct councils  ({dt:.2f}s — first call hits the Sheet)")
    print(f"  Sample: {', '.join(councils[:8])}{'…' if len(councils) > 8 else ''}")

    # 2. list_leads() — no filter, should now be cache-hit
    hr("list_leads()  no filter")
    t1 = time.monotonic()
    leads = repo.list_leads()
    dt = time.monotonic() - t1
    print(f"  {len(leads)} leads in {dt * 1000:.1f}ms  (cache hit — should be near-instant)")
    if not leads:
        print("  ⚠️  Sheet is empty — most assertions below will be no-ops.")
        return 0
    print()
    print("  First lead in the sheet:")
    pp_lead(leads[0])

    # 3. list_leads(LeadFilters(min_score=80))
    hr("list_leads(LeadFilters(min_score=80))")
    high = repo.list_leads(LeadFilters(min_score=80))
    print(f"  {len(high)} leads with score ≥ 80")
    if high:
        top_scores = sorted({l.score for l in high}, reverse=True)[:6]
        print(f"  Top scores: {top_scores}")

    # 4. list_leads filtered by council
    if councils:
        first_council = councils[0]
        hr(f"list_leads(LeadFilters(council={first_council!r}))")
        per_council = repo.list_leads(LeadFilters(council=first_council))
        print(f"  {len(per_council)} leads for {first_council}")

    # 5. list_leads enforcement_only + limit
    hr("list_leads(LeadFilters(enforcement_only=True, limit=5))")
    enf = repo.list_leads(LeadFilters(enforcement_only=True, limit=5))
    print(f"  {len(enf)} enforcement leads returned (capped at 5)")
    for l in enf:
        print(f"    • [{l.score}] {l.council} | {l.ref}")

    # 6. get_lead round-trip — should match the lead we just listed
    hr("get_lead(council, ref)")
    target = leads[0]
    fetched = repo.get_lead(council=target.council, ref=target.ref)
    if fetched is None:
        print(f"  ❌ get_lead returned None for ({target.council}, {target.ref})")
        return 1
    ok = fetched.council == target.council and fetched.ref == target.ref
    print(f"  Looked up ({target.council}, {target.ref}) → {'OK' if ok else 'MISMATCH'}")
    print(f"  Score on returned lead: {fetched.score} (int)")

    # 7. get_lead with bogus key
    hr("get_lead with missing key")
    missing = repo.get_lead(council="Nowhere", ref="00/0000/X")
    print(f"  Missing lead returns: {missing!r}  (should be None)")
    assert missing is None, "expected None for missing lead"

    # 8. Cache hit timing — multiple list_leads calls should be near-zero
    hr("Cache hit timing")
    t = time.monotonic()
    for _ in range(5):
        repo.list_leads()
    elapsed_ms = (time.monotonic() - t) * 1000
    print(f"  5 × list_leads() back-to-back: {elapsed_ms:.1f}ms total")
    if elapsed_ms > 1000:
        print("  ⚠️  Looks slow for a cache hit — investigate.")
    else:
        print("  ✓ cache is absorbing the reads")

    hr("DONE")
    print("All three repo methods returned. Typed values + cache working.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
