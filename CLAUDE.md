# CLAUDE.md

Context for future Claude sessions working in this repo. Read this before touching the data layer or building anything that reads/writes leads.

## What this codebase does

`core/engine.py` scrapes ~150 UK council Idox planning portals, scans decision-notice PDFs for retail/Class E policy-failure triggers (sequential test, vitality, evidence gaps, etc.), and writes qualified leads to a single Google Sheet. Two products are served from the same sheet:

- **Appeal service** (existing revenue) — refused applications Mark can offer to appeal.
- **Competitor alert service** (new revenue) — undecided applications with nearby competitors, with a draft objection letter.

`core/dashboard.py` is a Streamlit UI that reads the same sheet. `core/email_digest.py` sends a weekly summary. There is no database — the Google Sheet is the source of truth.

## Storage

**One Google Sheet, two tabs.**

- Sheet ID is hard-coded: `172bpv-b2_nK5ENE1XPk5rWeokvnr1sjHvLBfVzHWh6c` (`core/engine.py:27`).
- Auth via Google Cloud service account JSON: `GCP_SERVICE_ACCOUNT_JSON` env var (GitHub Actions) or `st.secrets["gcp_service_account"]` (dashboard).
- Access library: `gspread`.

| Tab | Written by | Read by | Purpose |
|---|---|---|---|
| `Leads` | `write_lead()` `engine.py:870` | `dashboard.py:269`, email digest | Refused applications → appeal leads |
| `New Applications` | `write_new_application()` `engine.py:3723` | `dashboard.py:276` | Pending applications + competitor alerts |

## The only unique key

**`(Council, Reference)`** — there is no global UUID.

- `Reference` is the council's own application number (e.g. `24/01234/FUL`). Unique within a council, not globally.
- Dedup is in-memory per run via `_existing_refs` (a Python `set` of references), loaded once at engine startup from column B. **It is not council-scoped** — if two councils ever produced the same reference string the engine would dedup them as one. In practice references are council-prefixed so this hasn't happened.
- The `concurrency: maplanning-scrape` block in `run_maplanning.yml` prevents parallel runs from racing on dedup.
- Any API or query that joins these tabs MUST use `(council, ref)` as the composite key.

## `Leads` tab — 32 columns

Canonical header list: `SHEET_HEADERS` at `core/engine.py:696`. **On every engine run, `get_sheet()` rewrites row 1 if it doesn't exactly match `SHEET_HEADERS`**, including clearing ghost columns. If you change the column list, change `SHEET_HEADERS` AND `write_lead()` `row_data` together — there's a length-mismatch guard at `engine.py:923` that aborts the write if they drift.

| # | Column | Type | Source | Notes |
|---|---|---|---|---|
| 1 | Council | str | engine | Display name from `COUNCILS` dict |
| 2 | Reference | str | portal | The council's app ref. Half of the unique key. |
| 3 | Address | str | portal | Site address |
| 4 | Description | str | portal | Proposal text |
| 5 | App Type | str | portal | Full / Householder / Outline / etc. |
| 6 | Applicant | str | portal | |
| 7 | Agent | str | portal | |
| 8 | Date Received | str | portal | **Free-text, format varies per council.** Don't assume ISO. |
| 9 | Date Decided | str | portal | Same caveat |
| 10 | Decision | str | engine | Normalised to `"REFUSED"` or `"APPROVED — <raw>"` via `_normalise_decision()` |
| 11 | Trigger Words | str | engine | Comma-joined PDF triggers (e.g. `"sequential test, no evidence"`) |
| 12 | Score | str | engine | Integer 0-100 (stored as string by gspread) |
| 13 | Keyword | str | engine | The `RETAIL_KEYWORDS` entry that surfaced this app |
| 14 | Portal Link | str | engine | Deep link to council app page |
| 15 | Decision Doc URL | str | engine | Direct link to the scanned PDF |
| 16 | Date Found | str | engine | `YYYY-MM-DD HH:MM` when row was written |
| 17 | **Mark's Comments** | str | **HUMAN** | **NEVER overwrite — see Data Integrity Rules** |
| 18 | AI Evaluation | str | engine | Multi-line markdown: `**Why refused:** … **Appeal grounds:** … **First action:** …` |
| 19 | Winability | str | engine | `HIGH` / `MEDIUM` / `LOW` |
| 20 | Recommended Action | str | engine | One-line next step |
| 21 | Top Trigger | str | engine | Single strongest trigger phrase |
| 22 | Est. Work Time | str | engine | Hours estimate |
| 23 | Days to Appeal | str | engine | Days left in 6-month appeal window, or `"Unknown"` |
| 24 | Appeal Urgency | str | engine | Score 0-100 (as string) |
| 25 | Est. Project Value | str | engine | Formatted GBP string |
| 26 | Developer | str | engine | |
| 27 | Architect | str | engine | |
| 28 | Impact Probability | str | engine | Integer + `"%"` |
| 29 | CH Number | str | engine | Companies House registration |
| 30 | Registered Address | str | engine | From Companies House |
| 31 | Contact Link | str | engine | Companies House profile URL |
| 32 | Is Enforcement | str | engine | `"YES"` for enforcement appeals, else blank |

Rows are colour-coded on write: pale green for REFUSED, pale red otherwise (`engine.py:937`).

