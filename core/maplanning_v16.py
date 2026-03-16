import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install",
    "requests", "beautifulsoup4", "pdfplumber", "gspread", "google-auth", "-q"])

import requests, re, io, time, urllib3, socket
from datetime import datetime, timedelta
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import gspread
from google.auth import default
from google.oauth2.service_account import Credentials as SACredentials
import os, json
import email_digest
import pdfplumber

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ════════════════════════════════════════════════════════════
# CONFIG
# First run:  WEEKS_TO_SCRAPE = 12  (3 month backfill)
# Weekly run: WEEKS_TO_SCRAPE = 2
# ════════════════════════════════════════════════════════════
SHEET_ID        = "172bpv-b2_nK5ENE1XPk5rWeokvnr1sjHvLBfVzHWh6c"
WEEKS_TO_SCRAPE = 12

# ── Verified Idox portals only ────────────────────────────
# Each URL is tested at startup — dead ones are skipped automatically.
# All use the standard Idox /search.do?action=advanced endpoint.
#
# ── v18 URL audit notes ──────────────────────────────────
# Many councils migrated Idox subdomains. All URLs below are verified
# against live search results (March 2026).
# Non-Idox portals (Northgate, Ocella, Fastweb, Angular SPAs) removed —
# they use different form structures and cannot be scraped by this tool.
# Councils that time-out from GitHub US IPs are kept in the dict —
# they work fine when run from Colab (UK IP routing).
COUNCILS = {
    # ══ West Yorkshire ══════════════════════════════════════════
    "Leeds":             "https://publicaccess.leeds.gov.uk/online-applications",
    "Wakefield":         "https://planning.wakefield.gov.uk/online-applications",
    "Bradford":          "https://planning.bradford.gov.uk/online-applications",
    "Calderdale":        "https://portal.calderdale.gov.uk/online-applications",
    "Kirklees":          "https://www.kirklees.gov.uk/beta/planning-and-building-control/online-applications",

    # ══ Greater Manchester ══════════════════════════════════════
    # All confirmed Idox — ALL require UK IP (blocked from GitHub US).
    # Run from Colab for these. Tameside = where Mark's confirmed leads came from.
    "Tameside":          "https://publicaccess.tameside.gov.uk/online-applications",
    "Manchester":        "https://pa.manchester.gov.uk/online-applications",
    "Salford":           "https://publicaccess.salford.gov.uk/online-applications",
    "Trafford":          "https://pa.trafford.gov.uk/online-applications",
    "Bolton":            "https://www.planningpa.bolton.gov.uk/online-applications-17",
    "Oldham":            "https://online.oldham.gov.uk/online-applications",
    "Bury":              "https://planning.bury.gov.uk/online-applications",
    "Rochdale":          "https://planning.rochdale.gov.uk/online-applications",
    "Wigan":             "https://planning.wigan.gov.uk/online-applications",
    "Stockport":         "https://planning.stockport.gov.uk/online-applications",

    # ══ South Yorkshire ═════════════════════════════════════════
    "Sheffield":         "https://planningapps.sheffield.gov.uk/online-applications",
    "Barnsley":          "https://www.barnsley.gov.uk/online-applications",
    "Doncaster":         "https://planning.doncaster.gov.uk/online-applications",
    # Rotherham: Fastweb portal — not Idox, excluded

    # ══ North/East Yorkshire ════════════════════════════════════
    "York":              "https://www.york.gov.uk/online-applications",
    "East Riding":       "https://www.eastriding.gov.uk/online-applications",
    "Hull":              "https://www.hullcc.gov.uk/online-applications",
    "North Yorkshire":   "https://planning.northyorks.gov.uk/online-applications",

    # ══ North East ══════════════════════════════════════════════
    "Sunderland":        "https://online-applications.sunderland.gov.uk/online-applications",
    "Durham":            "https://publicaccess.durham.gov.uk/online-applications",
    "North Tyneside":    "https://idoxpublicaccess.northtyneside.gov.uk/online-applications",
    "South Tyneside":    "https://www.southtyneside.gov.uk/online-applications",
    "Northumberland":    "https://www.northumberland.gov.uk/online-applications",
    "Middlesbrough":     "https://planning.middlesbrough.gov.uk/online-applications",
    "Darlington":        "https://planning.darlington.gov.uk/online-applications",
    "Stockton":          "https://www.stockton.gov.uk/online-applications",
    "Hartlepool":        "https://eha.hartlepool.gov.uk/online-applications",
    "Redcar":            "https://planning.redcar-cleveland.gov.uk/online-applications",

    # ══ North West ══════════════════════════════════════════════
    "Knowsley":          "https://publicaccess.knowsley.gov.uk/online-applications",
    "Wirral":            "https://planning.wirral.gov.uk/online-applications",
    "Lancaster":         "https://planning.lancaster.gov.uk/online-applications",
    "Blackpool":         "https://idoxpa.blackpool.gov.uk/online-applications",
    "Cheshire West":     "https://pa.cheshirewestandchester.gov.uk/online-applications",
    "Sefton":            "https://pa.sefton.gov.uk/online-applications",
    "St Helens":         "https://pa.sthelens.gov.uk/online-applications",
    "Halton":            "https://pa.halton.gov.uk/online-applications",
    "Burnley":           "https://planning.burnley.gov.uk/online-applications",
    "Pendle":            "https://planning.pendle.gov.uk/online-applications",
    "Chorley":           "https://pa.chorley.gov.uk/online-applications",
    "West Lancashire":   "https://planning.westlancs.gov.uk/online-applications",
    "South Ribble":      "https://planning.southribble.gov.uk/online-applications",
    # Preston: ASP.NET portal — not Idox
    # Warrington: migrated off Idox — not Idox
    # Cheshire East: AdvancedSearch.aspx — not Idox

    # ══ East Midlands ═══════════════════════════════════════════
    "Lincoln":           "https://planning.lincoln.gov.uk/online-applications",
    "Nottingham":        "https://publicaccess.nottinghamcity.gov.uk/online-applications",
    "Derby":             "https://eplanning.derby.gov.uk/online-applications",
    "Northampton":       "https://www.northampton.gov.uk/online-applications",
    "Leicester":         "https://planning.leicester.gov.uk/online-applications",
    "Chesterfield":      "https://planning.chesterfield.gov.uk/online-applications",
    "Peterborough":      "https://planning.peterborough.gov.uk/online-applications",

    # ══ West Midlands ═══════════════════════════════════════════
    "Wolverhampton":     "https://planningonline.wolverhampton.gov.uk/online-applications",
    "Solihull":          "https://publicaccess.solihull.gov.uk/online-applications",
    "Birmingham":        "https://eplanning.birmingham.gov.uk/online-applications",
    "Coventry":          "https://planningapps.coventry.gov.uk/online-applications",
    "Walsall":           "https://planningonline.walsall.gov.uk/online-applications",
    "Dudley":            "https://www.dudley.gov.uk/online-applications",

    # ══ South West ══════════════════════════════════════════════
    "Bristol":           "https://planningonline.bristol.gov.uk/online-applications",
    "Plymouth":          "https://planning.plymouth.gov.uk/online-applications",
    "Exeter":            "https://publicaccess.exeter.gov.uk/online-applications",
    "Cornwall":          "https://planning.cornwall.gov.uk/online-applications",
    "Cheltenham":        "https://publicaccess.cheltenham.gov.uk/online-applications",
    "Gloucester":        "https://publicaccess.gloucester.gov.uk/online-applications",
    "Swindon":           "https://pa.swindon.gov.uk/online-applications",
    "Torbay":            "https://www.torbay.gov.uk/online-applications",
    "Bath":              "https://www.bathnes.gov.uk/online-applications",

    # ══ South East ══════════════════════════════════════════════
    "Portsmouth":        "https://publicaccess.portsmouth.gov.uk/online-applications",
    "Southampton":       "https://planningpublicaccess.southampton.gov.uk/online-applications",
    "Reading":           "https://planning.reading.gov.uk/online-applications",
    "Oxford":            "https://public.oxford.gov.uk/online-applications",
    "Canterbury":        "https://pa.canterbury.gov.uk/online-applications",
    "Maidstone":         "https://pa.maidstone.gov.uk/online-applications",
    "Thanet":            "https://planning.thanet.gov.uk/online-applications",
    "Guildford":         "https://publicaccess.guildford.gov.uk/online-applications",
    "Eastbourne":        "https://planning.eastbourne.gov.uk/online-applications",
    "Worthing":          "https://planning.worthing.gov.uk/online-applications",
    "Brighton":          "https://planningapps.brighton-hove.gov.uk/online-applications",
    "Hastings":          "https://www.hastings.gov.uk/online-applications",
    "Chichester":        "https://publicaccess.chichester.gov.uk/online-applications",
    "Arun":              "https://www.arun.gov.uk/online-applications",
    "Reigate":           "https://idox.reigate-banstead.gov.uk/online-applications",
    "Medway":            "https://pa.medway.gov.uk/online-applications",
    "Swale":             "https://pa.swale.gov.uk/online-applications",
    "Tunbridge Wells":   "https://pa.tunbridgewells.gov.uk/online-applications",
    "Sevenoaks":         "https://pa.sevenoaks.gov.uk/online-applications",
    "Ashford":           "https://www.ashford.gov.uk/online-applications",
    "Dover":             "https://planning.dover.gov.uk/online-applications",
    "Folkestone":        "https://planningpa.folkestone.gov.uk/online-applications",
    "Tonbridge":         "https://www.tmbc.gov.uk/online-applications",
    "Fareham":           "https://planning.fareham.gov.uk/online-applications",
    "Winchester":        "https://www.winchester.gov.uk/online-applications",
    "Eastleigh":         "https://planning.eastleigh.gov.uk/online-applications",
    "New Forest":        "https://www.newforest.gov.uk/online-applications",
    "Test Valley":       "https://www.testvalley.gov.uk/online-applications",
    "Basingstoke":       "https://idoxpa.basingstoke.gov.uk/online-applications",
    "Hart":              "https://www.hart.gov.uk/online-applications",
    "West Berkshire":    "https://publicaccess.westberks.gov.uk/online-applications",
    "South Oxfordshire": "https://www.southoxon.gov.uk/online-applications",
    "Vale White Horse":  "https://www.whitehorsedc.gov.uk/online-applications",
    "Cherwell":          "https://pa.cherwell.gov.uk/online-applications",
    "West Oxfordshire":  "https://www.westoxon.gov.uk/online-applications",
    "Woking":            "https://planning.woking.gov.uk/online-applications",
    "Elmbridge":         "https://www.elmbridge.gov.uk/online-applications",
    "Crawley":           "https://planning.crawley.gov.uk/online-applications",
    "Horsham":           "https://www.horsham.gov.uk/online-applications",
    "Mid Sussex":        "https://www.midsussex.gov.uk/online-applications",
    "Wealden":           "https://www.wealden.gov.uk/online-applications",
    "Rother":            "https://www.rother.gov.uk/online-applications",
    "Runnymede":         "https://idoxpa.runnymede.gov.uk/online-applications",

    # ══ East of England ═════════════════════════════════════════
    "Norfolk (N)":       "https://idoxpa.north-norfolk.gov.uk/online-applications",
    "Norwich":           "https://planning.norwich.gov.uk/online-applications",
    "Cambridge":         "https://applications.greatercambridgeplanning.org/online-applications",
    "Chelmsford":        "https://publicaccess.chelmsford.gov.uk/online-applications",
    "Luton":             "https://planning.luton.gov.uk/online-applications",
    "Braintree":         "https://publicaccess.braintree.gov.uk/online-applications",
    "Basildon":          "https://planning.basildon.gov.uk/online-applications",
    "Tendring":          "https://idox.tendringdc.gov.uk/online-applications",
    "Ipswich":           "https://ppc.ipswich.gov.uk/online-applications",
    "Colchester":        "https://www.colchester.gov.uk/online-applications",
    "East Suffolk":      "https://www.eastsuffolk.gov.uk/online-applications",
    "West Suffolk":      "https://westsuffolk.gov.uk/online-applications",
    "Great Yarmouth":    "https://planning.great-yarmouth.gov.uk/online-applications",
    "Breckland":         "https://planning.breckland.gov.uk/online-applications",
    "South Norfolk":     "https://planning.south-norfolk.gov.uk/online-applications",
    "St Albans":         "https://planningregister.stalbans.gov.uk/online-applications",
    "Watford":           "https://planning.watford.gov.uk/online-applications",
    "Hertsmere":         "https://www6.hertsmere.gov.uk/online-applications",
    "Three Rivers":      "https://www.threerivers.gov.uk/online-applications",
    "East Herts":        "https://www.eastherts.gov.uk/online-applications",
    "Stevenage":         "https://publicaccess.stevenage.gov.uk/online-applications",
    "North Herts":       "https://www.north-herts.gov.uk/online-applications",
    "Huntingdonshire":   "https://publicaccess.huntingdonshire.gov.uk/online-applications",

    # ══ North East (add alongside Sunderland, Durham, etc.) ══════════
"Newcastle":         "https://publicaccess.newcastle.gov.uk/online-applications",
"Gateshead":         "https://planning.gateshead.gov.uk/online-applications",

# ══ West Midlands (add alongside Birmingham, Coventry, etc.) ═════
"Sandwell":          "https://www.sandwell.gov.uk/online-applications",
"Stoke-on-Trent":    "https://www.stoke.gov.uk/online-applications",
"Tamworth":          "https://www.tamworth.gov.uk/online-applications",

# ══ East Midlands (add alongside Nottingham, Derby, etc.) ════════
"Gedling":           "https://www.gedling.gov.uk/online-applications",
"Broxtowe":          "https://www.broxtowe.gov.uk/online-applications",
"Mansfield":         "https://www.mansfield.gov.uk/online-applications",
"Rushcliffe":        "https://planningon.rushcliffe.gov.uk/online-applications",
"Newark":            "https://www.newark-sherwooddc.gov.uk/online-applications",

# ══ East of England (add alongside Chelmsford, Braintree, etc.) ══
"Brentwood":         "https://www.brentwood.gov.uk/online-applications",
"Epping Forest":     "https://www.eppingforestdc.gov.uk/online-applications",

# ══ London ═══════════════════════════════════════════════════════
"Barking Dagenham":  "https://paplan.lbbd.gov.uk/online-applications",

    # ══ London (Idox portals only) ════════════════════════════
    # Non-Idox: Hackney, Waltham Forest, Harrow, Havering, Hillingdon,
    #           Hounslow, Merton, Redbridge, Wandsworth, Haringey, Camden, Richmond
    "Ealing":            "https://pam.ealing.gov.uk/online-applications",
    "Lewisham":          "https://planning.lewisham.gov.uk/online-applications",
    "Lambeth":           "https://planning.lambeth.gov.uk/online-applications",
    "Croydon":           "https://publicaccess3.croydon.gov.uk/online-applications",
    "Brent":             "https://pa.brent.gov.uk/online-applications",
    "Tower Hamlets":     "https://development.towerhamlets.gov.uk/online-applications",
    "Greenwich":         "https://planning.royalgreenwich.gov.uk/online-applications",
    "Newham":            "https://pa.newham.gov.uk/online-applications",
    "Bexley":            "https://pa.bexley.gov.uk/online-applications",
    "Kingston":          "https://publicaccess.kingston.gov.uk/online-applications",
    "Sutton":            "https://planningregister.sutton.gov.uk/online-applications",
    "Westminster":       "https://idoxpa.westminster.gov.uk/online-applications",
    "Southwark":         "https://planning.southwark.gov.uk/online-applications",
    "Barnet":            "https://publicaccess.barnet.gov.uk/online-applications",
    "Enfield":           "https://planningandbuildingcontrol.enfield.gov.uk/online-applications",
    "Bromley":           "https://searchapplications.bromley.gov.uk/online-applications",
    "Hammersmith":       "https://public-access.lbhf.gov.uk/online-applications",
    "City of London":    "https://www.planning2.cityoflondon.gov.uk/online-applications",
    "Islington":         "https://publicaccess.islington.gov.uk/online-applications",
    # ══ North West (additions) ══════════════════════════════════════
    "Wyre":              "https://planning.wyre.gov.uk/online-applications",
    "Fylde":             "https://www.fylde.gov.uk/online-applications",
    "Rossendale":        "https://planning.rossendale.gov.uk/online-applications",
    "Hyndburn":          "https://planning.hyndburn.gov.uk/online-applications",
    "Ribble Valley":     "https://www.ribblevalley.gov.uk/online-applications",

    # ══ East Midlands (additions) ════════════════════════════════════
    "Erewash":           "https://www.erewash.gov.uk/online-applications",
    "Amber Valley":      "https://www.ambervalley.gov.uk/online-applications",
    "South Derbyshire":  "https://www.south-derbys.gov.uk/online-applications",
    "Blaby":             "https://www.blaby.gov.uk/online-applications",
    "Hinckley Bosworth": "https://www.hinckley-bosworth.gov.uk/online-applications",
    "Harborough":        "https://www.harborough.gov.uk/online-applications",

    # ══ West Midlands (additions) ════════════════════════════════════
    "Lichfield":         "https://www.lichfielddc.gov.uk/online-applications",
    "Cannock Chase":     "https://www.cannockchasedc.gov.uk/online-applications",
    "East Staffordshire":"https://www.eaststaffsbc.gov.uk/online-applications",

    # ══ South East (additions) ═══════════════════════════════════════
    "Waverley":          "https://planning.waverley.gov.uk/online-applications",
    "Mole Valley":       "https://www.molevalley.gov.uk/online-applications",
    "Surrey Heath":      "https://www.surreyheath.gov.uk/online-applications",
    "Epsom Ewell":       "https://www.epsom-ewell.gov.uk/online-applications",
    "Spelthorne":        "https://www.spelthorne.gov.uk/online-applications",

    # ══ South West (additions) ═══════════════════════════════════════
    "North Devon":       "https://www.northdevon.gov.uk/online-applications",
    "East Devon":        "https://planning.eastdevon.gov.uk/online-applications",
    "Mid Devon":         "https://planning.middevon.gov.uk/online-applications",
    "Teignbridge":       "https://www.teignbridge.gov.uk/online-applications",

    # ══ East of England (additions) ══════════════════════════════════
    "Broadland":         "https://www.broadland.gov.uk/online-applications",
    "Kings Lynn":        "https://www.west-norfolk.gov.uk/online-applications",
    "Fenland":           "https://www.fenland.gov.uk/online-applications",
}

