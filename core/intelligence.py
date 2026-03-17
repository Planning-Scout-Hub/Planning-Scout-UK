# core/intelligence.py
# ════════════════════════════════════════════════════════════
# PlanningScout Intelligence Layer
# Static policy context that makes leads smarter than keyword hits.
# Updated: March 2026
# Sources: Natural England, MHCLG Housing Delivery Test 2024
# ════════════════════════════════════════════════════════════

# ── Nutrient Neutrality Catchments ──────────────────────────
# Councils where LPA is required to apply Habitats Regulations
# Assessment. Any planning refusal here may cite nutrient neutrality.
# Source: Natural England catchment authority lists (2024-25)
NUTRIENT_CATCHMENTS = {
    # Solent
    "Winchester":    "Solent",
    "Eastleigh":     "Solent",
    "Fareham":       "Solent",
    "Havant":        "Solent",
    "New Forest":    "Solent",
    "Chichester":    "Solent",
    "Gosport":       "Solent",
    "East Hampshire":"Solent",
    # Wye
    "Herefordshire": "Wye",
    # Somerset Levels
    "Taunton":       "Somerset Levels",
    "Sedgemoor":     "Somerset Levels",
    "Mendip":        "Somerset Levels",
    # Stour and Avon
    "Christchurch":  "Stour/Avon",
    "East Dorset":   "Stour/Avon",
    # Upper Thames
    "Oxford":        "Upper Thames",
    "Vale White Horse": "Upper Thames",
    "South Oxfordshire": "Upper Thames",
    # Poole Harbour
    "Purbeck":       "Poole Harbour",
    "Poole":         "Poole Harbour",
    "Bournemouth":   "Poole Harbour",
}

# ── 5-Year Housing Land Supply Deficit ───────────────────────
# Councils known to be in deficit based on HDT 2024 and local plan 
# examinations. "Open season" for housing appeals under NPPF para 11d.
# Update annually from MHCLG Housing Delivery Test results.
FYHLS_DEFICIT = {
    # Confirmed below 95% HDT threshold (tilted balance applies)
    "Rother":         {"hdt_score": "68%",  "status": "Significant deficit"},
    "Eastbourne":     {"hdt_score": "71%",  "status": "Deficit"},
    "Hastings":       {"hdt_score": "74%",  "status": "Deficit"},
    "Wealden":        {"hdt_score": "78%",  "status": "Deficit"},
    "Sevenoaks":      {"hdt_score": "81%",  "status": "Deficit"},
    "Thanet":         {"hdt_score": "83%",  "status": "Deficit"},
    "Tunbridge Wells":{"hdt_score": "76%",  "status": "Deficit"},
    "Chichester":     {"hdt_score": "69%",  "status": "Significant deficit"},
    "Horsham":        {"hdt_score": "80%",  "status": "Deficit"},
    "Mid Sussex":     {"hdt_score": "82%",  "status": "Deficit"},
    "Waverley":       {"hdt_score": "77%",  "status": "Deficit"},
    "Mole Valley":    {"hdt_score": "73%",  "status": "Deficit"},
    "Runnymede":      {"hdt_score": "79%",  "status": "Deficit"},
}

# ── Grey Belt Vulnerability ───────────────────────────────────
# Councils with significant Green Belt coverage AND known 
# housing pressure. The combination = high grey belt scrutiny.
# Source: DLUHC Green Belt statistics 2023, local plan reviews 2024-25
GREY_BELT_PRESSURE = {
    "Sevenoaks":      "High — 93% Green Belt coverage",
    "Tandridge":      "High — 94% Green Belt coverage",
    "Mole Valley":    "High — Green Belt + housing deficit",
    "Reigate":        "High — Green Belt ring + housing pressure",
    "Epping Forest":  "High — Green Belt + London fringe",
    "Welwyn":         "High — Green Belt + housing pressure",
    "St Albans":      "High — Green Belt + housing pressure",
    "Three Rivers":   "High — Green Belt + housing pressure",
    "Hertsmere":      "High — Green Belt + housing pressure",
    "Guildford":      "High — 88% Green Belt + housing target gap",
    "Waverley":       "Medium-High — Green Belt + deficit",
    "Chiltern":       "High — 83% Green Belt coverage",
    "South Bucks":    "High — 86% Green Belt coverage",
}

# ── BNG High-Risk Zones ───────────────────────────────────────
# Councils where Priority Habitat density is high enough that
# BNG 10% gain is consistently harder to achieve cheaply.
# Source: Natural England Priority Habitat Inventory summary
BNG_HIGH_RISK = {
    "New Forest":     "Priority habitats — ancient woodland, heathland",
    "Chichester":     "Priority habitats — coastal, lowland meadow",
    "Rother":         "Priority habitats — coastal grazing marsh",
    "Wealden":        "Priority habitats — ancient woodland dense",
    "North Devon":    "Priority habitats — blanket bog, coastal",
    "East Devon":     "Priority habitats — coastal, heathland",
    "Cornwall":       "Priority habitats — multiple coastal/heathland",
    "Northumberland": "Priority habitats — moorland, blanket bog",
}


def enrich_lead(lead: dict, council: str) -> dict:
    """
    Add policy intelligence flags to a lead dict before writing to sheet.
    Called by engine.py in process_app(), just before write_lead().
    
    Adds keys: catchment, fyhls_status, grey_belt_pressure, bng_risk
    """
    lead["catchment"]           = NUTRIENT_CATCHMENTS.get(council, "")
    
    fyhls = FYHLS_DEFICIT.get(council, {})
    lead["fyhls_status"]        = fyhls.get("status", "") + f" ({fyhls['hdt_score']})" if fyhls else ""
    
    lead["grey_belt_pressure"]  = GREY_BELT_PRESSURE.get(council, "")
    lead["bng_risk"]            = BNG_HIGH_RISK.get(council, "")
    
    return lead


def intelligence_score_bonus(council: str, triggers_text: str) -> int:
    """
    Returns a score bonus based on council-level policy intelligence.
    Called by engine.py score_lead() in addition to PDF trigger scoring.
    
    Max possible bonus: +25
    """
    bonus = 0
    t = triggers_text.lower()
    
    # BNG refusal + high-risk council = very specific instruction needed
    if council in BNG_HIGH_RISK and "biodiversity net gain" in t:
        bonus += 10
    
    # 5YHLS deficit council = tilted balance makes appeal easier
    if council in FYHLS_DEFICIT:
        bonus += 8
        if "tilted balance" in t or "five year housing land supply" in t:
            bonus += 7  # double signal — council deficit AND decision cites it
    
    # Nutrient neutrality catchment + nutrient trigger = highly specific lead
    if council in NUTRIENT_CATCHMENTS and any(
        w in t for w in ["nutrient", "nitrogen", "phosphorus", "habitats regulations"]
    ):
        bonus += 10
    
    # Grey belt pressure zone + grey belt trigger = premium lead
    if council in GREY_BELT_PRESSURE and "grey belt" in t:
        bonus += 15
    
    return min(bonus, 25)  # cap so it doesn't dominate score
