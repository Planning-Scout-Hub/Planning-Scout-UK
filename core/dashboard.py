# PlanningScout UK — MAPlanning Dashboard
# Adapted from PlanningScout ES (Spanish) for UK retail planning intelligence
# Same design system: Fraunces / Plus Jakarta Sans / JetBrains Mono
# Navy #003049  /  Amber #c8860a  /  Green #16a34a

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime, timedelta
import re
import hashlib
import hmac as _hmac_mod
import secrets as _secrets_mod
import os
import base64
import html as _html_esc

# ══════════════════════════════════════════════════════════════
# SESSION TOKENS — stateless, signed, 12-hour expiry
# ══════════════════════════════════════════════════════════════
_SESSION_HOURS = 12
SHEET_ID = "172bpv-b2_nK5ENE1XPk5rWeokvnr1sjHvLBfVzHWh6c"  # MAPlanning sheet

def _secret():
    try: return str(st.secrets.get("SESSION_SECRET", "ps-uk-2026"))
    except: return "ps-uk-2026"

def _make_tok(email, role):
    exp = int((datetime.now() + timedelta(hours=_SESSION_HOURS)).timestamp())
    payload = f"{email}|{role}|{exp}"
    sig = _hmac_mod.new(_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode().rstrip("=")

def _verify_tok(token):
    try:
        raw = base64.urlsafe_b64decode((token + "=" * (-len(token) % 4)).encode()).decode()
        payload, sig = raw.rsplit(".", 1)
        exp_sig = _hmac_mod.new(_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
        if not _hmac_mod.compare_digest(sig, exp_sig): return None, None
        email, role, exp = payload.split("|")
        if datetime.now().timestamp() > float(exp): return None, None
        return email, role
    except: return None, None

# ══════════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="PlanningScout UK — MAPlanning",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════
# COLUMN MAPS — maps Google Sheet column names → internal keys
# "Leads" tab: refused applications (appeal service)
# "New Applications" tab: pending apps with competitors (objection service)
# ══════════════════════════════════════════════════════════════
COL_MAP_LEADS = {
    "Council":              "council",
    "Reference":            "ref",
    "Address":              "addr",
    "Description":          "desc",
    "App Type":             "app_type",
    "Applicant":            "applicant",
    "Agent":                "agent",
    "Date Received":        "date_rec",
    "Date Decided":         "date_dec",
    "Decision":             "decision",
    "Trigger Words":        "triggers",
    "Score":                "score_raw",
    "Keyword":              "keyword",
    "Portal Link":          "portal_url",
    "Decision Doc URL":     "doc_url",
    "Date Found":           "date_found",
    "Mark's Comments":      "notes",
    "Est. Project Value":   "est_value",
    "Developer":            "developer",
    "Architect":            "architect",
    "Impact Probability":   "impact_prob",
    "CH Number":            "ch_number",
    "Registered Address":   "reg_address",
    "Contact Link":         "ch_link",
    "Days to Appeal":       "days_to_appeal",
    "Appeal Urgency":       "appeal_urgency",
}

COL_MAP_NEW = {
    "Council":                          "council",
    "Reference":                        "ref",
    "Address":                          "addr",
    "Proposal":                         "desc",
    "Applicant":                        "applicant",
    "Date Received":                    "date_rec",
    "Competitor Count":                 "comp_count",
    "Competitors (name + distance)":    "competitors",
    "AI Objection Draft (preview)":     "objection_preview",
    "Objection Quality":                "obj_quality",
    "Status":                           "status",
}

# ══════════════════════════════════════════════════════════════
# DESIGN TOKENS
# ══════════════════════════════════════════════════════════════
NAVY   = "#003049"
AMBER  = "#c8860a"
GREEN  = "#16a34a"
RED    = "#dc2626"
GREY   = "#64748b"
LIGHT  = "#f0f4f8"

def esc(v): return _html_esc.escape(str(v or ""))

def parse_score(v):
    try:
        s = str(v).strip().replace("%","")
        return max(0, min(100, int(float(s))))
    except: return 0

def _score_color(sc):
    if sc >= 80: return GREEN
    if sc >= 60: return AMBER
    return GREY

def _score_circle(sc):
    c = _score_color(sc)
    return (
        f'<div style="width:46px;height:46px;border-radius:50%;background:{c};'
        f'display:flex;align-items:center;justify-content:center;flex-shrink:0;">'
        f'<span style="font-size:11px;font-weight:700;color:#fff;line-height:1;">'
        f'{sc}<br>'
        f'<span style="font-size:8px;font-weight:500;opacity:.85;">pts</span>'
        f'</span></div>'
    )

def _urgency_badge(days_str):
    """Return coloured badge for appeal window."""
    if not days_str or days_str == "Unknown": return ""
    dl = str(days_str).lower()
    if "urgent" in dl or "closed" in dl:
        col, bg = "#dc2626", "#fef2f2"
    elif "window closed" in dl:
        col, bg = "#94a3b8", "#f8fafc"
    else:
        col, bg = GREEN, "#f0fdf4"
    return (
        f'<span style="font-size:10px;font-weight:600;color:{col};background:{bg};'
        f'border:1px solid {col}33;border-radius:100px;padding:2px 8px;">'
        f'{esc(days_str[:55])}</span>'
    )

def _decision_badge(decision):
    d = str(decision or "").upper()
    if "REFUSED" in d:
        return (f'<span style="font-size:10px;font-weight:700;color:#dc2626;background:#fef2f2;'
                f'border:1px solid #fca5a5;border-radius:100px;padding:2px 8px;">REFUSED ✗</span>')
    if "GRANTED" in d or "APPROVED" in d:
        return (f'<span style="font-size:10px;font-weight:600;color:#16a34a;background:#f0fdf4;'
                f'border:1px solid #86efac;border-radius:100px;padding:2px 8px;">APPROVED ✓</span>')
    if "APPEAL" in d:
        return (f'<span style="font-size:10px;font-weight:600;color:#c8860a;background:#fffbeb;'
                f'border:1px solid #fcd34d;border-radius:100px;padding:2px 8px;">APPEAL ⚡</span>')
    return (f'<span style="font-size:10px;font-weight:600;color:#64748b;background:#f8fafc;'
            f'border:1px solid #e2e8f0;border-radius:100px;padding:2px 8px;">{esc(decision)}</span>')

def _quality_badge(q):
    q = str(q or "")
    if "HIGH" in q: bg, c = "#f0fdf4", "#16a34a"
    elif "MEDIUM" in q: bg, c = "#fffbeb", "#c8860a"
    else: bg, c = "#f8fafc", "#64748b"
    return (f'<span style="font-size:10px;font-weight:600;color:{c};background:{bg};'
            f'border:1px solid {c}33;border-radius:100px;padding:2px 8px;">{esc(q[:50])}</span>')

# ══════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════
def inject_css():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;0,9..144,700&family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background: #f0f4f8 !important;
    font-family: 'Plus Jakarta Sans', system-ui, sans-serif !important;
}
[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1.5px solid #e2e8f0 !important;
}
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"], header { display: none !important; }
.block-container { padding: 20px 24px 60px !important; max-width: 1100px !important; }

/* Tabs */
[data-testid="stTabs"] button {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-size: 13px !important; font-weight: 500 !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #003049 !important; border-bottom-color: #003049 !important;
}

/* Cards */
details > summary { list-style: none; cursor: pointer; }
details > summary::-webkit-details-marker { display: none; }

/* Inputs */
.stTextInput > div > div > input,
.stSelectbox > div > div { border-radius: 8px !important; }
.stSlider label, .stNumberInput label {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 10px !important; color: #94a3b8 !important;
    letter-spacing: .1em !important; text-transform: uppercase !important;
}

/* Buttons */
.stButton > button {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-weight: 600 !important; border-radius: 8px !important;
    font-size: 13px !important;
}
.stDownloadButton > button {
    background: #fff !important; color: #003049 !important;
    border: 1.5px solid #003049 !important; border-radius: 10px !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-weight: 600 !important;
}

/* Selectbox: disable free-text typing */
div[data-baseweb="select"] input { caret-color: transparent !important; pointer-events: none !important; }

@media (max-width: 768px) {
    .block-container { padding: 12px 12px 60px !important; }
}
</style>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# LOGO
# ══════════════════════════════════════════════════════════════
def load_logo():
    for p in ["navbar.png", "core/navbar.png", "dashboard/navbar.png"]:
        try:
            with open(p, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            return f'<img src="data:image/png;base64,{b64}" style="width:160px;height:auto;" alt="PlanningScout">'
        except: continue
    return '<span style="font-size:15px;font-weight:700;color:#003049;">⚖️ PlanningScout UK</span>'

LOGO_HTML = load_logo()

# ══════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════
@st.cache_data(ttl=300)
def load_sheet_data():
    """Load both Leads and New Applications tabs. Returns (df_leads, df_new)."""
    try:
        sa = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(sa, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ])
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(st.secrets.get("SHEET_ID", SHEET_ID))

        # Tab 1: Leads (refused applications — appeal service)
        try:
            ws1 = sh.worksheet("Leads")
            d1  = ws1.get_all_records()
            df1 = pd.DataFrame(d1) if d1 else pd.DataFrame()
        except: df1 = pd.DataFrame()

        # Tab 2: New Applications (competitor alert — objection service)
        try:
            ws2 = sh.worksheet("New Applications")
            d2  = ws2.get_all_records()
            df2 = pd.DataFrame(d2) if d2 else pd.DataFrame()
        except: df2 = pd.DataFrame()

        return df1, df2
    except Exception as ex:
        st.error(f"Could not connect to Google Sheets: {ex}")
        return pd.DataFrame(), pd.DataFrame()

# ══════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════
inject_css()

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
    st.session_state["user_email"]    = ""

if not st.session_state["authenticated"]:
    # ── Login card ──────────────────────────────────────────
    st.markdown("""
<style>
[data-testid="stSidebar"] { display: none !important; }
.block-container {
    background: #fff !important; border-radius: 20px !important;
    border: 1px solid #e2e8f0 !important;
    box-shadow: 0 4px 32px rgba(0,0,0,.09) !important;
    padding: 40px 36px 36px !important; max-width: 420px !important;
    margin: 8vh auto 0 !important;
}
[data-testid="stForm"] { background: transparent !important; border: none !important; padding: 0 !important; }
.stTextInput > div > div > input { background: #f8fafc !important; }
</style>""", unsafe_allow_html=True)

    st.markdown(f'<div style="text-align:center;margin-bottom:24px;">{LOGO_HTML}</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<h2 style="font-family:\'Fraunces\',Georgia,serif;font-size:22px;font-weight:700;'
        'color:#003049;text-align:center;margin:0 0 6px;">Sign in</h2>'
        '<p style="text-align:center;font-size:13px;color:#64748b;margin:0 0 24px;">'
        'MAPlanning Retail Lead Intelligence</p>',
        unsafe_allow_html=True
    )
    with st.form("login_form"):
        email = st.text_input("Email", placeholder="mark@maplanning.co.uk")
        pwd   = st.text_input("Password", type="password", placeholder="••••••••")
        submitted = st.form_submit_button("Sign in →", use_container_width=True)
        if submitted:
            _users = {}
            try:
                _su = st.secrets.get("users", {})
                _users = {k.strip().lower(): v for k, v in dict(_su).items()} if _su else {}
            except: pass
            if email.strip().lower() in _users and _users[email.strip().lower()] == pwd:
                st.session_state["authenticated"] = True
                st.session_state["user_email"]    = email.strip().lower()
                st.rerun()
            else:
                st.error("Invalid email or password.")
    st.stop()

# ══════════════════════════════════════════════════════════════
# LOAD DATA
# ══════════════════════════════════════════════════════════════
with st.spinner("Loading planning intelligence…"):
    df_raw_leads, df_raw_new = load_sheet_data()

# Rename columns
df_leads = df_raw_leads.rename(
    columns={k: v for k, v in COL_MAP_LEADS.items() if k in df_raw_leads.columns}
) if not df_raw_leads.empty else pd.DataFrame()

df_new = df_raw_new.rename(
    columns={k: v for k, v in COL_MAP_NEW.items() if k in df_raw_new.columns}
) if not df_raw_new.empty else pd.DataFrame()

# Parse score
if not df_leads.empty and "score_raw" in df_leads.columns:
    df_leads["score"] = df_leads["score_raw"].apply(parse_score)
else:
    if not df_leads.empty: df_leads["score"] = 0

if not df_new.empty and "comp_count" in df_new.columns:
    df_new["comp_count_n"] = pd.to_numeric(df_new["comp_count"], errors="coerce").fillna(0)
else:
    if not df_new.empty: df_new["comp_count_n"] = 0

# ══════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(LOGO_HTML, unsafe_allow_html=True)
    st.markdown('<div style="height:1px;background:#e2e8f0;margin:14px 0 16px;"></div>', unsafe_allow_html=True)

    # View selector
    st.markdown(
        '<p style="font-family:\'JetBrains Mono\',monospace;font-size:10px;'
        'color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;margin:0 0 10px;">View</p>',
        unsafe_allow_html=True
    )
    _view = st.radio(
        "View", ["⚖️  Refused Applications", "🏪  Competitor Alerts"],
        label_visibility="collapsed",
    )
    IS_NEW_APPS = "Competitor" in _view

    st.markdown('<div style="height:1px;background:#e2e8f0;margin:14px 0 16px;"></div>', unsafe_allow_html=True)
    st.markdown(
        '<p style="font-family:\'JetBrains Mono\',monospace;font-size:10px;'
        'color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;margin:0 0 12px;">Filters</p>',
        unsafe_allow_html=True
    )

    if IS_NEW_APPS:
        # Competitor Alerts filters
        min_comps = st.slider("Min competitors nearby", 0, 10, 1, step=1)
        _qual_opts = ["All", "HIGH", "MEDIUM", "LOW", "INFO"]
        filter_quality = st.selectbox("Objection quality", _qual_opts, label_visibility="visible")
        st.markdown('<div style="height:1px;background:#e2e8f0;margin:14px 0 16px;"></div>',
                    unsafe_allow_html=True)
        # Info box
        st.markdown(
            '<div style="background:#eff8ff;border:1px solid #93c5fd;border-radius:10px;'
            'padding:10px 12px;font-size:12px;color:#1e40af;line-height:1.5;">'
            '🏪 <strong>Competitor Alert mode</strong><br>'
            'Shows NEW planning applications where existing competitors are operating within '
            '1,500m — prime targets for MAPlanning\'s objection service.'
            '</div>', unsafe_allow_html=True
        )
    else:
        # Refused Applications filters
        min_score = st.slider("Minimum score", 0, 100, 60, step=5)

        _COUNCILS_ALL = "All councils"
        _available_councils = (
            sorted(df_leads["council"].dropna().unique().tolist())
            if not df_leads.empty and "council" in df_leads.columns else []
        )
        selected_council = st.selectbox(
            "Council", [_COUNCILS_ALL] + _available_councils,
            label_visibility="visible"
        )

        _TRIGGER_ALL = "Any trigger"
        _TRIGGERS    = [
            "Any trigger",
            "sequential test", "out of centre", "lack of evidence",
            "retail impact", "failed to demonstrate",
        ]
        selected_trigger = st.selectbox("Trigger word", _TRIGGERS, label_visibility="visible")

        _DECISION_OPTS = ["Any decision", "REFUSED", "APPEAL", "GRANTED"]
        selected_decision = st.selectbox("Decision", _DECISION_OPTS, label_visibility="visible")

        st.markdown('<div style="height:1px;background:#e2e8f0;margin:14px 0 16px;"></div>',
                    unsafe_allow_html=True)
        # Info box
        st.markdown(
            '<div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;'
            'padding:10px 12px;font-size:12px;color:#9a3412;line-height:1.5;">'
            '⚖️ <strong>Refused Applications</strong><br>'
            'Retail/Class E applications refused on sequential test, evidence, or impact '
            'grounds — winnable appeal opportunities for MAPlanning.'
            '</div>', unsafe_allow_html=True
        )

    st.markdown('<div style="height:1px;background:#e2e8f0;margin:14px 0 16px;"></div>',
                unsafe_allow_html=True)
    if st.button("🚪 Sign out", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()

# ══════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════
_HEADER_TITLE = "Competitor Alerts" if IS_NEW_APPS else "Refused Applications"
_HEADER_SUB   = (
    "New retail applications where existing operators are within 1,500m"
    if IS_NEW_APPS else
    "Retail / Class E applications refused on sequential test & evidence grounds"
)
st.markdown(
    f'<div style="margin-bottom:16px;">'
    f'<h1 style="font-family:\'Fraunces\',Georgia,serif;font-size:26px;font-weight:700;'
    f'color:#003049;margin:0 0 4px;">{_HEADER_TITLE}</h1>'
    f'<p style="font-size:13px;color:#64748b;margin:0;">{_HEADER_SUB}</p>'
    f'</div>',
    unsafe_allow_html=True
)

# ══════════════════════════════════════════════════════════════
# MAIN CONTENT
# ══════════════════════════════════════════════════════════════
if IS_NEW_APPS:
    # ────────────────────────────────────────────────────────
    # VIEW: COMPETITOR ALERTS
    # ────────────────────────────────────────────────────────
    if df_new.empty:
        st.markdown(
            '<div style="text-align:center;padding:56px 24px;background:#fff;'
            'border:1.5px solid #e2e8f0;border-radius:14px;">'
            '<div style="font-size:40px;">🔍</div>'
            '<h3 style="font-family:\'Fraunces\',serif;font-size:19px;color:#003049;margin:14px 0 8px;">'
            'No competitor alerts yet</h3>'
            '<p style="font-size:13px;color:#64748b;line-height:1.6;">'
            'Run the engine with <code>--mode applications</code> to start scanning.<br>'
            'Requires: <code>GOOGLE_MAPS_API_KEY</code> + <code>OPENAI_API_KEY</code> secrets.'
            '</p></div>', unsafe_allow_html=True
        )
    else:
        # Filter
        df_f = df_new.copy()
        if "comp_count_n" in df_f.columns:
            df_f = df_f[df_f["comp_count_n"] >= min_comps]
        if filter_quality != "All" and "obj_quality" in df_f.columns:
            df_f = df_f[df_f["obj_quality"].astype(str).str.contains(filter_quality, na=False)]

        count = len(df_f)

        # Stats row
        _total_comp = int(df_new["comp_count_n"].sum()) if "comp_count_n" in df_new.columns else 0
        _high_q = df_new[df_new.get("obj_quality","").astype(str).str.contains("HIGH",na=False)].shape[0] if "obj_quality" in df_new.columns else 0
        c1, c2, c3 = st.columns(3)
        for col, val, label, sub in [
            (c1, len(df_new), "New Applications Found", "pending retail apps"),
            (c2, _total_comp, "Competitors Detected", "total within 1,500m"),
            (c3, _high_q,     "High Quality Alerts",  "AI objection ready"),
        ]:
            col.markdown(
                f'<div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;'
                f'padding:16px 20px;">'
                f'<div style="font-family:\'Fraunces\',serif;font-size:28px;font-weight:700;'
                f'color:#003049;">{val}</div>'
                f'<div style="font-size:13px;font-weight:600;color:#0d1a2b;margin:2px 0 2px;">{label}</div>'
                f'<div style="font-size:11px;color:#94a3b8;">{sub}</div>'
                f'</div>', unsafe_allow_html=True
            )

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        st.markdown(
            f'<h2 style="font-family:\'Fraunces\',serif;font-size:17px;font-weight:700;'
            f'color:#003049;margin:0 0 12px;">{count} alert{"s" if count!=1 else ""}</h2>',
            unsafe_allow_html=True
        )

        # Cards
        for _, row in df_f.iterrows():
            _ref   = esc(row.get("ref",""))
            _addr  = esc(row.get("addr",""))
            _desc  = esc(str(row.get("desc",""))[:200])
            _appl  = esc(row.get("applicant",""))
            _coun  = esc(row.get("council",""))
            _comps = esc(str(row.get("competitors","") or ""))
            _cnt   = str(row.get("comp_count","0"))
            _qual  = str(row.get("obj_quality",""))
            _obj   = str(row.get("objection_preview","") or "")
            _stat  = esc(row.get("status","REVIEW"))
            _date  = esc(row.get("date_rec",""))
            _url   = str(row.get("portal_url","") or "")
            if not _url and "addr" in row: _url = ""

            _badge = _quality_badge(_qual)

            card_html = f"""
<div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:14px;
     margin-bottom:10px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.04);">

  <div style="background:#f8fafc;border-bottom:1px solid #e2e8f0;
       padding:10px 16px;display:flex;align-items:center;gap:10px;">
    <div style="width:36px;height:36px;border-radius:8px;background:#003049;
         display:flex;align-items:center;justify-content:center;
         font-size:16px;flex-shrink:0;">🏪</div>
    <div style="flex:1;min-width:0;">
      <div style="font-family:'JetBrains Mono',monospace;font-size:10px;
           color:#94a3b8;">{_coun} · {_date}</div>
      <div style="font-family:'Fraunces',Georgia,serif;font-size:15px;
           font-weight:700;color:#003049;white-space:nowrap;overflow:hidden;
           text-overflow:ellipsis;">{_ref} — {_addr or _desc[:60]}</div>
    </div>
    <div style="display:flex;gap:6px;align-items:center;flex-shrink:0;">
      <span style="font-size:11px;font-weight:700;color:#003049;background:#eff8ff;
            border:1px solid #93c5fd;border-radius:100px;padding:3px 10px;">
        🏷️ {_cnt} competitors
      </span>
      {_badge}
    </div>
  </div>

  <div style="padding:12px 16px;">
    <p style="font-size:13px;color:#334155;margin:0 0 8px;line-height:1.55;">{_desc}</p>
    {"<p style='font-size:12px;color:#64748b;margin:0 0 6px;'><strong>Applicant:</strong> " + _appl + "</p>" if _appl else ""}
    {"<p style='font-size:12px;color:#003049;margin:0 0 8px;'><strong>Competitors within 1,500m:</strong> " + _comps + "</p>" if _comps else ""}
  </div>

  {"<div style='background:#fffbeb;border-top:1px solid #fde68a;padding:10px 16px;font-size:12px;color:#78350f;line-height:1.5;'><strong>AI Objection Draft Preview:</strong><br>" + esc(_obj[:350]) + "…</div>" if _obj else ""}

  <div style="padding:10px 16px;background:#f8fafc;border-top:1px solid #e2e8f0;
       display:flex;gap:8px;flex-wrap:wrap;">
    {"<a href='" + _url + "' target='_blank' style='font-size:12px;font-weight:600;color:#003049;text-decoration:none;border:1px solid #003049;border-radius:6px;padding:4px 10px;'>🔗 Portal</a>" if _url else ""}
    <span style="font-size:12px;color:#64748b;padding:4px 0;">Status: <strong>{_stat}</strong></span>
  </div>
</div>"""
            st.markdown(card_html, unsafe_allow_html=True)

else:
    # ────────────────────────────────────────────────────────
    # VIEW: REFUSED APPLICATIONS (Mark's core service)
    # ────────────────────────────────────────────────────────
    if df_leads.empty:
        st.markdown(
            '<div style="text-align:center;padding:56px 24px;background:#fff;'
            'border:1.5px solid #e2e8f0;border-radius:14px;">'
            '<div style="font-size:40px;">📡</div>'
            '<h3 style="font-family:\'Fraunces\',serif;font-size:19px;color:#003049;margin:14px 0 8px;">'
            'No leads yet</h3>'
            '<p style="font-size:13px;color:#64748b;line-height:1.6;">'
            'Run the engine with <code>python engine_ma.py --weeks 8</code> to backfill.<br>'
            'Check the GitHub Actions logs if the run has completed but nothing appears here.'
            '</p></div>', unsafe_allow_html=True
        )
    else:
        # Apply filters
        df_f = df_leads.copy()
        if "score" in df_f.columns:
            df_f = df_f[df_f["score"] >= min_score]
        if selected_council != "All councils" and "council" in df_f.columns:
            df_f = df_f[df_f["council"] == selected_council]
        if selected_trigger != "Any trigger" and "triggers" in df_f.columns:
            df_f = df_f[df_f["triggers"].astype(str).str.lower().str.contains(
                selected_trigger.lower(), na=False)]
        if selected_decision != "Any decision" and "decision" in df_f.columns:
            df_f = df_f[df_f["decision"].astype(str).str.upper().str.contains(
                selected_decision, na=False)]

        # Sort
        if "score" in df_f.columns:
            df_f = df_f.sort_values("score", ascending=False)

        count = len(df_f)

        # Stats row
        _urgent = df_leads[df_leads.get("days_to_appeal","").astype(str).str.contains("URGENT", na=False)].shape[0] if "days_to_appeal" in df_leads.columns else 0
        _avg_score = int(df_leads["score"].mean()) if not df_leads.empty and "score" in df_leads.columns else 0
        _refused = df_leads[df_leads.get("decision","").astype(str).str.upper().str.contains("REFUS", na=False)].shape[0] if "decision" in df_leads.columns else len(df_leads)
        c1, c2, c3, c4 = st.columns(4)
        for col, val, label, sub, color in [
            (c1, len(df_leads), "Total Leads",      "in database",       "#003049"),
            (c2, _refused,      "Refused",           "clear appeal case", "#dc2626"),
            (c3, _urgent,       "Urgent Appeals",    "< 60 days left",   "#c8860a"),
            (c4, _avg_score,    "Avg Score",         "out of 100",        "#16a34a"),
        ]:
            col.markdown(
                f'<div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;'
                f'padding:16px 20px;">'
                f'<div style="font-family:\'Fraunces\',serif;font-size:28px;font-weight:700;'
                f'color:{color};">{val}</div>'
                f'<div style="font-size:13px;font-weight:600;color:#0d1a2b;margin:2px 0 2px;">{label}</div>'
                f'<div style="font-size:11px;color:#94a3b8;">{sub}</div>'
                f'</div>', unsafe_allow_html=True
            )

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

        # Export CSV
        _hdr_l, _hdr_r = st.columns([3,2])
        with _hdr_l:
            st.markdown(
                f'<h2 style="font-family:\'Fraunces\',serif;font-size:18px;font-weight:700;'
                f'color:#003049;margin:0;">{count} lead{"s" if count!=1 else ""}</h2>',
                unsafe_allow_html=True
            )
        with _hdr_r:
            _csv = df_f.to_csv(index=False).encode("utf-8")
            st.download_button("⬇ Export CSV", _csv,
                               f"maplanning_leads_{datetime.now().strftime('%Y%m%d')}.csv",
                               "text/csv", use_container_width=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        if df_f.empty:
            st.info("No leads match these filters. Try lowering the minimum score or changing the council.")
        else:
            for _, row in df_f.iterrows():
                sc    = parse_score(row.get("score_raw", row.get("score", 0)))
                _ref  = esc(row.get("ref",""))
                _addr = esc(row.get("addr",""))
                _desc = esc(str(row.get("desc",""))[:220])
                _appl = esc(row.get("applicant",""))
                _agt  = esc(row.get("agent","") or "")
                _coun = esc(row.get("council",""))
                _dec_date = esc(row.get("date_dec",""))
                _rec_date = esc(row.get("date_rec",""))
                _dec  = str(row.get("decision","") or "REFUSED")
                _trigs = esc(str(row.get("triggers","") or ""))
                _kw   = esc(str(row.get("keyword","") or ""))
                _est  = esc(str(row.get("est_value","") or ""))
                _prob = esc(str(row.get("impact_prob","") or ""))
                _dta  = str(row.get("days_to_appeal","") or "")
                _ch   = str(row.get("ch_link","") or "")
                _notes = esc(str(row.get("notes","") or ""))
                _portal = str(row.get("portal_url","") or "")
                _doc    = str(row.get("doc_url","") or "")

                _sc_circle = _score_circle(sc)
                _dec_badge = _decision_badge(_dec)
                _urg_badge = _urgency_badge(_dta)
                _sc_color  = _score_color(sc)

                # Build trigger pills
                _trig_pills = ""
                if _trigs:
                    for t in _trigs.split(",")[:4]:
                        t = t.strip()
                        if t:
                            _trig_pills += (
                                f'<span style="font-size:10px;background:#fffbeb;color:#92400e;'
                                f'border:1px solid #fcd34d;border-radius:100px;padding:2px 8px;'
                                f'margin-right:4px;white-space:nowrap;">{esc(t)}</span>'
                            )

                # Links row
                _links = ""
                if _portal:
                    _links += f'<a href="{_portal}" target="_blank" style="font-size:12px;font-weight:600;color:#003049;text-decoration:none;border:1px solid #003049;border-radius:6px;padding:4px 10px;margin-right:6px;">🔗 Portal</a>'
                if _doc:
                    _links += f'<a href="{_doc}" target="_blank" style="font-size:12px;font-weight:600;color:#dc2626;text-decoration:none;border:1px solid #dc2626;border-radius:6px;padding:4px 10px;margin-right:6px;">📄 Decision Notice</a>'
                if _ch:
                    _links += f'<a href="{_ch}" target="_blank" style="font-size:12px;font-weight:600;color:#64748b;text-decoration:none;border:1px solid #e2e8f0;border-radius:6px;padding:4px 10px;margin-right:6px;">🏢 Companies House</a>'

                card_html = f"""
<details style="background:#fff;border:1.5px solid #e2e8f0;border-radius:14px;
  margin-bottom:10px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.04);">
<summary style="padding:12px 16px;cursor:pointer;list-style:none;">
  <div style="display:flex;align-items:flex-start;gap:12px;">
    {_sc_circle}
    <div style="flex:1;min-width:0;">
      <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:#94a3b8;
           margin-bottom:2px;">{_coun} · {_ref} · decided {_dec_date}</div>
      <div style="font-family:'Fraunces',Georgia,serif;font-size:15px;font-weight:700;
           color:#003049;margin-bottom:4px;line-height:1.3;">{_addr or _desc[:70]}</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
        {_dec_badge}
        {_urg_badge}
        {_trig_pills}
      </div>
    </div>
    <div style="text-align:right;flex-shrink:0;">
      {"<div style='font-size:12px;font-weight:600;color:#003049;'>💰 " + _est + "</div>" if _est else ""}
      {"<div style='font-size:11px;color:#64748b;'>Impact: " + _prob + "</div>" if _prob else ""}
    </div>
  </div>
</summary>

<div style="padding:14px 16px;border-top:1px solid #f1f5f9;">
  {"<p style='font-size:13px;color:#334155;line-height:1.55;margin:0 0 10px;'>" + _desc + "</p>" if _desc else ""}

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px;">
    {"<div><span style='font-size:10px;font-family:JetBrains Mono,monospace;color:#94a3b8;text-transform:uppercase;'>Applicant</span><br><span style='font-size:13px;color:#0d1a2b;'>" + _appl + "</span></div>" if _appl else ""}
    {"<div><span style='font-size:10px;font-family:JetBrains Mono,monospace;color:#94a3b8;text-transform:uppercase;'>Agent / Architect</span><br><span style='font-size:13px;color:#0d1a2b;'>" + _agt + "</span></div>" if _agt else ""}
    {"<div><span style='font-size:10px;font-family:JetBrains Mono,monospace;color:#94a3b8;text-transform:uppercase;'>Keyword Match</span><br><span style='font-size:13px;color:#0d1a2b;'>" + _kw + "</span></div>" if _kw else ""}
    {"<div><span style='font-size:10px;font-family:JetBrains Mono,monospace;color:#94a3b8;text-transform:uppercase;'>Date Received</span><br><span style='font-size:13px;color:#0d1a2b;'>" + _rec_date + "</span></div>" if _rec_date else ""}
  </div>

  {"<div style='background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:8px 12px;font-size:12px;color:#9a3412;margin-bottom:10px;'><strong>Mark's Notes:</strong> " + _notes + "</div>" if _notes else ""}

  <div style="display:flex;gap:8px;flex-wrap:wrap;">{_links}</div>
</div>
</details>"""
                st.markdown(card_html, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════
st.markdown(
    '<div style="margin-top:32px;padding:14px 0;border-top:1px solid #e2e8f0;'
    'font-size:11px;color:#94a3b8;text-align:center;font-family:\'JetBrains Mono\',monospace;">'
    'PlanningScout UK · MAPlanning · Data refreshes every 5 minutes'
    '</div>', unsafe_allow_html=True
)