# ── Search keywords — what goes into the portal's description field ──────────
# Goal: catch any Class E change-of-use refused for out-of-centre location.
# Mark's insight: the best leads are small change-of-use applications (easy to
# win on appeal) where refusal was "lack of evidence" / sequential test failure.
# NOT just supermarkets — gyms, salons, cafes, offices all fall under Class E.
RETAIL_KEYWORDS = [
    # ── Core Class E use class terms ─────────────────────────────────────
    "Class E",          # the main use class umbrella
    "change of use",    # CoU apps say "change of use to Class E"
    "use class e",      # alternative phrasing

    # ── Traditional retail ───────────────────────────────────────────────
    "shop",             # A1/Class E retail unit
    "retail",           # retail-specific applications
    "supermarket",      # large format food retail
    "convenience",      # convenience stores
    "food store",       # food retail (alternative to supermarket)
    "discount store",   # Aldi/Lidl type retail

    # ── Food & beverage (Class E) ────────────────────────────────────────
    "café", "cafe",     # cafes — Class E
    "restaurant",       # restaurants — Class E
    "hot food",         # hot food takeaway — Class E boundary
    "takeaway",         # hot food takeaway
    "coffee shop",      # coffee shops e.g. Costa

    # ── Health & fitness / personal services (Class E) ───────────────────
    "gym",              # health & fitness — Class E(d)
    "fitness",          # fitness studio / health club
    "hair",             # hair salons — Class E
    "beauty",           # beauty salons — Class E
    "nail",             # nail bars — Class E
    "barber",           # barbers — Class E
    "health centre",    # health / medical — Class E(e)
    "clinic",           # GP / dental / medical clinic

    # ── Office / workspace (Class E) ─────────────────────────────────────
    "office",           # offices — Class E(g)(i)
    "workspace",        # co-working/flex workspace

    # ── Other relevant types ─────────────────────────────────────────────
    "sui generis",      # uses outside a class — sequential test often needed
    "betting",          # betting shops — sui generis, out-of-centre issues
    "amusement",        # amusement centres — sui generis
    "car wash",         # car washes often refused for sequential test

    # ── Additional Class E / mixed use terms ─────────────────────
    "mixed use",        # common in retail-led mixed use schemes
    "pharmacy",         # Class E(e) health — often refused out-of-centre
    "optician",         # Class E — common CoU application type
    "drive-through",    # Class E boundary, sequential test almost always required
    "drive through",    # alternative spelling (both needed)
    "food and drink",   # F&B use class grouping in many officer reports
]

# ── PDF trigger words — searched inside the Decision Notice PDF ──────────────
# A lead only qualifies if the PDF contains at least one of these.
# Mark's priority tags (confirmed from real qualified leads):
#   "out of centre" / "out-of-centre"  — location issue, classic appeal ground
#   "edge of centre"                   — borderline location, often winnable
#   "sequential test"                  — applicant didn't prove no sequentially
#                                        preferable sites exist
#   "sequential approach"              — same issue, different wording
#   "retail impact assessment"         — impact not properly assessed
#   "lack of evidence"                 — MOST WINNABLE: council refused because
#                                        applicant didn't submit a document.
#                                        Easy fix on appeal = high value lead.
PDF_TRIGGERS = [
    # ════════════════════════════════════════════════════════════════════
    # MARK'S CONFIRMED GOOD SIGNALS ONLY — v19
    #
    # REMOVED (were causing noise — these appear as boilerplate in every
    # retail decision notice, not actual refusal grounds):
    #   ✗ "nppf" / "national planning policy framework"
    #   ✗ "main town centre" / "main town centre use"
    #   ✗ "primary shopping area" / "primary shopping" / "primary retail"
    #   ✗ "town centre first" / "town centre boundary"
    #   ✗ "impact assessment" (generic — keep only "retail impact assessment")
    #   ✗ "retail impact" (too broad alone)
    #   ✗ "vitality and viability" (appears in every retail refusal boilerplate)
    #   ✗ Use class references (class e(a), etc — not refusal grounds)
    #   ✗ "out of town" / "not in a town centre" (weaker variants)
    #
    # KEPT (specific refusal grounds Mark identified as winnable):
    # ════════════════════════════════════════════════════════════════════

    # ── 1. OUT-OF-CENTRE LOCATION ────────────────────────────────────────
    # Core appeal ground. Mark's explicit #1 signal.
    "out of centre",
    "out-of-centre",
    "outside the town centre",
    "outside a defined centre",
    "edge of centre",
    "edge-of-centre",
    "edge of the town centre",

    # ── 2. SEQUENTIAL TEST FAILURE ───────────────────────────────────────
    # Applicant failed to prove no sequentially preferable town centre
    # sites exist. Always the core planning appeal ground.
    # NOTE: "sequential" standalone IS included — Mark's confirmed lead
    # 25/00622/FUL was found via this exact word in the decision notice.
    # In planning refusals, "sequential" ONLY refers to the NPPF sequential
    # approach — it is never ambiguous or generic in this context.
    "sequential",
    "sequential test",
    "sequential approach",
    "sequential assessment",
    "sequential preference",
    "sequential search",
    "sequential step",
    "no sequential",
    "fails the sequential",
    "failed the sequential",
    "fail the sequential",
    "sequentially preferable",

    # ── 3. LACK OF EVIDENCE / FAILURE TO DEMONSTRATE ────────────────────
    # MARK'S MOST WINNABLE CATEGORY: council refused because applicant
    # simply didn't submit a required document. Easy fix on appeal.
    "lack of evidence",
    "insufficient evidence",
    "no evidence",
    "lack of information",
    "insufficient information",
    "failure to demonstrate",
    "failed to demonstrate",
    "fails to demonstrate",
    "not demonstrated",
    "has not demonstrated",
    "cannot demonstrate",
    "unable to demonstrate",
    "no information provided",
    "no assessment",
    "has not been submitted",
    "not been submitted",
    "not been provided",
    "has not been provided",
    "was not submitted",
    "absence of",
    "in the absence of",

    # ── 4. RETAIL IMPACT ASSESSMENT ──────────────────────────────────────
    # Specific: applicant failed to provide a Retail Impact Assessment.
    # "retail impact" alone NOT included — too often just a policy mention.
    "retail impact assessment",
    "retail impact study",

    # ── 5. SPECIFIC TOWN CENTRE HARM FINDINGS ────────────────────────────
    # Only the specific harm findings — NOT generic "vitality and viability"
    # which appears in every retail refusal as boilerplate policy citation.
    "harm to the vitality and viability",
    "harm to the vitality",
    "adverse impact on the vitality",
    "undermine the vitality",
    "prejudice the vitality",

        # ── 6. NO IDENTIFIED NEED / NEED NOT DEMONSTRATED ────────────────────
    # MARK'S "LACK OF EVIDENCE" FAMILY — extended.
    # These are refusals where the council says the applicant didn't prove
    # there is a need for the use in that location. Identical appeal ground
    # to "lack of evidence" — easy to address on resubmission or appeal.
    "no identified need",
    "no quantitative need",
    "no qualitative need",
    "need has not been",
    "need has not been demonstrated",
    "no overriding need",
    "need not been established",
    "unmet need",
    "no need has been",
    "insufficient justification",
    "failed to justify",
    "fails to justify",
    "not justified",
]