The dashboard only surfaces a subset via `COL_MAP_LEADS` (`dashboard.py:61`) — cols 18-21, 22, 32 exist in the sheet but aren't shown in the UI today.

## `New Applications` tab — 11 columns

Created on first run by `_get_or_create_new_apps_tab()` (`engine.py:3692`). **Unlike `Leads`, this tab has no header reconciliation** — if you change the column list, old rows will silently misalign.

| # | Column | Source | Notes |
|---|---|---|---|
| 1 | Council | engine | |
| 2 | Reference | engine | Half of the unique key |
| 3 | Address | engine | **Truncated to 200 chars** |
| 4 | Proposal | engine | **Truncated to 300 chars** |
| 5 | Applicant | engine | |
| 6 | Date Received | engine | |
| 7 | Competitor Count | engine | Integer as string |
| 8 | Competitors (name + distance) | engine | Pipe-joined, max 5: `"Aldi (340m) \| Costa Coffee (820m)"` |
| 9 | AI Objection Draft (preview) | engine | **First 400 chars only of the full draft — full text is NOT persisted** |
| 10 | Objection Quality | engine | `HIGH` / `MEDIUM` / `LOW` / `INFO` |
| 11 | **Status** | **HUMAN** | Engine writes `"REVIEW"` on first insert. **Never overwrite once human edits it.** |

## Data Integrity Rules — NEVER break these

1. **Mark's Comments (Leads col 17) is human-edited. Never overwrite.**
   `write_lead()` writes `""` to col 17 on insert and never touches existing rows. Any new API or sync job MUST preserve cell A17:Z17 contents on existing rows. If you add update-in-place logic, exclude col 17.

2. **New Applications `Status` (col 11) is human-edited after first write.**
   Engine writes `"REVIEW"` on initial insert. Mark moves it through `OBJECTED`, `WON`, `LOST`, etc. Updates to a row must preserve the human-edited Status — if you can't safely update without clobbering, leave the row alone.

3. **`(Council, Reference)` is the only unique key.**
   Never assume row index is stable (rows get sorted / filtered in the UI). Never assume a single-column key. Lookups, updates and dedup must use both fields.

4. **Don't change `SHEET_HEADERS` without updating `write_lead()`'s `row_data`.**
   The engine has a length-mismatch guard (`engine.py:923`) that will refuse to write if they differ. Touch them together, or the engine silently drops leads for an entire run.

5. **Don't add columns to the `New Applications` tab without a migration.**
   It has no header reconciliation. Existing rows will misalign by one column for every column you insert before their position.

6. **Dates are free-text strings, not ISO.**
   Don't `datetime.fromisoformat()` on `Date Received` / `Date Decided`. Format varies per council. The dashboard's `parse_score()` style is the right pattern — try multiple formats, fall back to string.

7. **`Decision` is normalised on write, not on read.**
   `engine.py:_normalise_decision()` produces `"REFUSED"` or `"APPROVED — <raw>"`. Read code can rely on this. If you ever write directly to the sheet, run the same normalisation.

## Known limitations to fix when building further

- **Full AI objection text is lost.** Only the first 400 chars are persisted (col 9 of New Applications). The full draft exists in memory in `process_new_application()` as `lead["ai_objection"]` and is discarded after `write_new_application()`. If a product needs the full draft (re-send, edit, audit), the engine must persist it — options: extra column with full text, or a separate `Objection Drafts` tab keyed by `(council, ref)`.

- **gspread read latency.** `ws.get_all_records()` and `ws.get_all_values()` pull the entire sheet on every call. The dashboard caches inside its Streamlit session, but any API hitting the sheet per request will hit Google's per-minute quota within a handful of users. **Any API tier must add a server-side cache** (60-300 s TTL is a reasonable starting point) or a sync into a real database. Don't expose `gspread` calls 1:1 to an HTTP endpoint.

- **No edit history.** `Date Found` is set once on write. Mark's Comments and Status changes have no timestamp or audit trail. If versioned history matters, it has to live outside the sheet.

- **All values come back as strings.** `gspread.get_all_records()` returns string-typed cells. Numeric fields (Score, Competitor Count, Impact Probability, Appeal Urgency) need parsing on read.

- **In-memory dedup is per-run.** `_existing_refs` is populated once at engine startup from col B. A row added by run A is invisible to run B if it started before A finished. The new workflow `concurrency` block prevents this for the scheduled scraper, but any other writer (API, manual entry) needs to refresh dedup state or trust the sheet's append-then-dedup-later flow.

## Where the engine runs

- **GitHub Actions, weekly Mondays 06:00 UTC**, via `.github/workflows/run_maplanning.yml`. 4-batch matrix (each batch handles ~30 councils). Budget caps: `MAX_RUNTIME_HOURS=2.8` (engine soft-stop), 180-min job timeout (GitHub hard-kill).
- **GitHub Actions manual** for the competitor alert pipeline via `.github/workflows/competitor_alert.yml` (`--mode applications`).
- **Google Colab** for full UK coverage. Actions runs from US IPs and ~25 councils block those — the engine recognises this via preflight, classifies them as `geo_blocked`, and skips them when `SKIP_GEO_BLOCKED=1` is set (set by both workflows). Run from Colab without the flag for full coverage.