# ── Minimum lead score to write to sheet ─────────────────────────────────────
# Safety net: any lead scoring below this is discarded even if it matched a
# trigger. Prevents edge-case noise. Genuine leads score 60+ because they
# need at least one strong trigger (evidence +25, sequential +20,
# out-of-centre +15) plus a use class description signal (+8).
# Score-48 rows (old "only NPPF" junk) can no longer reach this threshold.
MIN_LEAD_SCORE = 60

HEADERS_HTTP = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# ── Per-council rate limit tracker ───────────────────────────────────────────
# When a council returns HTTP 429, record when the ban expires.
# search_one_keyword checks this before each keyword — if the council is still
# rate-limited, it skips immediately instead of wasting time on doomed requests.
_rate_limited_until = {}   # base_url -> datetime when ban expires

# ════════════════════════════════════════════════════════════
# LOGGING
# ════════════════════════════════════════════════════════════
def log(msg, i=0):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {'  '*i}{msg}", flush=True)

# ════════════════════════════════════════════════════════════
# SESSION
# ════════════════════════════════════════════════════════════
def new_session():
    s = requests.Session()
    s.headers.update(HEADERS_HTTP)
    s.verify = False
    return s

def _is_dns_error(e):
    """True if the error is a DNS resolution failure — pointless to retry."""
    msg = str(e)
    return any(x in msg for x in [
        "NameResolutionError", "Name or service not known",
        "nodename nor servname", "getaddrinfo failed",
        "[Errno -2]", "[Errno 11001]",
    ])

def safe_get(sess, url, timeout=25, retries=2):
    for attempt in range(retries):
        try:
            # These two lines MUST have the same number of spaces (12 spaces)
            r = sess.get(url, timeout=timeout, allow_redirects=True)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 90))
                log(f"  🚫 429 on GET — marking {url[:50]} blocked for {wait}s", 2)
                _rate_limited_until[url.split("/online-applications")[0] + "/online-applications"] = \
                    datetime.now() + timedelta(seconds=wait)
            return r
        except requests.exceptions.ConnectionError as e:
            if _is_dns_error(e):
                # DNS won't fix itself on retry — fail immediately
                log(f"  ❌ DNS failure (dead URL): {url[:70]}", 2)
                return None
            if attempt < retries - 1:
                time.sleep(4)
            else:
                log(f"  ❌ GET failed: {e}", 2)
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                log(f"  ⏱️  Timeout, retry {attempt+2}...", 2)
                time.sleep(5)
            else:
                log(f"  ❌ Timeout after {retries} attempts: {url[:60]}", 2)
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(4)
            else:
                log(f"  ❌ GET failed: {e}", 2)
    return None

# ════════════════════════════════════════════════════════════
# PRE-FLIGHT: test every council URL before scraping
# ════════════════════════════════════════════════════════════
def preflight_check(councils):
    """
    Single-attempt check per council. Classifies results into three buckets:

      ok          → responds from current IP, include in this run
      geo_blocked → ConnErr or Timeout from GitHub US IPs; confirmed Idox portals
                    that require a UK IP address. INCLUDED in the scrape run —
                    the scraper will try them and skip gracefully if they fail.
                    Run from Colab (UK IP) to get 100% coverage from these.
      dead        → DNS failure or no Idox form detected — genuinely gone, skip.

    Why this matters: previously ConnErr/Timeout both went into dead{} and were
    SKIPPED. ~20 valid councils were silently dropped on every GitHub Actions run.
    Now they are included and will either work (from Colab) or fail gracefully.
    """
    import concurrent.futures
    log("\n🔍 PRE-FLIGHT  (single-attempt, parallel)")
    log("=" * 60)
    live        = {}
    geo_blocked = {}  # ConnErr/Timeout — include in scrape, log separately
    dead        = {}  # DNS / no_form — genuinely skip

    def _test(name_url):
        name, base_url = name_url
        test_url = f"{base_url}/search.do?action=advanced&searchType=Application"
        headers_variants = [
            None,
            {"Accept": "text/html,*/*;q=0.9", "Accept-Language": "en-GB,en;q=0.5"},
        ]
        for extra_headers in headers_variants:
            try:
                sess = new_session()
                if extra_headers:
                    sess.headers.update(extra_headers)
                r = sess.get(test_url, timeout=15, allow_redirects=True, verify=False)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "html.parser")
                    text_lower = r.text.lower()
                    has_search_form = bool(
                        soup.find("input", {"name": re.compile(r"description|caseDecision|keyWord", re.I)})
                        or soup.find("form", {"id": re.compile(r"search|criteria", re.I)})
                        or soup.find("select", {"name": re.compile(r"caseDecision|decision|status", re.I)})
                    )
                    is_disclaimer = any(kw in text_lower for kw in (
                        "disclaimer", "terms and conditions", "accept", "cookies",
                        "i accept", "agree to", "before you continue"
                    ))
                    is_idox = any(kw in text_lower for kw in (
                        "planning application", "search.do", "idox",
                        "application reference", "applicationdetails",
                        "online-applications", "keyval"
                    ))
                    if has_search_form or (is_disclaimer and is_idox):
                        return name, base_url, "ok", r.status_code
                    if soup.find("form") and is_idox:
                        return name, base_url, "ok", r.status_code
                    return name, base_url, "no_form", r.status_code
                if r.status_code == 406 and extra_headers is None:
                    continue
                return name, base_url, "bad_status", r.status_code
            except requests.exceptions.ConnectionError as e:
                if _is_dns_error(e):
                    return name, base_url, "DNS", 0
                # Non-DNS ConnErr = geo-IP block. Do NOT skip — include in scrape.
                return name, base_url, "geo_blocked", 0
            except requests.exceptions.Timeout:
                # Timeout from GitHub US almost always = geo-IP block, not a dead server.
                return name, base_url, "geo_blocked", 0
            except Exception as e:
                return name, base_url, f"Err:{type(e).__name__}", 0
        return name, base_url, "bad_status", 406

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_test, item): item[0] for item in councils.items()}
        for fut in concurrent.futures.as_completed(futures):
            name, base_url, status, code = fut.result()
            if status == "ok":
                live[name] = base_url
                log(f"  ✅ {name:25s} reachable")
            elif status == "geo_blocked":
                geo_blocked[name] = base_url
                log(f"  🌍 {name:25s} geo-blocked (included — use Colab for full coverage)")
            else:
                reason = f"HTTP {code}" if code else status
                dead[name] = reason
                log(f"  ❌ {name:25s} {reason} — skipping")

    # Include geo_blocked in the live set — scrape_council will skip gracefully if still blocked
    combined_live = {**dict(sorted(live.items())), **dict(sorted(geo_blocked.items()))}

    log(f"\n  ✅ {len(live):3d} directly reachable")
    log(f"  🌍 {len(geo_blocked):3d} geo-blocked from this IP (included, try Colab for these)")
    log(f"  ❌ {len(dead):3d} truly dead (DNS / no Idox form)")
    log(f"  ─── Scraping {len(combined_live)} councils total")
    log("=" * 60)
    return combined_live, dead

# ════════════════════════════════════════════════════════════
# GOOGLE SHEETS — with retry + in-memory dedup cache
# ════════════════════════════════════════════════════════════
SHEET_HEADERS = [
    "Council", "Reference", "Address", "Description", "App Type",
    "Applicant", "Agent", "Date Received", "Date Decided", "Decision",
    "Trigger Words", "Score", "Keyword", "Portal Link", "Decision Doc URL",
    "Date Found", "Mark's Comments",
    # ── Sales Intelligence (added v16) ──
    "Est. Project Value", "Developer", "Architect",
    "Impact Probability", "CH Number", "Registered Address", "Contact Link",
]

_ws           = None   # cached worksheet
_existing_refs = set() # in-memory dedup — loaded once at startup

def sheets_retry(fn, retries=5, base_delay=10):
    """Exponential backoff for transient Google API errors (500/503/quota)."""
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            transient = any(code in msg for code in [
                "500", "503", "quota", "rate", "UNAVAILABLE",
                "internal", "temporarily", "overloaded",
            ])
            if transient and attempt < retries - 1:
                delay = base_delay * (2 ** attempt)  # 10s, 20s, 40s, 80s, 160s
                log(f"  ⚠️  Sheets API error (attempt {attempt+1}/{retries}): {msg[:55]}")
                log(f"  ⏳ Waiting {delay}s...")
                time.sleep(delay)
            else:
                raise

def _make_gspread_client():
    """
    Returns an authorised gspread client.
    - GitHub Actions / automated: reads GCP_SERVICE_ACCOUNT_JSON env var.
    - Google Colab interactive:   uses google.colab.auth + default().
    """
    sa_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON", "").strip()
    if sa_json:
        info  = json.loads(sa_json)
        creds = SACredentials.from_service_account_info(info, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ])
        log("✅ Auth via service account (automated mode)")
        return gspread.authorize(creds)
    else:
        creds, _ = default()
        log("✅ Auth via Colab default credentials")
        return gspread.authorize(creds)


def get_sheet():
    global _ws
    if _ws:
        return _ws
    try:
        def _connect():
            gc_client = _make_gspread_client()
            ws = gc_client.open_by_key(SHEET_ID).worksheet("Leads")
            existing = ws.row_values(1)
            if existing != SHEET_HEADERS:
                ws.update(values=[SHEET_HEADERS], range_name="A1")
                log("✅ Headers written")
            else:
                log("✅ Sheets connected")
            return ws
        _ws = sheets_retry(_connect)
        return _ws
    except Exception as e:
        log(f"❌ Sheets connect failed after retries: {e}")
        return None

def load_existing_refs():
    """
    Load all existing reference numbers from column B into memory.
    Called once at startup — avoids per-lead API calls for dedup.
    """
    global _existing_refs
    ws = get_sheet()
    if not ws:
        return
    try:
        refs = sheets_retry(lambda: ws.col_values(2))
        _existing_refs = set(refs[1:])  # skip header row
        log(f"✅ Loaded {len(_existing_refs)} existing refs (dedup cache)")
    except Exception as e:
        log(f"⚠️  Could not load existing refs: {e} — duplicate check may miss some")

def get_weekly_lead_count():
    """
    Count how many leads were added to the sheet in the past 7 days.
    Reads the "Date Found" column (column 16) and counts rows where
    the date is within the last 7 days.

    This is included in the email digest even when the current run
    finds 0 new leads — so the email is always meaningful.
    """
    ws = get_sheet()
    if not ws:
        return 0, []
    try:
        # Get all rows including Date Found (col 16) and key fields
        all_rows = sheets_retry(lambda: ws.get_all_values())
        if len(all_rows) < 2:
            return 0, []

        cutoff = datetime.now() - timedelta(days=7)
        weekly_leads = []

        for row in all_rows[1:]:  # skip header
            if len(row) < 16:
                continue
            date_found_str = row[15].strip()  # column P = index 15 = "Date Found"
            if not date_found_str:
                continue
            try:
                # Handles both "2026-03-10 14:22" and "2026-03-10" formats
                date_found = datetime.strptime(date_found_str[:10], "%Y-%m-%d")
                if date_found >= cutoff:
                    weekly_leads.append({
                        "council": row[0] if row else "",
                        "ref":     row[1] if len(row) > 1 else "",
                        "desc":    row[3][:80] if len(row) > 3 else "",
                        "score":   row[11] if len(row) > 11 else "",
                        "date":    date_found_str,
                    })
            except Exception:
                continue

        log(f"✅ {len(weekly_leads)} leads added in the past 7 days (from sheet)")
        return len(weekly_leads), weekly_leads

    except Exception as e:
        log(f"⚠️  Could not read weekly leads from sheet: {e}")
        return 0, []

def write_lead(lead):
    ws = get_sheet()
    if not ws:
        return False

    # Fast in-memory dedup check
    if lead["ref"] in _existing_refs:
        log(f"  ⏭️  Duplicate: {lead['ref']}")
        return False

    row_data = [
        lead["council"], lead["ref"], lead["addr"], lead["desc"],
        lead["app_type"], lead["applicant"], lead["agent"],
        lead["date_rec"], lead["date_dec"], lead.get("decision", "REFUSED"),
        lead["triggers"], lead["score"], lead["keyword"],
        lead["url"], lead["doc_url"],
        datetime.now().strftime("%Y-%m-%d %H:%M"), "",
        # Sales intelligence columns
        lead.get("est_value",""),
        lead.get("developer",""),
        lead.get("architect",""),
        str(lead.get("impact_prob","")) + "%" if lead.get("impact_prob") else "",
        lead.get("ch_number",""),
        lead.get("reg_address",""),
        lead.get("contact_link",""),
    ]

    try:
        # Use lambda here to match your retry logic
        sheets_retry(lambda: ws.append_row(row_data))
        _existing_refs.add(lead["ref"]) 

        try:
            all_rows   = sheets_retry(lambda: ws.get_all_values())
            row_num    = len(all_rows)
            dec        = lead.get("decision", "").upper()
            is_refused = dec == "REFUSED" or dec.startswith("REFUSED")
            r, g, b    = (0.85, 0.93, 0.85) if is_refused else (0.96, 0.80, 0.80)
            
            fmt_body = {
                "requests": [{
                    "repeatCell": {
                        "range": {
                            "sheetId": ws.id,
                            "startRowIndex": row_num - 1,
                            "endRowIndex":   row_num,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {"red": r, "green": g, "blue": b}
                            }
                        },
                        "fields": "userEnteredFormat.backgroundColor",
                    }
                }]
            }
            sheets_retry(lambda: ws.spreadsheet.batch_update(fmt_body))
        except Exception:
            pass 

        log(f"  💾 SAVED: {lead['ref']} | {lead['triggers'][:50]}")
        return True
    except Exception as e:
        log(f"  ❌ Sheets write failed after retries: {e}")
        return False

# ════════════════════════════════════════════════════════════
# SCORING
# ════════════════════════════════════════════════════════════
def score_lead(desc, triggers):
    """
    Score a qualified lead 0-100 based on how likely it is to be a
    winnable appeal case that Mark can act on.

    Scoring philosophy (from Mark's feedback):
      - "Lack of evidence" refusals = highest value (easy to win on appeal)
      - Out-of-centre + sequential test failure = strong signal
      - Class E change of use = the target application type
      - Small single-use apps are MORE winnable than large retail parks
      - sqm size is NOT a quality signal — small salons/gyms score just as well
    """
    s  = 40   # base
    d  = desc.lower()
    tw = " ".join(triggers).lower()

    # ── "Lack of evidence" family — most winnable refusal type ──────────
    _evidence_phrases = (
        "lack of evidence", "insufficient evidence", "no evidence",
        "lack of information", "insufficient information",
        "failure to demonstrate", "failed to demonstrate", "fails to demonstrate",
        "not demonstrated", "has not demonstrated", "cannot demonstrate",
        "unable to demonstrate",
        "no information", "no assessment", "no retail impact",
        "has not been submitted", "not been provided", "has not been provided",
        "was not submitted", "not been submitted",
        "absence of", "in the absence of",
        # ── New: need family (same scoring tier) ──────────────────
        "no identified need", "no quantitative need", "no qualitative need",
        "need has not been demonstrated", "no overriding need",
        "insufficient justification", "failed to justify", "not justified",
    )
    for w in _evidence_phrases:
        if w in tw:
            s += 25   # massive bonus — Mark explicitly called these out
            break     # only count once

    # ── Sequential test failure — core NPPF appeal ground ──────────────
    _seq_phrases = (
        "sequential test", "sequential approach", "sequential assessment",
        "sequential preference", "sequential search", "sequential step",
        "sequentially preferable", "sequentially preferred",
        "fail the sequential", "failed the sequential", "fails the sequential",
    )
    for w in _seq_phrases:
        if w in tw:
            s += 20
            break
    if "no sequential" in tw: s += 15

    # ── Out-of-centre location ───────────────────────────────────────────
    _outofcentre = (
        "out of centre", "out-of-centre", "outside the town centre",
        "outside a defined centre", "out of town", "out-of-town",
        "not within the town centre", "not in a town centre",
    )
    for w in _outofcentre:
        if w in tw:
            s += 15
            break
    _edgeofcentre = (
        "edge of centre", "edge-of-centre",
        "edge of the town centre",
    )
    for w in _edgeofcentre:
        if w in tw:
            s += 10
            break

    # ── Retail impact not assessed ───────────────────────────────────────
    if "retail impact assessment" in tw or "retail impact study" in tw: s += 15
    elif "retail impact"          in tw:                                 s += 10
    elif "impact assessment"      in tw:                                 s += 8
    for w in ("impact on the vitality", "impact on vitality",
              "impact on the viability", "impact on viability",
              "harm to the vitality", "harm to vitality",
              "adverse impact on the town centre"):
        if w in tw:
            s += 8
            break

    # ── Vitality & viability ─────────────────────────────────────────────
    for w in ("vitality and viability", "vitality or viability",
              "health of the town centre", "undermine the vitality",
              "prejudice the vitality"):
        if w in tw:
            s += 5
            break

    # ── Description signals — use type ──────────────────────────────────
    if "class e"        in d: s += 10
    if "use class e"    in d: s += 10
    if "change of use"  in d: s += 8

    # Specific Class E sub-types Mark mentioned as good leads
    for w in ("gym", "fitness", "hair", "beauty", "salon",
              "nail", "barber", "café", "cafe", "coffee",
              "restaurant", "hot food", "takeaway", "office", "clinic"):
        if w in d:
            s += 5
            break

    # Traditional retail — valuable but not prioritised over small CoU
    if "supermarket"  in d: s += 8
    if "food store"   in d: s += 8
    if "retail park"  in d: s += 5
    if "convenience"  in d: s += 5
    if "shop"         in d: s += 3

    # ── Penalise non-lead application types ──────────────────────────────
    # Mark explicitly: discharge of conditions / reserved matters = NOT leads
    for bad in (
        "discharge of condition", "discharge of planning condition",
        "reserved matters", "approval of details", "condition discharge",
        "details reserved by condition", "approval of reserved",
        "prior approval", "lawful development certificate",
        "certificate of lawful",
    ):
        if bad in d:
            s -= 60   # always results in score below 10 minimum
            break

    return max(10, min(s, 100))

# ════════════════════════════════════════════════════════════
# SALES INTELLIGENCE ENRICHMENT
# ════════════════════════════════════════════════════════════

# Build rate per sqm by use type (conservative UK estimates, £/sqm)
_BUILD_RATES = {
    "supermarket":    1800,
    "food store":     1800,
    "retail park":    1200,
    "retail":         1100,
    "class e":        1000,
    "mixed use":      1400,
    "restaurant":     1600,
    "convenience":    1100,
    "comparison":     1000,
    "shop":           1000,
}
_LONDON_BOROUGHS = {
    "westminster","camden","southwark","ealing","islington","hackney",
    "lewisham","lambeth","newham","croydon","barnet","enfield","brent",
    "tower hamlets","greenwich","waltham forest","wandsworth","haringey",
}

def estimate_project_value(desc, council, triggers):
    """
    Estimate construction value from:
    1. Floor area (sqm) × build rate per use type
    2. If no sqm found, use keyword-based banding
    Returns a string like "£2.1m–£3.4m" or "£500k–£1m"
    """
    d   = desc.lower()
    loc = council.lower()
    london_premium = 1.35 if any(b in loc for b in _LONDON_BOROUGHS) else 1.0

    # Detect build rate
    rate = 1000  # default
    for kw, r in _BUILD_RATES.items():
        if kw in d:
            rate = r
            break

    rate = int(rate * london_premium)

    # Try to find sqm
    sqm_match = re.findall(
        r'(\d[\d,]*)\s*(?:sq\.?\s*m(?:etres?)?|sqm|m2|square\s+metre)', d
    )
    if sqm_match:
        try:
            sqm = int(sqm_match[0].replace(",",""))
            lo  = sqm * rate
            hi  = sqm * int(rate * 1.3)
            return _fmt_value(lo), _fmt_value(hi)
        except Exception:
            pass

    # No sqm — band by keywords
    if any(w in d for w in ["major","superstore","supermarket","retail park","district centre"]):
        lo, hi = 3_000_000, 15_000_000
    elif any(w in d for w in ["food store","convenience","large format"]):
        lo, hi = 1_000_000, 5_000_000
    elif any(w in d for w in ["retail","class e","shop","commercial"]):
        lo, hi = 250_000, 1_500_000
    else:
        lo, hi = 150_000, 750_000

    lo = int(lo * london_premium)
    hi = int(hi * london_premium)
    return _fmt_value(lo), _fmt_value(hi)

def _fmt_value(n):
    if n >= 1_000_000:
        return f"£{n/1_000_000:.1f}m"
    return f"£{n//1000}k"

def impact_probability(desc, triggers, score):
    """
    0–100 probability that this project needs a formal retail impact study.
    Based on NPPF threshold indicators and trigger word strength.
    """
    d  = desc.lower()
    tw = " ".join(triggers).lower() if triggers else ""
    p  = 40  # base

    # Size indicators (main NPPF trigger: >2500 sqm needs full RIA)
    sqm_m = re.findall(r'(\d[\d,]*)\s*(?:sq\.?\s*m|sqm|m2)', d)
    if sqm_m:
        try:
            sqm = int(sqm_m[0].replace(",",""))
            if sqm >= 2500: p += 40
            elif sqm >= 1000: p += 25
            elif sqm >= 500:  p += 10
        except Exception:
            pass

    # Use type
    for kw, pts in [("supermarket",25),("food store",25),("retail park",20),
                    ("out of centre",20),("out-of-centre",20),
                    ("major",10),("district centre",10)]:
        if kw in d: p += pts

    # Trigger words confirm retail policy engagement
    if "sequential test"   in tw: p += 15
    if "retail impact"     in tw: p += 15
    if "impact assessment" in tw: p += 10
    if "main town centre"  in tw: p += 5
    if "primary shopping"  in tw: p += 5

    # High score = more complex = more likely to need study
    p += (score - 50) // 5

    return min(p, 98)  # never show 100% — leaves room for nuance

_CH_CACHE = {}  # avoid re-querying same company name

def lookup_companies_house(name):
    """
    Free Companies House API — no key required.
    Returns dict with: ch_number, reg_address, contact_link
    """
    if not name or len(name) < 4:
        return {}
    key = name.strip().lower()
    if key in _CH_CACHE:
        return _CH_CACHE[key]

    # Strip common suffixes to improve match quality
    clean = re.sub(
        r'(ltd|limited|plc|llp|llc|group|holdings|properties|developments?|'
        r'architects?|associates?|consulting|consultants?|design)',
        "", name, flags=re.I
    ).strip(" .,")
    if len(clean) < 3:
        clean = name

    try:
        url  = f"https://api.company-information.service.gov.uk/search/companies?q={requests.utils.quote(clean)}&items_per_page=3"
        resp = requests.get(url, timeout=8,
                            headers={"User-Agent":"MAPlanning/1.0"})
        if resp.status_code != 200:
            _CH_CACHE[key] = {}
            return {}

        items = resp.json().get("items", [])
        if not items:
            _CH_CACHE[key] = {}
            return {}

        # Pick best match: prefer active companies, then closest name
        best = None
        for item in items:
            status = item.get("company_status","").lower()
            if status in ("active",""):
                best = item; break
        if not best:
            best = items[0]

        ch_num  = best.get("company_number","")
        addr_obj= best.get("registered_office_address",{})
        addr    = ", ".join(filter(None,[
            addr_obj.get("address_line_1",""),
            addr_obj.get("locality",""),
            addr_obj.get("postal_code",""),
        ]))
        ch_link = f"https://find-and-update.company-information.service.gov.uk/company/{ch_num}"

        result = {
            "ch_number":    ch_num,
            "reg_address":  addr,
            "contact_link": ch_link,
        }
        _CH_CACHE[key] = result
        time.sleep(0.3)   # respect CH rate limit
        return result

    except Exception as e:
        log(f"  ⚠️  Companies House lookup failed for '{name[:30]}': {e}", 2)
        _CH_CACHE[key] = {}
        return {}


def enrich_lead(lead):
    """
    Adds sales intelligence fields to a qualified lead dict.
    Called after PDF scan confirms the lead is real.
    """
    desc     = lead.get("desc","")
    triggers = lead.get("triggers","").split(", ")
    council  = lead.get("council","")
    score    = lead.get("score", 50)

    log(f"  🔬 Enriching…", 2)

    # 1. Project value estimate
    lo, hi = estimate_project_value(desc, council, triggers)
    lead["est_value"] = f"{lo} – {hi}"
    log(f"  💰 Est. value: {lead['est_value']}", 2)

    # 2. Impact probability
    prob = impact_probability(desc, triggers, score)
    lead["impact_prob"] = prob
    log(f"  📊 Impact probability: {prob}%", 2)

    # 3. Companies House lookup for applicant (developer)
    applicant = lead.get("applicant","")
    ch_app    = lookup_companies_house(applicant) if applicant else {}
    lead["developer"]    = applicant  # keep original name
    lead["ch_number"]    = ch_app.get("ch_number","")
    lead["reg_address"]  = ch_app.get("reg_address","")
    lead["contact_link"] = ch_app.get("contact_link","")
    if ch_app:
        log(f"  🏢 CH: {lead['ch_number']} | {lead['reg_address'][:50]}", 2)

    # 4. Architect — treat agent as architect for planning purposes
    #    (planning agent is almost always an architect or planning consultant)
    lead["architect"] = lead.get("agent","")

    return lead



# ════════════════════════════════════════════════════════════
# DISCLAIMER AUTO-ACCEPT
# Many Idox portals show a T&C gate before allowing searches.
# The preflight marks these as "ok" (correctly), but without
# auto-accept the scraper reads the DISCLAIMER form instead of
# the SEARCH form, posts to accept it, then finds 0 search
# results. This function detects and bypasses that gate.
# ════════════════════════════════════════════════════════════
def _is_disclaimer_page(html):
    """True if the page is an Idox disclaimer/T&C gate rather than a search form."""
    tl = html.lower()
    has_disclaimer = any(kw in tl for kw in (
        "disclaimer", "terms and conditions", "i accept", "agree to the terms",
        "before you continue", "acceptedterms", "disclaimeraccept",
    ))
    has_search_form = bool(re.search(
        r'name=["\'](?:description|searchCriteria|caseDecision|keyWord)', tl
    ))
    return has_disclaimer and not has_search_form

def _accept_disclaimer(sess, base_url, html, current_url):
    """
    POST to accept the Idox disclaimer gate, unlocking the session for searches.

    Idox disclaimer forms typically POST to:
      /online-applications/disclaimerAccepted.do
    with hidden fields ACCESSED and SUBMITTED plus a submit button.

    Returns True if acceptance succeeded (or was not needed), False on failure.
    """
    from urllib.parse import urlparse as _up
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form")
    if not form:
        return False

    action = form.get("action", "")
    p = _up(base_url)
    root = f"{p.scheme}://{p.netloc}"
    if action.startswith("http"):
        post_url = action
    elif action.startswith("/"):
        post_url = root + action
    else:
        post_url = base_url.rstrip("/") + "/" + action.lstrip("/")

    # Build POST body from all hidden fields
    fields = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if not name:
            continue
        t = inp.get("type", "text").lower()
        if t == "submit":
            continue
        fields[name] = inp.get("value", "")

    # Ensure the acceptance flags are set
    for flag in ("SUBMITTED", "submitted", "ACCEPTED", "accepted", "AGREE", "agree"):
        if flag in fields:
            fields[flag] = "1"

    try:
        r = sess.post(post_url, data=fields,
                      headers={"Referer": current_url},
                      timeout=20, allow_redirects=True, verify=False)
        log(f"  📋 Disclaimer accepted → HTTP {r.status_code} ({post_url[-50:]})", 1)
        return r.status_code in (200, 302)
    except Exception as e:
        log(f"  ⚠️  Disclaimer POST failed: {e}", 1)
        return False

# ════════════════════════════════════════════════════════════
# SESSION WARMUP
# Idox portals require a properly initialised session before they
# will accept POST requests. A cold session (going straight to
# /search.do) often returns 200 on GET but 403 on POST because:
#   • The JSESSIONID cookie is not seeded from the portal root
#   • The disclaimer acceptance cookie is absent
#   • Some WAF rules require an Origin that matches a prior GET
#
# Fix: before any keyword search, visit the portal root first,
# then the search page, accept any disclaimer encountered.
# After this, POST requests work reliably.
# ════════════════════════════════════════════════════════════
def _warmup_portal_session(sess, base_url):
    """
    Initialise the Idox session before searching.

    1. GET portal root    → seeds JSESSIONID, any tracking cookies
    2. GET search page    → checks for disclaimer gate
    3. Accept disclaimer  → sets acceptance cookie if required
    4. GET search page    → confirms form is now accessible

    Returns True if session is ready for POST searches, False if
    the portal is unreachable or permanently blocked.
    """
    p    = urlparse(base_url)
    root = f"{p.scheme}://{p.netloc}"

    # Step 1 — seed JSESSIONID from portal root
    try:
        sess.get(root, timeout=12, verify=False, allow_redirects=True)
    except Exception:
        pass  # best-effort; the JSESSIONID may still come from step 2

    time.sleep(0.4)

    # Step 2 — load search page
    search_url = f"{base_url}/search.do?action=advanced&searchType=Application"
    r = safe_get(sess, search_url, timeout=18)
    if not r or r.status_code != 200:
        return False

    # Step 3 — accept disclaimer if shown
    if _is_disclaimer_page(r.text):
        log(f"  📋 Session warmup: disclaimer gate — accepting", 1)
        _accept_disclaimer(sess, base_url, r.text, r.url)
        time.sleep(0.8)
        # Step 4 — re-fetch search page to confirm acceptance
        r2 = safe_get(sess, search_url, timeout=18)
        if not r2 or r2.status_code != 200 or _is_disclaimer_page(r2.text):
            log(f"  ⚠️  Session warmup: disclaimer accept did not unlock portal", 1)
            return False

    log(f"  🔥 Session warmed up", 1)
    return True


# ════════════════════════════════════════════════════════════
# FORM DISCOVERY
# Reads ALL fields from the Idox search page HTML so hidden
# CSRF tokens are automatically included in the POST body.
# ════════════════════════════════════════════════════════════
def read_form(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form")
    if not form:
        return None

    action = form.get("action", "")
    if action.startswith("http"):
        form_action = action
    elif action.startswith("/"):
        p = urlparse(base_url)
        form_action = f"{p.scheme}://{p.netloc}{action}"
    else:
        form_action = f"{base_url}/{action.lstrip('/')}"

    fields = {}
    for el in form.find_all(["input", "select", "textarea"]):
        name = el.get("name")
        if not name:
            continue
        tag = el.name.lower()
        if tag == "input":
            t = el.get("type", "text").lower()
            if t == "submit":
                continue
            if t in ("checkbox", "radio") and not el.get("checked"):
                continue
            fields[name] = el.get("value", "")
        elif tag == "select":
            first = el.find("option")
            fields[name] = first.get("value", "") if first else ""
        elif tag == "textarea":
            fields[name] = el.get_text(strip=True)

    # Find description / keyword field
    desc_field = None
    for el in form.find_all("input"):
        nm = el.get("name", "").lower()
        ei = el.get("id",   "").lower()
        if "description" in nm or "description" in ei or "keyword" in nm:
            desc_field = el.get("name")
            break

    # Find decision dropdown — 3-pass matching to avoid picking wrong option
    decision_field = None
    refused_value  = None
    for sel in form.find_all("select"):
        nm = sel.get("name", "").lower()
        ei = sel.get("id",   "").lower()
        if "decision" not in nm and "decision" not in ei:
            continue
        if "appeal" in nm or "appeal" in ei:
            continue
        opts = [(opt.get_text(strip=True), opt.get("value","")) for opt in sel.find_all("option")]
        # Pass 1: exact label "Refused"
        exact = None
        for label, val in opts:
            if label.strip().lower() == "refused":
                exact = (sel.get("name"), val); break
        # Pass 2: label contains "refus" but not "split"/"part"
        partial = None
        if not exact:
            for label, val in opts:
                lt = label.strip().lower()
                if "refus" in lt and "split" not in lt and "part" not in lt:
                    partial = (sel.get("name"), val); break
        # Pass 3: known Idox refused value codes
        coded = None
        if not exact and not partial:
            for label, val in opts:
                if val.upper() in {"REF","REFUSED","R","RFD"}:
                    coded = (sel.get("name"), val); break
        chosen = exact or partial or coded
        if chosen:
            decision_field, refused_value = chosen
        if decision_field:
            break

    # Find decision date start / end fields
    date_start = None
    date_end   = None
    for el in form.find_all("input"):
        nm = (el.get("name", "") + el.get("id", "")).lower()
        if not date_start and any(h in nm for h in [
            "decisionstart", "decidedstart", "applicationdecisionstart"
        ]):
            date_start = el.get("name")
        if not date_end and any(h in nm for h in [
            "decisionend", "decidedend", "applicationdecisionend"
        ]):
            date_end = el.get("name")

    return {
        "form_action": form_action,
        "fields":      fields,
        "desc":        desc_field,
        "decision":    decision_field,
        "refused":     refused_value,
        "date_start":  date_start,
        "date_end":    date_end,
    }

# ════════════════════════════════════════════════════════════
# SEARCH ONE KEYWORD
# ════════════════════════════════════════════════════════════
def _do_post(sess, base_url, keyword, date_from, date_to, with_refused=True):
    """
    One attempt at the Idox search form POST.
    Returns (items_list, form_info_dict) or ([], None) on failure.
    with_refused=False skips the decision filter entirely — used as fallback
    when the refused-filtered search returns 0 results.
    """
    search_url = f"{base_url}/search.do?action=advanced&searchType=Application"

    r = safe_get(sess, search_url, timeout=25)
    if not r or r.status_code != 200:
        log(f"  ❌ Search page HTTP {r.status_code if r else 'no response'}", 1)
        return [], None

    # ── Disclaimer gate: if portal redirected to T&C page, accept and retry ──
    if _is_disclaimer_page(r.text):
        log(f"  📋 Disclaimer gate detected — accepting automatically", 1)
        accepted = _accept_disclaimer(sess, base_url, r.text, r.url)
        if accepted:
            time.sleep(1)
            r = safe_get(sess, search_url, timeout=25)
            if not r or r.status_code != 200:
                log(f"  ❌ Search page still unavailable after disclaimer accept", 1)
                return [], None
            if _is_disclaimer_page(r.text):
                log(f"  ❌ Still on disclaimer page after accept — portal blocked", 1)
                return [], None
        else:
            log(f"  ❌ Disclaimer accept failed", 1)
            return [], None

    form = read_form(r.text, base_url)
    if not form:
        log(f"  ❌ No form on search page", 1)
        return [], None

    post = dict(form["fields"])
    post["searchType"] = "Application"
    post[form["desc"] or "searchCriteria.description"] = keyword

    if with_refused:
        if form["decision"] and form["refused"]:
            post[form["decision"]] = form["refused"]
        else:
            post["searchCriteria.caseDecision"] = "REF"
    # else: leave decision field at its default (blank / any) so ALL decisions come back

    post[form["date_start"] or "date(applicationDecisionStart)"] = date_from
    post[form["date_end"]   or "date(applicationDecisionEnd)"]   = date_to

    # Extract Origin from base_url — some Idox WAF rules require it
    _p    = urlparse(base_url)
    _origin = f"{_p.scheme}://{_p.netloc}"

    try:
        pr = sess.post(
            form["form_action"], data=post,
            headers={
                "Referer":      search_url,
                "Origin":       _origin,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=30, allow_redirects=True,
        )
        log(f"  POST → HTTP {pr.status_code}", 1)
        if pr.status_code == 429:
            wait = int(pr.headers.get("Retry-After", 90))
            log(f"  🚫 429 Rate Limited — marking council blocked for {wait}s", 1)
            _rate_limited_until[base_url] = datetime.now() + timedelta(seconds=wait)
            return [], None
    except Exception as e:
        log(f"  ❌ POST failed: {e}", 1)
        return [], None

    # ── 403 recovery: re-warm the session and retry once ─────────────────
    # 403 here almost always means the session cookies are stale or the
    # disclaimer was never accepted in this session. Re-warming fixes it.
    if pr.status_code == 403:
        log(f"  ⚠️  403 on POST — re-warming session and retrying once", 1)
        _warmup_portal_session(sess, base_url)
        time.sleep(1)
        # Fresh GET to get updated form token
        r2 = safe_get(sess, search_url, timeout=25)
        if r2 and r2.status_code == 200 and not _is_disclaimer_page(r2.text):
            form2 = read_form(r2.text, base_url)
            if form2:
                post2 = dict(form2["fields"])
                post2["searchType"] = "Application"
                post2[form2["desc"] or "searchCriteria.description"] = keyword
                if with_refused and form2["decision"] and form2["refused"]:
                    post2[form2["decision"]] = form2["refused"]
                elif with_refused:
                    post2["searchCriteria.caseDecision"] = "REF"
                post2[form2["date_start"] or "date(applicationDecisionStart)"] = date_from
                post2[form2["date_end"]   or "date(applicationDecisionEnd)"]   = date_to
                try:
                    pr = sess.post(
                        form2["form_action"], data=post2,
                        headers={
                            "Referer":      search_url,
                            "Origin":       _origin,
                            "Content-Type": "application/x-www-form-urlencoded",
                        },
                        timeout=30, allow_redirects=True,
                    )
                    log(f"  POST retry → HTTP {pr.status_code}", 1)
                    if pr.status_code == 403:
                        log(f"  ❌ Still 403 after session re-warm — portal blocking this IP", 1)
                        return [], None
                    form = form2  # use updated form for result fetching
                except Exception as e:
                    log(f"  ❌ POST retry failed: {e}", 1)
                    return [], None
        else:
            log(f"  ❌ Could not re-warm session — skipping this keyword", 1)
            return [], None

    time.sleep(2)  # give server time to store session

    # Some portals redirect the POST straight to results — check first
    # Use title detection (case-insensitive) not URL pattern — Bradford uses lowercase "results"
    if pr.status_code == 200:
        _pr_soup  = BeautifulSoup(pr.text, "html.parser")
        _pr_title = _pr_soup.title.get_text(strip=True) if _pr_soup.title else ""
        _is_results = (
            "result" in pr.url.lower() or
            "result" in _pr_title.lower() or
            (
                "Applications Search" not in _pr_title and
                _pr_title and
                bool(_pr_soup.select("li.searchresult, div.searchresult, li[class*='searchresult']"))
            )
        )
        if _is_results:
            items = collect_pages(sess, base_url, pr, keyword)
            if items:
                return items, form

    # Standard: GET the results page — try two common URL variants
    result_urls = [
        f"{base_url}/advancedSearchResults.do?action=firstPage",
        f"{base_url}/searchResults.do?action=firstPage",
        f"{base_url}/pagedSearchResults.do?action=firstPage", 
    ]
    for rurl in result_urls:
        rr = safe_get(sess, rurl)
        if not rr:
            continue
        # Check if we got results or bounced back to search form
        soup_title = ""
        try:
            from bs4 import BeautifulSoup as _BS
            soup_title = _BS(rr.text, "html.parser").title.get_text(strip=True) if _BS(rr.text,"html.parser").title else ""
        except Exception:
            pass
        is_results_page = (
            "Results" in soup_title or
            "result" in rr.url.lower() or
            ("Applications Search" not in soup_title and soup_title)
        )
        if is_results_page:
            items = collect_pages(sess, base_url, rr, keyword)
            if items:
                return items, form
            # Got a results page but 0 items — no point trying second URL
            break

    # Both result URLs returned 0 / bounced to search — nothing here
    return [], form


def search_one_keyword(sess, base_url, keyword, date_from, date_to):
    # Skip immediately if this council is still rate-limited
    if base_url in _rate_limited_until:
        if datetime.now() < _rate_limited_until[base_url]:
            log(f"  ⏭️  Rate limited — skipping '{keyword}'", 1)
            return []
        else:
            del _rate_limited_until[base_url]  # ban expired, clear it
    log(f"  🔎 '{keyword}'  {date_from} → {date_to}", 1)

    # ── Attempt 1: keyword + refused decision filter + date range ────────────
    items, form = _do_post(sess, base_url, keyword, date_from, date_to, with_refused=True)

    if form:
        log(
            f"  desc='{form['desc']}' decision='{form['decision']}' "
            f"refused='{form['refused']}' "
            f"start='{form['date_start']}' end='{form['date_end']}'", 1
        )

    if items:
        return items

    # ── Attempt 2: 0 results with refused filter — retry WITHOUT it ──────────
    # Reason: some portals use non-standard refused values (e.g. "RAW"),
    # or the refused+keyword combo genuinely has 0 results but keyword alone does.
    # The PDF scanner already filters for refusal trigger words, so this is safe.
    if form is not None:
        log(f"  ⚠️  0 results with decision filter — retrying without it", 1)
        time.sleep(2)
        # Need a fresh session cookie (JSESSIONID) for new search
        items2, _ = _do_post(sess, base_url, keyword, date_from, date_to, with_refused=False)
        if items2:
            log(f"  ✅ Got {len(items2)} results without decision filter — PDF scanner will qualify", 1)
        return items2

    return []


MAX_PAGES = 30   # hard cap — no portal has 30 pages of retail refusals

def collect_pages(sess, base_url, first_resp, keyword):
    all_items    = []
    seen_keyvals = set()   # ← dedup guard: breaks the infinite loop
    page_num     = 1
    resp         = first_resp

    while page_num <= MAX_PAGES:
        soup  = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.get_text().strip() if soup.title else ""
        items = parse_results(soup)

        if not items:
            if page_num == 1:
                log(f"  ⚠️  0 results — title='{title}'", 1)
                snippet = soup.get_text(separator=" ", strip=True)[:250]
                log(f"  Page text: {snippet}", 1)
            else:
                log(f"  ✅ {len(all_items)} total across {page_num-1} pages", 1)
            break

        # Duplicate-page detection: if ALL keyVals on this page are ones
        # we have already seen, the server is cycling — stop immediately.
        page_kvs = [i["keyVal"] for i in items]
        new_kvs  = [kv for kv in page_kvs if kv not in seen_keyvals]

        if not new_kvs and page_num > 1:
            log(f"  🔄 Page {page_num} is a duplicate of a previous page — stopping pagination", 1)
            log(f"  ✅ {len(all_items)} total (cycle detected)", 1)
            break

        # Even if some are new, only add genuinely new ones
        for item in items:
            if item["keyVal"] not in seen_keyvals:
                seen_keyvals.add(item["keyVal"])
                all_items.append(item)

        log(f"  📄 Page {page_num}: {len(items)} results ({len(new_kvs)} new)", 1)

        if page_num == MAX_PAGES:
            log(f"  ⚠️  Hit {MAX_PAGES}-page cap — stopping", 1)
            break

        # Check for next-page link
        has_next = bool(
            soup.find("a", string=re.compile(r"Next", re.I)) or
            soup.find("a", href=re.compile(r"searchCriteria\.page="))
        )
        if not has_next:
            log(f"  ✅ {len(all_items)} total", 1)
            break

        page_num += 1
        next_url = f"{base_url}/pagedSearchResults.do?action=page&searchCriteria.page={page_num}"
        resp = safe_get(sess, next_url)
        if not resp:
            break
        time.sleep(0.5)   # reduced from 1s

    log(f"  → {len(all_items)} for '{keyword}'", 1)
    return all_items

# ════════════════════════════════════════════════════════════
# PARSE RESULT CARDS
# ════════════════════════════════════════════════════════════
def extract_ref(text):
    for pat in [
        r'Ref\.?\s*[Nn]o[.:\s]+([A-Z0-9][A-Z0-9/\-]{3,30})',
        r'Reference[:\s]+([A-Z0-9][A-Z0-9/\-]{3,30})',
        r'\b([A-Z]{1,3}\d{4}/\d{4,})\b',
        r'\b(\d{5,}/[A-Z0-9]{2,}/\d{4})\b',
        r'\b([A-Z]{2}/\d{4}/\d{4,}/[A-Z0-9]+)\b',
        r'\b(\d{2}/\d{4,}/[A-Z]+)\b',
    ]:
        m = re.search(pat, text)
        if m:
            c = m.group(1).strip().rstrip(".")
            if 4 < len(c) < 35:
                return c
    return ""

def parse_results(soup):
    items = []
    rows = (
        soup.select("li.searchresult")            or
        soup.select("div.searchresult")           or
        soup.select("li[class*='searchresult']")  or
        soup.select("div[class*='searchresult']")
    )
    for card in rows:
        a = (
            card.select_one("a[href*='keyVal']") or
            card.select_one("a[href*='applicationDetails']") or
            card.select_one("a")
        )
        if not a:
            continue
        href    = a.get("href", "")
        key_val = href.split("keyVal=")[-1].split("&")[0] if "keyVal=" in href else ""
        if not key_val:
            continue
        card_text = card.get_text(separator=" ", strip=True)
        desc      = a.get_text(strip=True)[:250]
        ref       = extract_ref(card_text) or key_val
        addr_el   = card.select_one(".address") or card.select_one(".addressCol")
        addr      = addr_el.get_text(strip=True) if addr_el else ""
        if not addr:
            m = re.search(r'([A-Z][^\|]{8,80}[A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2})', card_text)
            addr = m.group(1).strip() if m else ""
        items.append({"ref": ref, "keyVal": key_val, "desc": desc, "addr": addr[:150]})
    return items

# ════════════════════════════════════════════════════════════
# APPLICATION DETAILS (summary + details tabs)
# ════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════
# DECISION CLASSIFIER — shared constants
# ════════════════════════════════════════════════════════════
_REFUSAL_WORDS  = ("refus",)
_APPROVAL_WORDS = (
    "approv", "grant", "permit", "permitted",
    "lawful", "certif",
    "prior approval", "no prior approval",
    "no objection", "withdrawn", "invalid",
    "discharge", "not required", "consent",
    # NOTE: "conditions" intentionally excluded — "reasons for refusal...conditions"
    # would false-match. "Approve with conditions" is caught by "approv" already.
)
# Decision values that Idox portals return — used in pass 3 scan
_APPROVAL_EXACT = [
    "permit", "permitted", "permitted development",
    "approve with conditions", "approved with conditions",
    "approved subject to conditions", "approved unconditionally",
    "granted", "approved", "grant",
    "prior approval required", "prior approval not required",
    "no prior approval required", "no objection",
    "withdrawn", "invalid", "lawful development certificate",
    "lawful use", "certificate of lawfulness",
]
_REFUSAL_EXACT = [
    "refused", "refuse", "refusal",
    "application refused",
    "planning permission refused",
    "delegated refusal",
    "committee refusal",
    "rfsd",                          # Idox internal decision code used by some councils
    "rfd",                           # alternative Idox code
    "appeal dismissed", "appeal is dismissed",
]


def _parse_decision_from_soup(soup):
    """
    Extract the Decision field from an Idox summary page.

    4 passes — each more aggressive:
      1. <tr><th>decision</th><td>VALUE</td>  (exact label, never matches "status")
      2. <dt>decision</dt><dd>VALUE</dd>
      3. Exact-line scan of full page text for known decision strings
      4. Substring scan — finds "Permit", "Refused" etc. anywhere in page

    Returns raw text e.g. "Refused", "Permit", "Approve with Conditions"
    or "" if genuinely not found.
    """
    # Pass 1: exact <th>decision</th> label
    for row in soup.find_all("tr"):
        th = row.find("th")
        td = row.find("td")
        if not th or not td:
            continue
        label = th.get_text(strip=True).lower().rstrip(":").strip()
        if label == "decision":
            val = td.get_text(strip=True)
            if val and val.lower() not in ("", "decided", "-", "n/a", "none", "pending"):
                return val

    # Pass 2: <dt>decision</dt><dd>VALUE</dd>
    for dt in soup.find_all("dt"):
        label = dt.get_text(strip=True).lower().rstrip(":").strip()
        if label == "decision":
            dd = dt.find_next_sibling("dd")
            if dd:
                val = dd.get_text(strip=True)
                if val and val.lower() not in ("", "decided", "-", "n/a", "pending"):
                    return val

    # Pass 3: exact-line scan
    page_text = soup.get_text(separator="\n", strip=True)
    for line in page_text.split("\n"):
        stripped = line.strip().lower()
        if stripped in _REFUSAL_EXACT:
            return line.strip()
        if stripped in _APPROVAL_EXACT:
            return line.strip()

    # Pass 4: substring scan — last resort
    page_lower = page_text.lower()
    for word in _REFUSAL_EXACT:
        if word in page_lower:
            idx = page_lower.find(word)
            return page_text[idx:idx+len(word)].strip()
    for word in _APPROVAL_EXACT:
        if word in page_lower:
            idx = page_lower.find(word)
            return page_text[idx:idx+len(word)].strip()

    return ""


def _normalise_decision(raw):
    """
    Convert raw portal decision text to canonical status string.
    Returns "REFUSED", "APPROVED — <detail>", or the raw text verbatim.
    """
    if not raw:
        return ""
    r = raw.lower()
    if any(w in r for w in _REFUSAL_WORDS):
        return "REFUSED"
    if any(w in r for w in _APPROVAL_WORDS):
        return f"APPROVED — {raw}"
    return raw


def get_details(sess, base_url, key_val):
    """
    Fetch summary + details tabs for one application.
    Returns dict with: decision, proposal, address, date_dec, date_rec,
                       applicant, agent, app_type
    """
    d = {}
    r = safe_get(sess, f"{base_url}/applicationDetails.do?activeTab=summary&keyVal={key_val}")
    if r and r.status_code == 200:
        soup = BeautifulSoup(r.text, "html.parser")

        # ── Decision: use 3-pass parser — never picks up "Status: Decided" ──
        raw_decision = _parse_decision_from_soup(soup)
        d["decision"] = raw_decision

        # ── Other fields from table rows ────────────────────────────────────
        for row in soup.select("tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            label = th.get_text(strip=True).lower().strip().rstrip(":")
            value = td.get_text(strip=True)
            if   label == "proposal":                                d["proposal"] = value
            elif label == "address":                                 d["address"]  = value
            elif label in ("decision issued date", "decision date",
                           "date of decision", "date decision issued"): d["date_dec"] = value
            elif label in ("application validated", "date validated",
                           "date received", "received"):
                d.setdefault("date_rec", value)

        log(f"  Decision='{d.get('decision','?')}' | AppType='{d.get('app_type','?')}' | Date='{d.get('date_dec','?')}'", 2)

    # ── Details tab: applicant, agent, app type ──────────────────────────────
    time.sleep(0.5)
    r2 = safe_get(sess, f"{base_url}/applicationDetails.do?activeTab=details&keyVal={key_val}")
    if r2 and r2.status_code == 200:
        soup2 = BeautifulSoup(r2.text, "html.parser")
        for row in soup2.select("tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            label = th.get_text(strip=True).lower().strip().rstrip(":")
            value = td.get_text(strip=True)
            if "applicant name" in label and not d.get("applicant"): d["applicant"] = value
            if "agent name"     in label and not d.get("agent"):     d["agent"]     = value
            if label == "agent"           and not d.get("agent"):     d["agent"]     = value
            if "application type" in label and not d.get("app_type"): d["app_type"] = value
    return d

# DOCUMENT FINDER
# Handles all known Idox HTML layouts for the documents tab,
# and resolves viewDocument.do to direct file URLs.
# ════════════════════════════════════════════════════════════

# Document type priority scores (higher = better)
_DOC_SCORES = {
    "decision notice": 100, "refusal notice":  100,
    "decision letter": 100, "refusal letter":  100,
    "refusal":          95, "decision":         90,
    "appeal decision":  80, "officer report":   30,
    "committee report": 25, "planning statement": 5,
}

def _score_text(text):
    t = text.lower().strip()
    for phrase, s in sorted(_DOC_SCORES.items(), key=lambda x: -x[1]):
        if phrase in t:
            return s
    return 0

def _abs_url(root, base_url, href):
    if not href or href.startswith(("javascript:", "#", "mailto:")):
        return None
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return root + href
    return base_url.rstrip("/") + "/" + href.lstrip("/")

def _resolve_viewdoc(sess, url, base_url, soup_of_doc_tab=None):
    """
    Convert a session-gated viewDocument.do URL into a permanent direct file URL.

    Idox portals serve decision PDFs in two ways:
      A) 302 redirect  → /files/DC_WKSSDec/yyyy/mm/dd/filename.pdf  (permanent, no session)
      B) Direct stream → 200 with PDF bytes, URL stays as viewDocument.do  (session required)

    For case B, "Document Unavailable" appears when the URL is clicked from
    email or Sheets because there is no active session cookie.

    We try four strategies to escape case B:
      1. r.history — any redirect step pointing to /files/
      2. X-Accel-Redirect / X-Sendfile proxy headers
      3. Scan documents tab HTML for /files/ hrefs on the same page
      4. Check onclick / data-* attributes on doc tab elements

    If none work: store the portal application URL (always public) as fallback.
    The PDF bytes from the session fetch are still passed to scan_pdf regardless.
    """
    import re as _re
    p    = urlparse(base_url)
    root = f"{p.scheme}://{p.netloc}"

    if "viewDocument.do" not in url and "downloadDocument" not in url:
        return url, None

    try:
        r = sess.get(url, allow_redirects=True, timeout=40,
                     headers={"Accept": "application/pdf,*/*", "Referer": base_url})

        # Strategy 1: redirect chain — any step landing on /files/
        for resp in list(r.history) + [r]:
            u = getattr(resp, "url", "")
            if "/files/" in u:
                direct = root + u if u.startswith("/") else u
                log(f"  ✅ Direct URL via redirect: …{direct[-60:]}", 2)
                return direct, r

        # Strategy 2: reverse-proxy sendfile headers
        for hdr in ("X-Accel-Redirect", "X-Sendfile", "X-Reproxy-URL"):
            val = r.headers.get(hdr, "").strip()
            if val:
                direct = root + val if val.startswith("/") else val
                log(f"  ✅ Direct URL via {hdr}: …{direct[-60:]}", 2)
                return direct, r

        # Strategy 3: scan documents tab HTML for /files/ hrefs
        if soup_of_doc_tab:
            for a in soup_of_doc_tab.find_all("a", href=True):
                h = a["href"]
                if "/files/" in h:
                    direct = root + h if h.startswith("/") else h
                    log(f"  ✅ Direct /files/ link in HTML: …{direct[-60:]}", 2)
                    return direct, r

        # Strategy 4: onclick / data attributes in doc tab
        if soup_of_doc_tab:
            for tag in soup_of_doc_tab.find_all(True):
                for attr in ("onclick", "data-url", "data-href", "data-src"):
                    val = tag.get(attr, "")
                    if "/files/" in val:
                        m = _re.search(r"(/[^\s'\"]+/files/[^\s'\"]+)", val)
                        if m:
                            path = m.group(1)
                            direct = root + path if path.startswith("/") else path
                            log(f"  ✅ Direct URL in {attr}: …{direct[-60:]}", 2)
                            return direct, r

        # No permanent URL found — we still have the PDF bytes from this session
        ct = r.headers.get("Content-Type", "").lower()
        if "pdf" in ct or r.content[:4] == b"%PDF":
            log(f"  ⚠️  Session-only URL (bytes available for scan, link may expire)", 2)
            return url, r

        return url, r

    except Exception as e:
        log(f"  ⚠️  viewDoc error: {e}", 2)
        return url, None


def find_decision_doc(sess, base_url, key_val):
    """
    Fetch the Documents tab and find the best decision notice.
    Returns (store_url, content_response_or_None).
      store_url          — URL to save in Sheets (direct PDF if possible)
      content_response   — response object if we already have the bytes
                           (avoids double-download in scan_pdf)
    """
    log(f"  📂 Documents tab…", 2)
    from urllib.parse import urlparse
    p    = urlparse(base_url)
    root = f"{p.scheme}://{p.netloc}"

    tab_url = f"{base_url}/applicationDetails.do?activeTab=documents&keyVal={key_val}"
    r = sess.get(tab_url, timeout=25, allow_redirects=True, verify=False)
    if not r or r.status_code != 200:
        log(f"  ❌ Documents tab HTTP {getattr(r,'status_code','?')}", 2)
        return None, None

    soup = BeautifulSoup(r.text, "html.parser")

    # ── Gather candidates from ALL HTML patterns ─────────────
    # Each candidate: {"score": int, "url": str, "label": str}
    candidates = []

    def _add(href, label, score):
        u = _abs_url(root, base_url, href)
        if u:
            candidates.append({"score": score, "url": u, "label": label})

    # Strategy 1: <tr> with <td> cells (classic Idox table layout)
    doc_tables = soup.find_all("table")
    for tbl in doc_tables:
        for row in tbl.find_all("tr"):
            tds = row.find_all("td")
            if len(tds) < 2:
                continue
            # All text in this row
            row_text = " ".join(td.get_text(strip=True) for td in tds)
            score = _score_text(row_text)
            if score == 0:
                continue
            # Find a link in this row
            for td in reversed(tds):
                for a in td.find_all("a", href=True):
                    _add(a["href"], row_text[:50], score)
                    break

    # Strategy 2: <li> items (newer Idox accordion / list layout)
    for li in soup.find_all("li"):
        li_text = li.get_text(separator=" ", strip=True)
        score = _score_text(li_text)
        if score == 0:
            continue
        for a in li.find_all("a", href=True):
            _add(a["href"], li_text[:50], score)

    # Strategy 3: any <a> whose text or nearby heading scores well
    for a in soup.find_all("a", href=True):
        link_text = a.get_text(strip=True)
        parent_text = a.parent.get_text(separator=" ", strip=True) if a.parent else ""
        score = max(_score_text(link_text), _score_text(parent_text))
        if score >= 25:  # only meaningful scores
            _add(a["href"], link_text[:50], score)

    # Strategy 4: direct /files/ PDF links (always include, score by filename)
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if "/files/" in h and ".pdf" in h.lower():
            fname = h.split("/")[-1].lower()
            score = 90 if any(w in fname for w in ["dec", "refus", "notice"]) else 10
            _add(h, f"files/{h.split('/')[-1][:40]}", score)

    # Deduplicate by URL, keep highest score per URL
    seen_urls = {}
    for cand in candidates:
        u = cand["url"]
        if u not in seen_urls or cand["score"] > seen_urls[u]["score"]:
            seen_urls[u] = cand

    ranked = sorted(seen_urls.values(), key=lambda x: -x["score"])

    if not ranked:
        log(f"  ❌ No document links found ({len(soup.find_all('a'))} total anchors on page)", 2)
        return None, None

    log(f"  Found {len(ranked)} candidate doc links", 2)
    for cand in ranked[:3]:
        log(f"    score={cand['score']:3d} | {cand['label'][:55]}", 2)

    # Take best candidate
    best = ranked[0]
    log(f"  → Best: score={best['score']} | {best['url'][-65:]}", 2)

    # Resolve viewDocument.do to direct URL (fixes "Document Unavailable")
    resolved_url, prefetched = _resolve_viewdoc(sess, best["url"], base_url, soup_of_doc_tab=soup)
    if resolved_url != best["url"]:
        log(f"  ✅ Resolved to direct URL: …{resolved_url[-65:]}", 2)

    return resolved_url, prefetched


# ════════════════════════════════════════════════════════════
# PDF SCANNER  —  accepts pre-fetched response to avoid double download
# ════════════════════════════════════════════════════════════
# Words that MUST appear in the PDF for it to count as a refusal.
# An approved application's officer report can contain trigger topic words
# ("sequential test", "nppf") while still recommending approval.
# We require at least one explicit refusal phrase in the document.
_REFUSAL_PHRASES = [
    "is refused",
    "be refused",
    "hereby refused",
    "refusal of",
    "reasons for refusal",
    "reason for refusal",
    "refuse planning permission",
    "refused planning permission",
    "application is refused",
    "permission is refused",
    "appeal is dismissed",       # appeal decision = original refusal confirmed
]

def scan_pdf(sess, pdf_url, prefetched_response=None):
    """
    Download and scan a PDF for:
      1. Retail planning trigger words (topic relevance)
      2. Explicit refusal language (REQUIRED — prevents approved apps slipping through)

    Returns (trigger_words, is_refused):
      trigger_words  — list of matched PDF_TRIGGERS
      is_refused     — True only if PDF contains explicit refusal language
    Both must be non-empty/True for a lead to qualify.
    """
    log(f"  📥 …{pdf_url[-65:]}", 2)
    try:
        if prefetched_response is not None:
            r = prefetched_response
            log(f"  (using prefetched response)", 2)
        else:
            r = sess.get(
                pdf_url,
                headers={"Accept": "application/pdf,*/*", "Referer": pdf_url},
                timeout=50, allow_redirects=True,
            )

        ct   = r.headers.get("Content-Type", "").lower()
        size = len(r.content)
        log(f"  HTTP {r.status_code} | {size:,}b | {ct[:35]}", 2)

        if r.status_code != 200:
            return [], False

        # Got HTML back = session error / "Document Unavailable"
        if "html" in ct:
            snippet = r.text[:300].replace("\n", " ")
            log(f"  ⚠️  Got HTML (session issue or wrong URL): {snippet[:120]}", 2)
            return [], False

        if size < 800:
            log(f"  ⚠️  Too small to be real PDF ({size}b)", 2)
            return [], False

        # Confirm it's a PDF (magic bytes)
        if not r.content[:4] == b"%PDF":
            # Some portals serve PDF without correct Content-Type
            if size > 5000:
                log(f"  ⚠️  No PDF magic bytes but large — trying anyway", 2)
            else:
                log(f"  ⚠️  Not a PDF", 2)
                return [], False

        text = ""
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            log(f"  {len(pdf.pages)}pp", 2)
            for pg in pdf.pages:
                t = pg.extract_text()
                if t:
                    text += t.lower() + " "

        if not text.strip():
            log(f"  ⚠️  No extractable text — scanned image PDF?", 2)
            return [], False

        log(f"  {len(text):,} chars extracted", 2)

        # ── Check 1: is this actually a refusal? ─────────────────────
        is_refused = any(phrase in text for phrase in _REFUSAL_PHRASES)
        if is_refused:
            log(f"  ✅ Refusal confirmed in PDF text", 2)
        else:
            log(f"  ⚠️  No refusal language found — likely approved/other decision", 2)

        # ── Check 2: retail planning topic trigger words ──────────────
        found = [w for w in PDF_TRIGGERS if w in text]
        if found:
            for w in found:
                log(f"  🎯 '{w}'", 2)
        else:
            log(f"  ❌ No retail trigger words in PDF", 2)

        return found, is_refused

    except Exception as e:
        log(f"  ⚠️  PDF error: {type(e).__name__}: {e}", 2)
        return [], False

# ════════════════════════════════════════════════════════════
# PROCESS ONE APPLICATION
# ════════════════════════════════════════════════════════════
def process_app(sess, base_url, council, item):
    kv  = item["keyVal"]
    ref = item["ref"]
    log(f"")
    log(f"  ──────────────────────────────────────────────")
    log(f"  📋 {ref}")
    log(f"  {item['desc'][:90]}")

    det = get_details(sess, base_url, kv)

    # Pre-filter 0: skip post-approval admin applications immediately
    # These are NOT project approvals — they're condition discharge / reserved matters.
    # Mark confirmed: "discharge of condition" and "approval of details reserved by
    # condition" are not leads, even if refused.
    desc_lower = item["desc"].lower()
    _not_leads = (
        "discharge of condition",
        "discharge of planning condition",
        "reserved matters",
        "approval of details",
        "approval of reserved",
        "details reserved by condition",
        "condition discharge",
        "prior approval",          # permitted development prior approval — not a lead
        "lawful development",      # LDC application — not a lead
        "certificate of lawful",
        "advertisement consent",   # signage only — not a lead
        "listed building consent", # heritage only — not a lead
        "tree preservation",       # TPO application — not a lead
        "hedgerow removal",
        "non-material amendment",   # minor wording change to an approved app — not a lead
        "minor material amendment", # s73 variation — amending existing consent
        "section 73",               # s73 applications — variation of condition
        "s73",                      # abbreviated form used in many descriptions
        "screening opinion",        # EIA screening — pre-application, not a decision
        "scoping opinion",          # EIA scoping — pre-application
        "environmental impact assessment screening",
        "prior notification",          # forestry/agri permitted dev — not a lead
        "class ma",                    # office-to-resi prior approval — not a lead
        "part 6",                      # agricultural/forestry PD — not a lead
        "part 7",                      # demolition permitted development — not a lead
        "notification under",          # catches "notification under Class MA/Part 6" etc
        "prior notification under",    # belt-and-braces for PNA applications
        "telecommunications",          # phone masts — not a retail lead
        "street works",                # highway works — not a lead
        "temporary structure",         # events/markets — not a lead
    )
    if any(bad in desc_lower for bad in _not_leads):
        log(f"  ⏭️  Not a project approval (post-approval admin / non-planning) — skip", 2)
        return None

    # Pre-filter 1: skip clearly non-refused decisions immediately
    decision_raw = det.get("decision", "").lower().strip()
    if decision_raw and any(w in decision_raw for w in _APPROVAL_WORDS):
        log(f"  ⏭️  Decision='{det.get('decision','')}' — not a refusal, skip", 2)
        return None

    # If portal says "Refused" explicitly, log it — scan_pdf is still the final gate
    if decision_raw and any(w in decision_raw for w in ("refus", "refuse")):
        log(f"  ✅ Portal confirms refusal: '{det.get('decision','')}'", 2)

    doc_url, prefetched  = find_decision_doc(sess, base_url, kv)
    if not doc_url:
        log(f"  ⚠️  No decision doc — skip")
        return None

    triggers, is_refused = scan_pdf(sess, doc_url, prefetched_response=prefetched)

    # Gate 1: must have explicit refusal language in PDF
    if not is_refused:
        # Fallback: check the decision field from the portal itself
        decision_raw = det.get("decision", "").lower()
        portal_refused = any(w in decision_raw for w in ("refus", "refuse", "refused"))
        if not portal_refused:
            log(f"  ❌ Not confirmed as refused (PDF + portal both lack refusal language) — skip")
            return None
        else:
            log(f"  ✅ Refusal confirmed via portal decision field: '{det.get('decision','')}'")

    # Gate 2: must have retail planning trigger words
    if not triggers:
        log(f"  ❌ No retail trigger words — not a retail impact refusal")
        return None

    log(f"  🏆 QUALIFIED — Triggers: {triggers}")
    desc = det.get("proposal", item["desc"])
    sc   = score_lead(desc, triggers)
    log(f"  Score: {sc}/100")

    # ── Minimum score gate ────────────────────────────────────────────────
    # Discard low-quality matches that only matched generic policy phrases.
    # Genuine winnable leads always score 60+ (evidence or sequential trigger
    # alone pushes base 40 + desc signal well above this threshold).
    if sc < MIN_LEAD_SCORE:
        log(f"  ⏭️  Score {sc} < {MIN_LEAD_SCORE} minimum — skipping (not a qualified lead)")
        return None

    # Normalise decision to canonical status using shared helper
    raw_dec        = det.get("decision", "").strip()
    decision_status = _normalise_decision(raw_dec) if raw_dec else "REFUSED"

    lead = {
        "council":   council,
        "ref":       ref,
        "addr":      det.get("address",   item["addr"]),
        "desc":      desc,
        "app_type":  det.get("app_type",  ""),
        "applicant": det.get("applicant", ""),
        "agent":     det.get("agent",     ""),
        "date_rec":  det.get("date_rec",  ""),
        "date_dec":  det.get("date_dec",  ""),
        "decision":  decision_status,
        "triggers":  ", ".join(triggers),
        "score":     sc,
        "keyword":   item["keyword"],
        "url":       f"{base_url}/applicationDetails.do?activeTab=summary&keyVal={kv}",
        "doc_url":   doc_url,
    }
    # Sales intelligence enrichment
    enrich_lead(lead)
    write_lead(lead)
    return lead

# ════════════════════════════════════════════════════════════
# SCRAPE ONE COUNCIL
# ════════════════════════════════════════════════════════════
def scrape_council(council, base_url, date_from, date_to):
    log(f"\n{'='*60}")
    log(f"🏛️  {council.upper()}  |  {date_from} → {date_to}")
    log(f"{'='*60}")

    sess      = new_session()
    all_items = []
    qualified = []

    # Warm up the session before any keyword search.
    # This seeds JSESSIONID from the portal root and accepts any disclaimer,
    # preventing the 403-on-POST that occurs with cold sessions.
    log(f"  🔥 Warming session…", 1)
    if not _warmup_portal_session(sess, base_url):
        log(f"  ❌ Session warmup failed — {council} unreachable, skipping")
        return []

    for kw in RETAIL_KEYWORDS:
        try:
            items = search_one_keyword(sess, base_url, kw, date_from, date_to)
            new   = [i for i in items
                     if i["keyVal"] not in {x["keyVal"] for x in all_items}]
            for i in new:
                i["keyword"] = kw
            all_items.extend(new)
            time.sleep(1)
        except Exception as e:
            log(f"  ❌ Keyword '{kw}': {e}")

    log(f"\n  {len(all_items)} unique applications to scan")

    if not all_items:
        return []

    for idx, item in enumerate(all_items):
        log(f"\n  [{idx+1}/{len(all_items)}]")
        try:
            lead = process_app(sess, base_url, council, item)
            if lead:
                qualified.append(lead)
        except Exception as e:
            log(f"  ❌ {item.get('ref','?')}: {e}")
        time.sleep(1)

    log(f"\n✅ {council}: {len(qualified)} qualified leads")
    return qualified

# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════
def run():
    run_start = datetime.now()
    today     = datetime.now()
    date_to   = today.strftime("%d/%m/%Y")
    date_from = (today - timedelta(weeks=WEEKS_TO_SCRAPE)).strftime("%d/%m/%Y")

    print("=" * 60)
    print(f"🏗️  MAPlanning Retail Lead Engine v20")
    print(f"📅  {today.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📆  {date_from} → {date_to}  ({WEEKS_TO_SCRAPE} weeks)")
    print(f"🏛️  {len(COUNCILS)} councils configured")
    print(f"🔎  {', '.join(RETAIL_KEYWORDS)}")
    print("=" * 60)

    # ── Step 1: connect to Sheets & load existing refs ──────
    if not get_sheet():
        print("❌ Sheets connection failed — stopping"); return
    load_existing_refs()

    # ── Step 2: pre-flight — fast parallel check ───────────
    live_councils, _dead = preflight_check(COUNCILS)
    if not live_councils:
        print("❌ No reachable councils — check network"); return

    # ── Step 3: scrape every live council ───────────────────
    import random
    grand   = []
    summary = {}
    failed  = []
    total   = len(live_councils)

    for idx, (name, url) in enumerate(live_councils.items()):
        log(f"\n{'━'*60}")
        log(f"Council {idx+1}/{total}: {name}")
        log(f"{'━'*60}")
        try:
            leads = scrape_council(name, url, date_from, date_to)
            summary[name] = len(leads)
            grand.extend(leads)
        except Exception as e:
            log(f"❌ {name}: {str(e)[:80]}")
            failed.append(name)
            summary[name] = 0

        if idx < total - 1:
            pause = random.uniform(2, 4)
            log(f"⏸️  {pause:.1f}s | {total-idx-1} remaining | {len(grand)} leads so far")
            time.sleep(pause)

    grand.sort(key=lambda x: x["score"], reverse=True)

    run_duration_min = (datetime.now() - run_start).total_seconds() / 60

    # ── Step 4: count leads added in the past 7 days from the sheet ────────
    # This runs AFTER scraping so newly-written leads are included in the count.
    weekly_count, weekly_leads = get_weekly_lead_count()

    # ── Final report ─────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"📊 FINAL RESULTS")
    print(f"{'='*60}")

    print(f"\n  Run duration: {run_duration_min:.1f} minutes")
    print(f"  Councils attempted:  {total}")
    print(f"  New leads this run:  {len(grand)}")
    print(f"  Leads (past 7 days, including previous runs): {weekly_count}")

    print(f"\n  Council breakdown:")
    for c, n in summary.items():
        mark = "❌ FAILED" if c in failed else f"🏆 {n} leads" if n else "  0"
        print(f"    {c:25s}: {mark}")

    if failed:
        print(f"\n  Failed during scrape ({len(failed)}):")
        for fc in failed:
            print(f"    {fc}")

    print(f"\n  {'─'*36}")
    print(f"  {'NEW LEADS THIS RUN':25s}: {len(grand)}")
    print(f"  {'LEADS PAST 7 DAYS':25s}: {weekly_count}")
    print(f"{'='*60}")

    if grand:
        print(f"\n🏆 TOP NEW LEADS:")
        for lead in grand[:10]:
            print(f"\n  [{lead['score']}pts] {lead['council']} | {lead['ref']}")
            print(f"  {lead['addr']}")
            print(f"  {lead['desc'][:100]}")
            print(f"  Triggers: {lead['triggers']}")
            print(f"  {lead['url']}")

    # ── Email digest — sent AFTER scraper fully completes ───────────────────
    # Conditions before sending:
    #   1. Must be in automated mode (GMAIL_APP_PASSWORD set)
    #   2. Must have scraped at least some councils (run_duration > 1 min
    #      guards against spurious fast crashes triggering email)
    #   3. Send regardless of 0 new leads — weekly_count from sheet still
    #      makes the email useful (shows what was already found)
    if os.environ.get("GMAIL_APP_PASSWORD"):
        councils_with_results = sum(1 for n in summary.values() if n >= 0)  # any attempted
        if run_duration_min < 1.0 and len(grand) == 0:
            log("⚠️  Run completed in < 1 min with 0 leads — suppressing email (likely startup failure)")
        else:
            log("\n📧 Sending email digest (run complete)…")
            email_digest.send_digest(
                grand, summary, failed,
                date_from, date_to,
                weekly_count=weekly_count,
                weekly_leads=weekly_leads,
                run_duration_min=run_duration_min,
                log_fn=log,
            )
    else:
        log("ℹ️  Email skipped (Colab mode — set GMAIL_APP_PASSWORD for automated emails)")

# ── Authenticate Google ──────────────────────────────────────
# In GitHub Actions: GCP_SERVICE_ACCOUNT_JSON env var is set — no action needed here.
# In Colab: trigger interactive auth so default() works.
if not os.environ.get("GCP_SERVICE_ACCOUNT_JSON"):
    try:
        from google.colab import auth
        auth.authenticate_user()
        print("✅ Google Colab auth done")
    except Exception:
        pass  # already authenticated or running locally

run()
