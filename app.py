"""
app.py — BankOS Enterprise Web Application
PRACTICE PROJECT — demo only. Do NOT enter real personal, banking or financial data.
Full Streamlit UI for BankOS v3/v4.

Features:
- Role-based Authentication: Bank Admin (bankadmin/bankadmin), Customer Login, Self-service Password Reset (login page + in-portal sidebar entry for both roles).
- Practice Project Credentials Display: easily inspect demo customer passwords and original passwords.
- Admin Portal: Dashboard Overview, Comprehensive Account CRUD (Create, Freeze, Convert, Daily Limit, Delete),
  Vault Management, Pending Transfers Approval/Rejection Queue, Multi-Log Audit Viewer,
  Unified Database Management (Table Inspector, Schema Viewer, Multi-Format Importer, CSV/XLSX Exporter),
  and PDF Statement Generation.
- Customer Portal: Real-time Account Overview (with dual-currency converted values), Deposit & Withdraw,
  Cross-currency & Threshold-checked Transfers, Credit Card Payback, Secured Vault Operations (Cash & Physical Assets),
  Financial Instruments (Loans, Bonds, Checks), Utility Bill & Government Tax Settlements,
  Transaction History, and Instant PDF Statement Downloads.
"""

from __future__ import annotations

import os
import tempfile
import sqlite3
from datetime import datetime, timedelta
from html import escape as html_escape
from typing import NamedTuple
import pandas as pd
import streamlit as st

from utils_storage import (
    init_storage,
    ensure_log_db,
    authenticate_admin,
    authenticate_customer,
    get_security_question,
    execute_password_reset,
    list_accounts,
    bank_overview,
    create_account,
    delete_account,
    freeze_account,
    set_daily_limit,
    convert_account_type,
    create_vault,
    destroy_vault,
    vault_add,
    vault_deduct,
    add_vault_item,
    add_funds,
    deduct_funds,
    transfer,
    payback_credit,
    get_pending_transfers,
    review_pending,
    get_logs,
    recent_transactions,
    get_billers_by_category,
    pay_biller,
    get_all_table_names,
    import_file_to_table,
    export_accounts_csv,
    export_accounts_xlsx,
    execute_loan_disbursal,
    execute_loan_repayment,
    execute_bond_purchase,
    execute_bond_redemption,
    execute_check_issuance,
    execute_check_clearing,
    execute_check_bouncing,
    verify_vault_auth,
)
from utils_currency import (
    format_money,
    format_money_dual,
    to_minor,
    from_minor,
    convert_minor,
    get_usd_to_bdt_rate,
    min_deposit_for,
    SUPPORTED,
)
from utils_reports import generate_pdf_statement


class Logs(NamedTuple):
    acc: sqlite3.Connection
    tx: sqlite3.Connection
    freeze: sqlite3.Connection
    pending: sqlite3.Connection


def init_dbs() -> tuple[sqlite3.Connection, Logs]:
    """Ensure active SQLite connection and unified logs exist in session state."""
    if "conn" not in st.session_state or st.session_state.conn is None:
        conn = init_storage()
        st.session_state.conn = conn
        acc, tx, freeze, pending = ensure_log_db(conn)
        st.session_state.logs = Logs(acc, tx, freeze, pending)
    return st.session_state.conn, st.session_state.logs


def logout() -> None:
    st.session_state.logged_in = False
    st.session_state.user_type = None
    st.session_state.identifier = None
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
#  Theme (soft blue + deep teal dashboard) and small visual helpers — styling only
# ─────────────────────────────────────────────────────────────────────────────

import functools
import re
import urllib.parse

# ── icon system ──────────────────────────────────────────────────────────────
# Raw emojis in labels are shown as themed Material icons instead. The original
# strings are never changed in the logic (menu comparisons still use them): the
# swap happens at display time only, and silently falls back to the emoji on
# Streamlit versions that cannot render :material/...: shortcodes.

_EMOJI_ICONS = {
    "📊": "dashboard", "👥": "group", "🔐": "lock", "⏳": "hourglass_top", "📜": "receipt_long",
    "🗄": "database", "📄": "description", "🛡": "shield", "👤": "person", "🔑": "key",
    "⚡": "bolt", "📋": "list_alt", "➕": "add_circle", "❄": "ac_unit", "🔄": "sync",
    "⚙": "settings", "🗑": "delete", "💡": "lightbulb", "🏛": "request_quote", "🏠": "home",
    "💰": "payments", "💸": "swap_horiz", "💳": "credit_card", "📈": "trending_up", "🖋": "edit_note",
    "🏦": "account_balance", "📥": "move_to_inbox", "📤": "outbox", "💎": "diamond", "⚠": "warning",
    "✅": "check_circle", "❌": "cancel", "🎉": "celebration", "🔓": "lock_open", "📱": "sms",
    "💱": "currency_exchange", "⬇": "download", "➔": "arrow_right_alt",
}
_EMOJI_RE = re.compile("(" + "|".join(map(re.escape, _EMOJI_ICONS)) + ")[\ufe0f]?")


def _material_supported() -> bool:
    """:material/name: shortcodes in labels need Streamlit >= 1.40."""
    try:
        major, minor = (int(x) for x in st.__version__.split(".")[:2])
        return (major, minor) >= (1, 40)
    except Exception:
        return False


def _ic(text):
    """Replace known emojis in a label/markdown string by Material icon shortcodes."""
    if not isinstance(text, str) or not _material_supported():
        return text
    return _EMOJI_RE.sub(lambda m: f":material/{_EMOJI_ICONS[m.group(1)]}:", text)


def _install_icon_labels() -> None:
    """Route Streamlit's text-taking widgets through _ic(). Display-only; values are untouched."""
    if getattr(st, "_bk_icons_installed", False) or not _material_supported():
        return

    def first_arg(fn, kw="label"):
        @functools.wraps(fn)
        def inner(*a, **k):
            if a:
                a = (_ic(a[0]),) + tuple(a[1:])
            elif kw in k:
                k[kw] = _ic(k[kw])
            return fn(*a, **k)
        return inner

    orig_markdown, orig_tabs, orig_radio = st.markdown, st.tabs, st.radio

    @functools.wraps(orig_markdown)
    def markdown(body, *a, **k):
        raw_html = k.get("unsafe_allow_html", a[0] if a else False)
        return orig_markdown(body if raw_html else _ic(body), *a, **k)

    @functools.wraps(orig_tabs)
    def tabs(tabs, *a, **k):
        return orig_tabs([_ic(t) for t in tabs], *a, **k)

    @functools.wraps(orig_radio)
    def radio(label, options=(), *a, **k):
        if len(a) < 2:  # no positional format_func given
            base = k.pop("format_func", None) or str
            k["format_func"] = lambda o, _b=base: _ic(str(_b(o)))
        return orig_radio(label, options, *a, **k)

    st.markdown, st.tabs, st.radio = markdown, tabs, radio
    for name, kw in (("button", "label"), ("download_button", "label"), ("expander", "label"),
                     ("success", "body"), ("info", "body"), ("warning", "body"), ("error", "body")):
        setattr(st, name, first_arg(getattr(st, name), kw))
    st._bk_icons_installed = True


# Line icons (24px grid, Lucide-style paths) used by the custom HTML / CSS tiles.
_SVG_ICONS = {
    "bank": '<line x1="3" x2="21" y1="22" y2="22"/><line x1="6" x2="6" y1="18" y2="11"/><line x1="10" x2="10" y1="18" y2="11"/>'
            '<line x1="14" x2="14" y1="18" y2="11"/><line x1="18" x2="18" y1="18" y2="11"/><polygon points="12 2 20 7 4 7"/>',
    "snow": '<line x1="2" x2="22" y1="12" y2="12"/><line x1="12" x2="12" y1="2" y2="22"/><path d="m20 16-4-4 4-4"/>'
            '<path d="m4 8 4 4-4 4"/><path d="m16 4-4 4-4-4"/><path d="m8 20 4-4 4 4"/>',
    "hourglass": '<path d="M5 22h14"/><path d="M5 2h14"/><path d="M17 22v-4.172a2 2 0 0 0-.586-1.414L12 12l-4.414 4.414A2 2 0 0 0 7 17.828V22"/>'
                 '<path d="M7 2v4.172a2 2 0 0 0 .586 1.414L12 12l4.414-4.414A2 2 0 0 0 17 6.172V2"/>',
    "wallet": '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"/>'
              '<path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>',
    "cash": '<rect width="20" height="12" x="2" y="6" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M6 12h.01M18 12h.01"/>',
    "swap": '<path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/>',
    "calendar": '<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
}


def _svg(name: str, size: int = 18, stroke: str = "currentColor", sw: float = 2) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="{stroke}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f'{_SVG_ICONS[name]}</svg>'
    )


def _icon_vars_css() -> str:
    """CSS custom properties holding each icon as a data-URI (used as a colourable mask)."""
    out = []
    for name in _SVG_ICONS:
        uri = urllib.parse.quote(_svg(name, 24, "black", 2))
        out.append(f'--ic-{name}:url("data:image/svg+xml,{uri}");')
    return ":root{" + "".join(out) + "}"


_THEME_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');
/*__ICON_VARS__*/

/* overall UI scale: ~90% (same look as 90% browser zoom for text, rem-based spacing and widgets).
   Change 90% to 100% to go back to the original size, or 85% to go smaller still. */
html{font-size:90% !important;}

:root{
  --bk-bg:#d6e7f0; --bk-card:#f8f9fd; --bk-panel:#f5f9fc; --bk-input:#ffffff;
  --bk-line:#c9dce6; --bk-text:#1f3f52; --bk-muted:#5f7b8c;
  --bk-side:#2a546a; --bk-side2:#244a5e; --bk-accent:#51788c; --bk-accent2:#3f6a80; --bk-soft:#b9d2df;
  --bk-mint:#d1ebe1; --bk-mint-b:#9fd3bc; --bk-peach:#f3dccd; --bk-peach-b:#e7b99b;
}

/* helper <style> blocks should not leave an empty gap */
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdownContainer"] > style),
.element-container:has(> [data-testid="stMarkdownContainer"] > style){display:none;}

/* base */
.stApp{
  background:linear-gradient(180deg,#dcebf3 0%,#cde1ec 45%,#bcd5e3 100%) fixed;
  color:var(--bk-text);
  font-family:'Poppins','Segoe UI',system-ui,-apple-system,sans-serif;
}
h1,h2,h3,h4,h5,h6,p,label,li,button,input,textarea,td,th{
  font-family:'Poppins','Segoe UI',system-ui,-apple-system,sans-serif;
}
[data-testid="stHeader"]{background:transparent;}
#MainMenu, footer, .stDeployButton, [data-testid="stToolbar"]{visibility:hidden;}
.block-container, [data-testid="stMainBlockContainer"]{padding-top:1.2rem;max-width:1400px;}
h1{font-size:1.75rem !important;font-weight:700 !important;letter-spacing:-.01em;color:#1f3f52 !important;}
h2,h3,h4{color:#24485c !important;font-weight:600 !important;}
h3{font-size:1.1rem !important;}
[data-testid="stMain"] p, [data-testid="stMain"] li, [data-testid="stMain"] span,
[data-testid="stMain"] [data-testid="stMarkdownContainer"]{color:var(--bk-text);}
hr{border-color:var(--bk-line) !important;}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] *{color:var(--bk-muted) !important;}
[data-testid="stWidgetLabel"] p, label{color:#33566a;font-weight:500;}
:not(pre) > code{background:rgba(81,120,140,.14);color:#2a546a;border-radius:6px;}
::-webkit-scrollbar{width:8px;height:8px;}
::-webkit-scrollbar-thumb{background:#a9c3d1;border-radius:8px;}

/* sidebar = deep teal rail */
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#2d5a71,#244a5e);
  border-right:none;
  box-shadow:6px 0 24px rgba(36,74,94,.18);
}
[data-testid="stSidebar"] > div:first-child{background:transparent;}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3,
[data-testid="stSidebar"] h4{color:#ffffff !important;}
[data-testid="stSidebar"] h3{font-size:.98rem !important;margin-bottom:.2rem;}
[data-testid="stSidebar"] p, [data-testid="stSidebar"] li, [data-testid="stSidebar"] span,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"]{color:#dcebf2;}
[data-testid="stSidebar"] :not(pre) > code{background:rgba(255,255,255,.16);color:#ffffff;}
[data-testid="stSidebar"] hr{border-color:rgba(255,255,255,.16) !important;}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p{
  text-transform:uppercase;letter-spacing:.14em;font-size:.66rem;color:rgba(220,235,242,.6);font-weight:500;
}
[data-testid="stSidebar"] [role="radiogroup"]{gap:2px;}
[data-testid="stSidebar"] [role="radiogroup"] label{
  width:100%;padding:8px 14px;border-radius:12px;border:1px solid transparent;
  cursor:pointer;transition:all .15s ease;box-sizing:border-box;margin:0;
}
/* hide the native radio dot (older DOM: first child div; newer DOM: first div inside the label's content div) */
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child:not(:has(p)),
[data-testid="stSidebar"] [role="radiogroup"] label > div > div:first-child:not(:has(p)){display:none;}
[data-testid="stSidebar"] [role="radiogroup"] label p{color:#dcebf2;font-weight:500;font-size:.9rem;display:flex;align-items:center;gap:10px;line-height:1.25;}
[data-testid="stSidebar"] [role="radiogroup"] label:hover{background:rgba(255,255,255,.1);}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked),
[data-testid="stSidebar"] [role="radiogroup"] label[data-selected="true"]{
  background:#eaf3f8;box-shadow:0 4px 14px rgba(0,0,0,.18);
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p,
[data-testid="stSidebar"] [role="radiogroup"] label[data-selected="true"] p{color:#2a546a;font-weight:600;}
[data-testid="stSidebar"] .stButton > button{
  background:rgba(255,255,255,.08);color:#ffffff;border:1px solid rgba(255,255,255,.35);box-shadow:none;
}
[data-testid="stSidebar"] .stButton > button:hover{background:rgba(255,255,255,.18);color:#ffffff;border-color:#ffffff;box-shadow:none;}

/* brand / profile block (sidebar) + top bar */
.bk-orb{display:inline-block;width:14px;height:14px;border-radius:50%;
  background:radial-gradient(circle at 35% 30%,#a8d8c6,#51788c 60%,#2a546a);
  box-shadow:0 0 0 3px rgba(81,120,140,.18);}
.bk-orb.big{width:38px;height:38px;flex:0 0 38px;}
.bk-brand{display:flex;flex-direction:column;align-items:center;text-align:center;gap:8px;
  padding:8px 4px 16px;margin-bottom:12px;border-bottom:1px solid rgba(255,255,255,.14);}
.bk-avatar{width:72px;height:72px;border-radius:50%;display:grid;place-items:center;color:#2a546a;transition:transform .25s cubic-bezier(.3,1.6,.5,1);
  background:linear-gradient(145deg,#f6fafc,#cfe2ec);border:3px solid #ffffff;
  box-shadow:0 0 0 4px rgba(255,255,255,.22),0 8px 20px rgba(0,0,0,.2);}
.bk-avatar:hover{transform:scale(1.07) rotate(-4deg);}
.bk-brand b{display:block;font-size:1.02rem;color:#ffffff;letter-spacing:.01em;font-weight:600;}
.bk-brand small{color:rgba(220,235,242,.7);font-size:.7rem;letter-spacing:.06em;}
.bk-top{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;
  padding:10px 18px;margin-bottom:16px;border-radius:18px;
  background:var(--bk-card);border:1px solid var(--bk-line);
  box-shadow:0 6px 18px rgba(42,84,106,.08);}
.bk-top-l{display:flex;align-items:center;gap:10px;color:var(--bk-muted);font-size:.92rem;}
.bk-top-l b{color:#1f3f52;font-weight:600;}
.bk-top-l i{opacity:.5;font-style:normal;}
.bk-top-l span:last-child{color:#2a546a;font-weight:500;}
.bk-top-r{display:flex;align-items:center;gap:10px;}
.bk-chip{padding:5px 14px;border-radius:999px;font-size:.76rem;font-weight:500;color:#2f6b57;
  background:var(--bk-mint);border:1px solid var(--bk-mint-b);}
.bk-date{display:inline-flex;align-items:center;gap:7px;padding:6px 14px;border-radius:999px;font-size:.76rem;color:var(--bk-muted);
  background:#eef2f7;border:1px solid #cfdbe5;transition:background .2s,color .2s,border-color .2s;}
.bk-date svg{color:var(--bk-accent);}
.bk-date:hover{background:#e2edf4;color:#1f3f52;border-color:#9fbccd;}
.bk-chip{transition:transform .2s ease;}
.bk-chip:hover{transform:translateY(-1px);}
.bk-bell{width:32px;height:32px;border-radius:50%;display:grid;place-items:center;color:var(--bk-accent);cursor:pointer;
  background:#eef2f7;border:1px solid #cfdbe5;transition:background .2s,color .2s,border-color .2s;}
.bk-bell:hover{background:var(--bk-side);color:#ffffff;border-color:var(--bk-side);}
.bk-bell svg{transform-origin:50% 12%;}
.bk-bell:hover svg{animation:bk-ring .7s ease-in-out;}
@keyframes bk-ring{0%,100%{transform:rotate(0)}20%{transform:rotate(16deg)}40%{transform:rotate(-14deg)}60%{transform:rotate(9deg)}80%{transform:rotate(-6deg)}}

/* login hero */
.bk-hero{text-align:center;padding:1.2rem 0 .6rem;}
.bk-hero h1{margin:.2rem 0 .1rem;}
.bk-hero h1 span{background:linear-gradient(135deg,#2a546a,#4f9aa8);-webkit-background-clip:text;
  background-clip:text;color:transparent;-webkit-text-fill-color:transparent;}
.bk-hero p{color:var(--bk-muted);font-size:1rem;margin:0;}
.bk-logo{width:68px;height:68px;margin:0 auto 10px;border-radius:50%;display:grid;place-items:center;
  font-size:0;line-height:0;color:transparent;transition:transform .25s cubic-bezier(.3,1.6,.5,1);
  background:linear-gradient(145deg,#f6fafc,#cfe2ec);
  border:3px solid #ffffff;
  box-shadow:0 0 0 4px rgba(42,84,106,.18),0 10px 26px rgba(42,84,106,.22);}

.bk-logo::after{content:"";width:32px;height:32px;background-color:#2a546a;
  -webkit-mask:var(--ic-bank) center/contain no-repeat;mask:var(--ic-bank) center/contain no-repeat;}
.bk-logo:hover{transform:scale(1.07) rotate(-4deg);}

/* cards: metrics (KPI tiles), expanders, custom */
[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]){
  background:var(--bk-panel);border-radius:20px;padding:16px;
  box-shadow:0 6px 20px rgba(42,84,106,.08);border:1px solid rgba(255,255,255,.7);
}
[data-testid="stMetric"]{
  position:relative;background:var(--bk-card);border:1.5px solid #bcdccf;border-radius:18px;
  padding:12px 10px 12px 58px;min-height:78px;
  display:flex;flex-direction:column-reverse;justify-content:center;gap:2px;
  box-shadow:0 4px 12px rgba(42,84,106,.06);
}
[data-testid="stMetric"]{--ic:var(--ic-wallet);--ic-fg:#2f7d62;--ic-bg:var(--bk-mint);--ic-bd:var(--bk-mint-b);
  transition:transform .2s ease,box-shadow .2s ease,border-color .2s ease;}
[data-testid="stMetric"]::before, [data-testid="stMetric"]::after{
  content:"";position:absolute;left:10px;top:50%;width:38px;height:38px;border-radius:11px;
  transform:translateY(-50%);transition:transform .25s cubic-bezier(.3,1.6,.5,1),background .2s ease;
}
[data-testid="stMetric"]::before{background:var(--ic-bg);border:1px solid var(--ic-bd);box-sizing:border-box;}
[data-testid="stMetric"]::after{
  background-color:var(--ic-fg);border-radius:0;
  -webkit-mask:var(--ic) center/20px 20px no-repeat;mask:var(--ic) center/20px 20px no-repeat;
}
[data-testid="stMetric"]:hover{transform:translateY(-3px);box-shadow:0 10px 22px rgba(42,84,106,.14);border-color:#9fd3bc;}
[data-testid="stMetric"]:hover::before, [data-testid="stMetric"]:hover::after{transform:translateY(-50%) scale(1.1) rotate(-6deg);}
[data-testid="stMetric"]:hover::before{background:#bfe3d3;}
[data-testid="stColumn"]:nth-child(2) [data-testid="stMetric"]{--ic:var(--ic-swap);}
[data-testid="stHorizontalBlock"]:has(> [data-testid$="olumn"]:nth-child(5)) > [data-testid$="olumn"]:nth-child(1) [data-testid="stMetric"]{--ic:var(--ic-bank);}
[data-testid="stHorizontalBlock"]:has(> [data-testid$="olumn"]:nth-child(5)) > [data-testid$="olumn"]:nth-child(2) [data-testid="stMetric"]{--ic:var(--ic-snow);}
[data-testid="stHorizontalBlock"]:has(> [data-testid$="olumn"]:nth-child(5)) > [data-testid$="olumn"]:nth-child(3) [data-testid="stMetric"]{--ic:var(--ic-hourglass);}
[data-testid="stHorizontalBlock"]:has(> [data-testid$="olumn"]:nth-child(5)) > [data-testid$="olumn"]:nth-child(4) [data-testid="stMetric"]{--ic:var(--ic-wallet);}
[data-testid="stHorizontalBlock"]:has(> [data-testid$="olumn"]:nth-child(5)) > [data-testid$="olumn"]:nth-child(5) [data-testid="stMetric"]{--ic:var(--ic-cash);}
/* attention tile (pending transfers) in the peach tone */
[data-testid="stHorizontalBlock"]:has(> [data-testid$="olumn"]:nth-child(5)) > [data-testid$="olumn"]:nth-child(3) [data-testid="stMetric"]{
  background:#fcf5f0;border-color:#e9cdb9;--ic-fg:#c0693a;--ic-bg:var(--bk-peach);--ic-bd:var(--bk-peach-b);
}
[data-testid="stHorizontalBlock"]:has(> [data-testid$="olumn"]:nth-child(5)) > [data-testid$="olumn"]:nth-child(3) [data-testid="stMetric"]:hover::before{background:#efcdb7;}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p{color:var(--bk-muted) !important;font-size:.72rem;font-weight:500;line-height:1.25;}
[data-testid="stMetric"] [data-testid="stMarkdownContainer"], [data-testid="stMetric"] [data-testid="stMarkdownContainer"] p,
[data-testid="stMetric"] label, [data-testid="stMetricValue"] > div{
  white-space:normal !important;overflow:visible !important;text-overflow:clip !important;overflow-wrap:break-word;word-break:normal;
}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div{
  color:#1f3f52 !important;font-weight:700;font-size:clamp(.82rem,.98vw,1.15rem);line-height:1.2;
}
.bk-card{
  background:var(--bk-card);border:1px solid var(--bk-line);border-radius:18px;padding:16px 20px;
  box-shadow:0 6px 18px rgba(42,84,106,.08);
}
[data-testid="stExpander"] details{
  background:var(--bk-card);border:1px solid var(--bk-line);border-radius:16px;
  box-shadow:0 4px 14px rgba(42,84,106,.06);
}
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary *{color:#ffffff;}
.bk-row{display:flex;flex-wrap:wrap;gap:16px;margin:18px 0 8px;}
.bk-row .bk-card{flex:2 1 360px;min-height:250px;}
.bk-row .bk-card.narrow{flex:1 1 280px;}
.bk-card-t{display:flex;justify-content:space-between;align-items:center;
  color:#1f3f52;font-weight:600;font-size:.95rem;margin-bottom:14px;}
.bk-dots{color:#9bb3c1;font-weight:700;letter-spacing:0;}
.bk-cap{text-align:center;color:var(--bk-muted);font-size:.8rem;margin-top:12px;}

/* donut gauge */
.bk-donut{display:flex;align-items:center;justify-content:center;gap:22px;flex-wrap:wrap;padding-top:4px;}
.bk-gauge{width:140px;height:140px;border-radius:50%;display:grid;place-items:center;flex:0 0 140px;
  background:conic-gradient(var(--bk-accent) var(--deg),var(--bk-soft) 0);}
.bk-gauge-in{width:98px;height:98px;border-radius:50%;background:var(--bk-card);display:flex;
  flex-direction:column;align-items:center;justify-content:center;}
.bk-gauge-in b{font-size:1.4rem;color:#1f3f52;font-weight:700;line-height:1.1;}
.bk-gauge-in span{font-size:.64rem;color:var(--bk-muted);text-transform:uppercase;letter-spacing:.1em;}
.bk-legend{display:flex;flex-direction:column;gap:10px;font-size:.8rem;color:#33566a;}
.bk-legend span{display:flex;align-items:center;gap:8px;}
.bk-legend i{display:inline-block;width:14px;height:14px;border-radius:3px;}
.bk-legend i.dk{background:var(--bk-accent);}
.bk-legend i.lt{background:var(--bk-soft);}

/* horizontal bars */
.bk-hbars{display:flex;flex-direction:column;gap:10px;padding-top:2px;}
.bk-hrow{display:flex;align-items:center;gap:12px;}
.bk-hl{flex:0 0 32%;max-width:32%;font-size:.76rem;color:#33566a;font-weight:500;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.bk-hb{flex:1 1 auto;display:flex;align-items:center;gap:8px;min-width:0;}
.bk-hf{height:9px;border-radius:999px;background:var(--bk-accent);min-width:6px;}
.bk-hv{font-size:.74rem;color:#1f3f52;font-weight:600;white-space:nowrap;}

/* area / line chart */
.bk-line svg{width:100%;height:auto;display:block;}

/* inputs */
div[data-baseweb="input"], div[data-baseweb="base-input"], div[data-baseweb="select"] > div,
[data-testid="stTextArea"] textarea{
  background:var(--bk-input) !important;border-color:#c3d6e1 !important;border-radius:10px !important;
  color:var(--bk-text) !important;
}
div[data-baseweb="input"] input, div[data-baseweb="select"] input, div[data-baseweb="select"] div{color:var(--bk-text);}
div[data-baseweb="select"] svg{fill:var(--bk-accent);}
div[data-baseweb="input"]:focus-within, div[data-baseweb="select"] > div:focus-within{
  border-color:var(--bk-accent) !important;box-shadow:0 0 0 1px rgba(81,120,140,.5);
}
[data-testid="stNumberInput"] button{background:transparent;color:#ffffff;border-color:transparent;}
[data-testid="stNumberInput"] button svg, [data-testid="stTextInput"] button, [data-testid="stTextInput"] button svg{color:#ffffff !important;fill:#ffffff;}
button[aria-label*="password" i], button[aria-label*="password" i] *, [data-testid="stTextInput"] [role="button"], [data-testid="stTextInput"] [role="button"] *, [data-testid="stTextInput"] div[data-baseweb="input"] svg, [data-testid="stTextInput"] div[data-baseweb="input"] svg path{color:#ffffff !important;fill:#ffffff !important;-webkit-text-fill-color:#ffffff !important;opacity:1 !important;}
[data-testid="InputInstructions"]{display:none !important;}
div[data-baseweb="popover"] ul, div[data-baseweb="menu"]{background:#ffffff !important;}
li[role="option"]{color:var(--bk-text);}
li[role="option"]:hover, li[aria-selected="true"]{background:rgba(81,120,140,.14) !important;}
[data-testid="stFileUploaderDropzone"]{background:#f1f7fa;border:1px dashed #9fbccd;border-radius:12px;}
[data-testid="stFileUploaderDropzone"] *{color:#33566a;}
[data-testid="stFileUploaderDropzone"] button{background:#ffffff;color:#2a546a;border:1px solid #9fbccd;}
/* slider: Streamlit paints it in its default primary red; rotate that hue to the teal accent */
[data-testid="stSlider"] [role="group"] > div > div:nth-child(-n+2){filter:hue-rotate(198deg) saturate(.42) brightness(.72);}
[data-testid="stSlider"] [data-baseweb="slider"] > div:nth-child(-n+2){filter:hue-rotate(198deg) saturate(.42) brightness(.72);}
[data-testid="stCheckbox"] [data-baseweb="checkbox"] > div:first-child{border-color:var(--bk-accent);}
[data-testid="stCheckbox"] [data-baseweb="checkbox"]:has(input:checked) > div:first-child{background:var(--bk-side) !important;border-color:var(--bk-side) !important;}
[data-testid="stMain"] [role="radiogroup"] label:has(input:checked) > div:first-child:not(:has(p)),
[data-testid="stMain"] [role="radiogroup"] label:has(input:checked) > div > div:first-child:not(:has(p)),
[data-testid="stMain"] [data-testid="stRadioOption"][data-selected="true"] > div > div:first-child:not(:has(p)){
  background:var(--bk-side) !important;border-color:var(--bk-side) !important;
}

/* buttons */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button{
  border-radius:12px;border:1px solid #9fbccd;background:#ffffff;color:#2a546a;
  font-weight:600;transition:all .15s ease;box-shadow:0 2px 8px rgba(42,84,106,.08);
}
.stButton > button *, .stDownloadButton > button *, .stFormSubmitButton > button *{color:inherit !important;}
.stButton > button:hover, .stDownloadButton > button:hover{
  border-color:var(--bk-accent);background:#eef5f9;color:#1f3f52;box-shadow:0 4px 14px rgba(42,84,106,.16);
}
.stButton > button[kind="primary"], .stButton > button[data-testid="stBaseButton-primary"],
.stFormSubmitButton > button[kind="primary"]{
  background:linear-gradient(135deg,#3f7089,#2a546a);color:#ffffff;border:none;
  box-shadow:0 6px 16px rgba(42,84,106,.28);
}
.stButton > button[kind="primary"] *, .stButton > button[data-testid="stBaseButton-primary"] *,
.stFormSubmitButton > button[kind="primary"] *{color:#ffffff !important;}
.stButton > button[kind="primary"]:hover, .stButton > button[data-testid="stBaseButton-primary"]:hover{
  color:#ffffff;background:linear-gradient(135deg,#477a95,#2f5e76);box-shadow:0 8px 22px rgba(42,84,106,.38);
}

/* tabs as pills (older + newer Streamlit DOM) */
.stTabs [data-baseweb="tab-list"], .stTabs [role="tablist"]{
  gap:6px;background:#e3eef4;padding:5px;border-radius:14px;border:1px solid var(--bk-line);
}
.stTabs [data-baseweb="tab"], .stTabs [role="tab"]{
  height:auto;padding:8px 16px;border-radius:10px;color:var(--bk-muted);background:transparent;position:relative;
}
.stTabs [data-baseweb="tab"] p, .stTabs [role="tab"] p{color:inherit;font-weight:500;}
.stTabs [aria-selected="true"]{background:var(--bk-side);color:#ffffff !important;box-shadow:0 4px 12px rgba(42,84,106,.25);}
.stTabs [aria-selected="true"] p{color:#ffffff !important;}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"],
.stTabs .react-aria-SelectionIndicator{display:none !important;}

/* practice-project warning banner (amber-orange) */
.bk-warn{display:flex;align-items:center;gap:12px;padding:10px 16px;margin:0 0 14px;border-radius:14px;
  background:#fce1ca;border:1px solid #e59a62;color:#6b2e0b;font-size:.82rem;line-height:1.45;
  box-shadow:0 4px 12px rgba(194,65,12,.16);transition:box-shadow .2s ease,transform .2s ease;}
.bk-warn:hover{box-shadow:0 8px 18px rgba(194,65,12,.26);transform:translateY(-1px);}
.bk-warn-ic{flex:0 0 32px;width:32px;height:32px;border-radius:10px;display:grid;place-items:center;
  background:#f8f9fd;border:1px solid #e59a62;color:#c2410c;transition:transform .25s cubic-bezier(.3,1.6,.5,1);}
.bk-warn:hover .bk-warn-ic{transform:scale(1.1) rotate(-6deg);}
.bk-warn b{color:#4a1d04;font-weight:600;}

/* card / chart hover */
.bk-card{transition:transform .2s ease,box-shadow .2s ease;}
.bk-card:hover{transform:translateY(-3px);box-shadow:0 12px 26px rgba(42,84,106,.14);}
.bk-dots{cursor:pointer;border-radius:8px;padding:0 6px;transition:background .2s,color .2s;}
.bk-dots:hover{background:#e3eef4;color:var(--bk-side);}
.bk-hrow .bk-hf{transition:filter .2s ease,transform .2s ease;transform-origin:left center;}
.bk-hrow:hover .bk-hf{filter:brightness(1.2);transform:scaleY(1.35);}
.bk-hrow:hover .bk-hl{color:#1f3f52;}
.bk-gauge{transition:transform .3s cubic-bezier(.3,1.6,.5,1);}
.bk-donut:hover .bk-gauge{transform:scale(1.04) rotate(8deg);}

/* icons: Material icons rendered by Streamlit in labels (tabs, nav, buttons, alerts) */
[aria-label$=" icon"][translate="no"], [data-testid="stIconMaterial"]{
  transition:transform .22s cubic-bezier(.3,1.6,.5,1),background .2s ease,color .2s ease;
  font-size:1.18em;vertical-align:-.22em;margin-right:.1em;
}
/* sidebar nav: icon in a rounded tile that lights up */
[data-testid="stSidebar"] [role="radiogroup"] label [aria-label$=" icon"][translate="no"]{
  display:inline-grid !important;place-items:center;flex:0 0 30px;width:30px;height:30px;font-size:1.05rem;border-radius:10px;margin:0;
  vertical-align:middle;background:rgba(255,255,255,.12);color:#ffffff;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover [aria-label$=" icon"][translate="no"]{
  background:rgba(255,255,255,.26);transform:scale(1.12) rotate(-7deg);
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) [aria-label$=" icon"][translate="no"],
[data-testid="stSidebar"] [role="radiogroup"] label[data-selected="true"] [aria-label$=" icon"][translate="no"]{
  background:var(--bk-side);color:#ffffff;
}
[data-testid="stSidebar"] h3 [aria-label$=" icon"][translate="no"]{
  display:inline-grid !important;place-items:center;width:28px;height:28px;border-radius:9px;margin-right:8px;
  background:rgba(255,255,255,.14);color:#ffffff;font-size:1rem;vertical-align:middle;
}
/* tabs, buttons, expanders, alerts */
.stTabs [role="tab"]:hover [aria-label$=" icon"][translate="no"], .stTabs [data-baseweb="tab"]:hover [aria-label$=" icon"][translate="no"]{
  transform:scale(1.25) rotate(-8deg);
}
.stTabs [role="tab"] [aria-label$=" icon"][translate="no"]{color:var(--bk-accent);}
.stTabs [aria-selected="true"] [aria-label$=" icon"][translate="no"]{color:#ffffff;}
.stButton > button:hover [aria-label$=" icon"][translate="no"], .stFormSubmitButton > button:hover [aria-label$=" icon"][translate="no"]{
  transform:scale(1.25) rotate(-8deg);
}
.stDownloadButton > button:hover [aria-label$=" icon"][translate="no"]{transform:translateY(3px) scale(1.15);}
[data-testid="stExpander"] summary:hover [aria-label$=" icon"][translate="no"]{transform:scale(1.2) rotate(-8deg);}
[data-testid="stExpander"] summary [aria-label$=" icon"][translate="no"]{color:#ffffff;}
[data-testid="stAlert"] [aria-label$=" icon"][translate="no"]{font-size:1.3em;margin-right:.25em;}
[data-testid="stMain"] h1 [aria-label$=" icon"][translate="no"], [data-testid="stMain"] h3 [aria-label$=" icon"][translate="no"]{color:var(--bk-accent);}
@media (prefers-reduced-motion:reduce){
  .bk-card, [data-testid="stMetric"], [data-testid="stMetric"]::before, [data-testid="stMetric"]::after, .bk-avatar, .bk-logo,
  [aria-label$=" icon"][translate="no"]{transition:none !important;animation:none !important;}
  .bk-bell:hover svg{animation:none !important;}
}

/* tables + alerts */
[data-testid="stDataFrame"]{border:1px solid var(--bk-line);border-radius:16px;overflow:hidden;
  background:#ffffff;box-shadow:0 4px 14px rgba(42,84,106,.06);}
[data-testid="stAlert"]{border-radius:14px;}
</style>""".replace("/*__ICON_VARS__*/", _icon_vars_css())

# Only used when the Streamlit base theme is dark (e.g. a dark .streamlit/config.toml):
# lightens the canvas-based tables so they match the light page.
_DARK_BASE_FALLBACK_CSS = (
    '<style>[data-testid="stDataFrame"]{filter:invert(.9) hue-rotate(180deg);}</style>'
)


def inject_theme() -> None:
    """Apply the soft-blue + deep-teal dashboard theme. Styling only."""
    _install_icon_labels()
    st.markdown(_THEME_CSS, unsafe_allow_html=True)
    try:
        base = st.get_option("theme.base")
    except Exception:
        base = None
    if base == "dark":
        st.markdown(_DARK_BASE_FALLBACK_CSS, unsafe_allow_html=True)


def _sidebar_brand() -> None:
    st.markdown(
        '<div class="bk-brand"><div class="bk-avatar">' + _svg("bank", 34, sw=1.8) + '</div>'
        '<div><b>BankOS</b><small>Enterprise Banking</small></div></div>',
        unsafe_allow_html=True,
    )


def _topbar(section: str, role: str) -> None:
    st.markdown(
        '<div class="bk-top"><div class="bk-top-l"><span class="bk-orb"></span>'
        f'<b>BankOS</b><i>/</i><span>{html_escape(_EMOJI_RE.sub("", section).strip())}</span></div>'
        f'<div class="bk-top-r"><span class="bk-chip">{html_escape(role)}</span>'
        f'<span class="bk-date">{_svg("calendar", 14)}{datetime.now():%a, %d %b %Y}</span></div></div>',
        unsafe_allow_html=True,
    )


def _practice_banner() -> None:
    """Persistent notice: this is a demo with fictional data."""
    st.markdown(
        '<div class="bk-warn" role="alert"><span class="bk-warn-ic">' + _svg("alert", 18) + '</span>'
        '<span><b>Practice project — do not enter real data.</b> This app is for demonstration only. '
        'Never type real personal, banking or financial information, or real passwords; '
        'all accounts, balances and credentials shown here are fictional.</span></div>',
        unsafe_allow_html=True,
    )


def _card(title: str, body: str, narrow: bool = False) -> str:
    cls = "bk-card narrow" if narrow else "bk-card"
    return (
        f'<div class="{cls}"><div class="bk-card-t"><span>{html_escape(title)}</span>'
        f'<span class="bk-dots">⋮</span></div>{body}</div>'
    )


def _gauge_html(pct: float, title: str, caption: str, rest_label: str = "Remaining") -> str:
    pct = max(0.0, min(100.0, float(pct)))
    return (
        '<div class="bk-donut">'
        f'<div class="bk-gauge" style="--deg:{pct * 3.6:.1f}deg"><div class="bk-gauge-in">'
        f'<b>{pct:.0f}%</b><span>{html_escape(title)}</span></div></div>'
        '<div class="bk-legend">'
        f'<span><i class="dk"></i>{html_escape(title.title())}</span>'
        f'<span><i class="lt"></i>{html_escape(rest_label)}</span></div></div>'
        f'<div class="bk-cap">{html_escape(caption)}</div>'
    )


def _short_num(v: float) -> str:
    v = abs(float(v))
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v / 1_000:.1f}k"
    return f"{v:.0f}"


def _bars_html(items: list) -> str:
    """items: list of (label, value, display_text). Rendered as horizontal bars."""
    peak = max((abs(float(v)) for _, v, _ in items), default=0) or 1
    rows = []
    for label, val, disp in items:
        w = max(4, round(abs(float(val)) / peak * 100))
        rows.append(
            '<div class="bk-hrow">'
            f'<div class="bk-hl" title="{html_escape(str(label))}">{html_escape(str(label))}</div>'
            '<div class="bk-hb">'
            f'<div class="bk-hf" style="width:{w * 0.78:.1f}%"></div>'
            f'<span class="bk-hv">{html_escape(str(disp))}</span></div></div>'
        )
    return '<div class="bk-hbars">' + "".join(rows) + "</div>"


def _line_html(items: list) -> str:
    """items: list of (label, value, display_text). Smooth area chart with a peak badge."""
    if len(items) < 2:
        return _bars_html(items)
    W, H = 520, 200
    pl, pr, pt, pb = 40, 30, 34, 30
    pw, ph = W - pl - pr, H - pt - pb
    vals = [abs(float(v)) for _, v, _ in items]
    top = (max(vals) or 1) * 1.1
    n = len(items)
    pts = [(pl + pw * i / (n - 1), pt + ph * (1 - v / top)) for i, v in enumerate(vals)]
    base_y = pt + ph

    def clamp_y(y: float) -> float:
        return max(pt - 6, min(base_y, y))

    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(n - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < n else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, clamp_y(p1[1] + (p2[1] - p0[1]) / 6))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, clamp_y(p2[1] - (p3[1] - p1[1]) / 6))
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    area = f"{d} L{pts[-1][0]:.1f},{base_y:.1f} L{pts[0][0]:.1f},{base_y:.1f} Z"

    parts = [
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img">',
        '<defs><linearGradient id="bkArea" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#7fc4aa" stop-opacity=".55"/>'
        '<stop offset="1" stop-color="#7fc4aa" stop-opacity=".04"/></linearGradient></defs>',
    ]
    for k in range(4):
        gy = pt + ph * k / 3
        parts.append(
            f'<line x1="{pl}" y1="{gy:.1f}" x2="{W - pr}" y2="{gy:.1f}" stroke="#b9cdd8" '
            'stroke-width="1" stroke-dasharray="3 4"/>'
            f'<text x="{pl - 8}" y="{gy + 3.5:.1f}" text-anchor="end" font-size="10" fill="#6f8a9a">'
            f'{html_escape(_short_num(top * (1 - k / 3)))}</text>'
        )
    parts.append(f'<path d="{area}" fill="url(#bkArea)"/>')
    parts.append(
        f'<path d="{d}" fill="none" stroke="#5aa58d" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    peak_i = max(range(n), key=lambda i: vals[i])
    for i, (x, y) in enumerate(pts):
        if i == peak_i:
            continue
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#ffffff" stroke="#5aa58d" stroke-width="1.6"/>')
    px, py = pts[peak_i]
    disp = str(items[peak_i][2])
    bw = 8 * len(disp) + 16
    bx = max(pl, min(W - pr - bw, px - bw / 2))
    by = py - 30 if py - 30 >= 2 else py + 10
    parts.append(
        f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw}" height="20" rx="5" fill="#2a546a"/>'
        f'<text x="{bx + bw / 2:.1f}" y="{by + 13.5:.1f}" text-anchor="middle" font-size="10.5" '
        f'font-weight="600" fill="#ffffff">{html_escape(disp)}</text>'
        f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="#2a546a" stroke="#ffffff" stroke-width="2"/>'
    )
    for i, (x, _) in enumerate(pts):
        parts.append(
            f'<text x="{x:.1f}" y="{H - 9}" text-anchor="middle" font-size="10" fill="#6f8a9a">'
            f'{html_escape(str(items[i][0]))}</text>'
        )
    parts.append("</svg>")
    return '<div class="bk-line">' + "".join(parts) + "</div>"


def _render_admin_visuals(conn: sqlite3.Connection, total_accs: int, frozen: int) -> None:
    try:
        rows = conn.execute("SELECT acc_type, COUNT(*) AS cnt FROM accounts GROUP BY acc_type").fetchall()
        items = [(str(r["acc_type"]).replace("_", " ").title(), r["cnt"], str(r["cnt"])) for r in rows]
        pct = (frozen / total_accs * 100) if total_accs else 0
        cards = [_card(
            "Frozen Accounts",
            _gauge_html(pct, "frozen", f"{frozen} of {total_accs} accounts", rest_label="Active"),
            narrow=True,
        )]
        if items:
            cards.append(_card("Accounts by Type", _bars_html(items)))
        st.markdown(f'<div class="bk-row">{"".join(cards)}</div>', unsafe_allow_html=True)
    except Exception:
        pass


def _render_customer_visuals(conn: sqlite3.Connection, logs, row, acc_num: int, currency: str, is_cc: bool) -> None:
    try:
        cards = []
        if is_cc and (row["credit_card_limit"] or 0) > 0:
            used, lim = row["credit_used"] or 0, row["credit_card_limit"]
            cards.append(_card(
                "Credit Utilization",
                _gauge_html(
                    used / lim * 100, "used", f"{format_money(used, currency)} of {format_money(lim, currency)}",
                    rest_label="Available",
                ),
                narrow=True,
            ))
        elif row["vault_no"]:
            vb, bal = row["vault_balance"] or 0, row["acc_balance"] or 0
            pct = vb / (vb + bal) * 100 if (vb + bal) else 0
            cards.append(_card(
                "Vault Reserve",
                _gauge_html(pct, "in vault", f"{format_money(vb, currency)} secured", rest_label="In account"),
                narrow=True,
            ))

        tx = [dict(r) for r in recent_transactions(conn, acc_num, limit=8, tx_log_conn=logs.tx)]
        tx.sort(key=lambda d: str(d.get("timestamp", "")))
        items = [
            (str(d.get("type") or "tx").replace("_", " ")[:8], from_minor(d["amount"]), _short_num(from_minor(d["amount"])))
            for d in tx[-8:]
            if d.get("amount") is not None
        ]
        if items:
            cards.append(_card("Recent Activity", _line_html(items)))
        if cards:
            st.markdown(f'<div class="bk-row">{"".join(cards)}</div>', unsafe_allow_html=True)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  Authentication Screen
# ─────────────────────────────────────────────────────────────────────────────

def render_login() -> None:
    conn, _ = init_dbs()

    st.markdown(
        """
        <div class="bk-hero">
            <div class="bk-logo">🏦</div>
            <h1>BankOS <span>Enterprise</span></h1>
            <p>Secure Digital Core Banking & Asset Management Platform</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<style>.block-container,[data-testid="stMainBlockContainer"]{max-width:1050px;}</style>',
        unsafe_allow_html=True,
    )

    tab_cust, tab_adm, tab_reset = st.tabs(["👤 Customer Login", "🛡️ Bank Admin Login", "🔑 Reset Password"])

    with tab_cust:
        st.subheader("Customer Portal Access")
        col_c1, col_c2 = st.columns([1, 1])
        with col_c1:
            acc_num_in = st.number_input("Account Number", min_value=1, step=1, value=1070, key="cust_acc_in")
            password_in = st.text_input("Account Password", type="password", key="cust_pw_in")
            if st.button("Sign In to Customer Account", type="primary", use_container_width=True):
                res = authenticate_customer(conn, int(acc_num_in), password_in)
                if res["status"] == "success":
                    st.session_state.logged_in = True
                    st.session_state.user_type = "customer"
                    st.session_state.identifier = int(acc_num_in)
                    st.success(res["message"])
                    st.rerun()
                else:
                    st.error(res["message"])

        with col_c2:
            with st.expander("💡 Practice Project Credentials (Demo Accounts)", expanded=True):
                st.markdown(
                    """
                    This is a practice database configured with plaintext original passwords alongside salted hashes:
                    - **Account 1070**: Password `pass1070` *(BDT, Credit Card)*
                    - **Account 1184**: Password `pass1184` *(USD, Non-Credit)*
                    - **Account 1205**: Password `pass1205` *(BDT, Credit Card with Vault)*
                    - **Account 1303**: Password `pass1303` *(BDT, Non-Credit)*
                    - **Account 1333**: Password `pass1333` *(USD, Student Account)*
                    """
                )

    with tab_adm:
        st.subheader("System Administrator Portal")
        st.info("Default Bank Admin credentials: Username: **`bankadmin`** | Password: **`bankadmin`**")
        admin_u = st.text_input("Administrator Username", value="bankadmin", key="admin_u_in")
        admin_p = st.text_input("Administrator Password", type="password", value="bankadmin", key="admin_p_in")
        if st.button("Sign In as Administrator", type="primary", use_container_width=True):
            res = authenticate_admin(conn, admin_u, admin_p)
            if res["status"] == "success":
                st.session_state.logged_in = True
                st.session_state.user_type = "admin"
                st.session_state.identifier = admin_u
                st.success(res["message"])
                st.rerun()
            else:
                st.error(res["message"])

    with tab_reset:
        st.subheader("Self-Service Password Reset")
        st.caption("Reset your password securely by verifying your security question answer.")
        role_type = st.radio("Account Role", ["Customer", "Admin"], horizontal=True, key="reset_role")
        is_admin_reset = (role_type == "Admin")

        if is_admin_reset:
            reset_ident = st.text_input("Admin Username", value="bankadmin", key="reset_admin_id")
        else:
            reset_ident = st.number_input("Account Number", min_value=1, step=1, value=1070, key="reset_cust_id")

        q_res = get_security_question(conn, str(reset_ident) if is_admin_reset else int(reset_ident), is_admin=is_admin_reset)
        if q_res["status"] == "success":
            st.markdown(f"**Security Question:** :blue[{q_res['data']['security_question']}]")
            sec_ans = st.text_input("Your Security Answer", type="password", key="reset_sec_ans")
            new_pw = st.text_input("New Desired Password", type="password", key="reset_new_pw")
            if st.button("Execute Password Reset", type="primary"):
                if not sec_ans or not new_pw:
                    st.warning("Please provide both your security answer and a new password.")
                else:
                    exec_res = execute_password_reset(
                        conn,
                        str(reset_ident) if is_admin_reset else int(reset_ident),
                        sec_ans,
                        new_pw,
                        is_admin=is_admin_reset,
                    )
                    if exec_res["status"] == "success":
                        st.success(f"{exec_res['message']} You can now log in with your new password.")
                    else:
                        st.error(exec_res["message"])
        else:
            st.warning(q_res["message"])


# ─────────────────────────────────────────────────────────────────────────────
#  Shared: in-portal password reset (admin + customer)
# ─────────────────────────────────────────────────────────────────────────────

def render_reset_password_panel(conn: sqlite3.Connection, is_admin: bool) -> None:
    """Reset the *logged-in* user's own password by verifying their security answer.

    Uses the same backend calls as the login-page reset (get_security_question /
    execute_password_reset), so no new storage code is needed. The identity comes
    from the session, so a logged-in user can only reset their own password.
    """
    ident = str(st.session_state.identifier) if is_admin else int(st.session_state.identifier)
    kind = "admin" if is_admin else "customer"

    st.title("Reset Password")
    st.caption("Verify your security question answer to set a new password for your own account.")

    q_res = get_security_question(conn, ident, is_admin=is_admin)
    if q_res["status"] != "success":
        st.warning(q_res["message"])
        return

    st.markdown(f"**Security Question:** :blue[{q_res['data']['security_question']}]")

    with st.form(f"reset_form_{kind}", clear_on_submit=True):
        sec_ans = st.text_input("Your Security Answer", type="password")
        new_pw = st.text_input("New Password", type="password")
        confirm_pw = st.text_input("Confirm New Password", type="password")
        submitted = st.form_submit_button("Execute Password Reset", type="primary")

    if submitted:
        if not sec_ans or not new_pw or not confirm_pw:
            st.warning("Please fill in your security answer, the new password and its confirmation.")
        elif new_pw != confirm_pw:
            st.error("The new password and its confirmation do not match.")
        else:
            res = execute_password_reset(conn, ident, sec_ans, new_pw, is_admin=is_admin)
            if res["status"] == "success":
                st.success(f"{res['message']} Use your new password the next time you log in.")
            else:
                st.error(res["message"])


# ─────────────────────────────────────────────────────────────────────────────
#  Admin Portal
# ─────────────────────────────────────────────────────────────────────────────

def render_admin_portal() -> None:
    conn, logs = init_dbs()

    with st.sidebar:
        _sidebar_brand()
        st.markdown(f"### 🛡️ Bank Admin\n**User:** `{st.session_state.identifier}`")
        menu = st.radio(
            "Navigation",
            [
                "📊 Overview",
                "👥 Account Management",
                "🔐 Vault Management",
                "⏳ Pending Transfers",
                "📜 Audit & Transaction Logs",
                "🗄️ Database Management",
                "📄 Generate Statements",
                "🔑 Reset Password",
            ],
        )
        st.markdown("---")
        if st.button("Log Out", use_container_width=True):
            logout()

    _topbar(menu, f"Admin · {st.session_state.identifier}")

    if menu == "📊 Overview":
        st.title("Platform Statistics & Overview")
        ov = bank_overview(conn, pending_conn=logs.pending)
        totals = ov.get("totals", {})
        frozen = ov.get("frozen_accounts", 0)
        pending = ov.get("pending_count", 0)

        total_accs = conn.execute("SELECT COUNT(*) as c FROM accounts").fetchone()["c"]
        rate = get_usd_to_bdt_rate()

        bdt_pool = totals.get("BDT", 0)
        usd_pool = totals.get("USD", 0)

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Accounts", f"{total_accs:,}")
        m2.metric("Frozen Accounts", f"{frozen:,}")
        m3.metric("Pending Transfers", f"{pending:,}")
        m4.metric("BDT Pool", format_money(bdt_pool, "BDT"))
        m5.metric("USD Pool", format_money(usd_pool, "USD"))

        st.markdown(f"**Live Exchange Rate:** `1 USD = {rate:.2f} BDT` *(Source: `config.json`)*")

        _render_admin_visuals(conn, total_accs, frozen)

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Account Distribution by Type")
            type_rows = conn.execute(
                "SELECT acc_type, COUNT(*) as cnt, SUM(acc_balance) as sum_bal FROM accounts GROUP BY acc_type"
            ).fetchall()
            df_types = pd.DataFrame([dict(r) for r in type_rows])
            if not df_types.empty:
                st.dataframe(df_types, use_container_width=True)
        with col_b:
            st.subheader("System Billers & Authorities")
            billers = conn.execute(
                "SELECT biller_id, biller_name, biller_category, receiving_acc_num FROM billers"
            ).fetchall()
            st.dataframe(pd.DataFrame([dict(b) for b in billers]), use_container_width=True)

    elif menu == "👥 Account Management":
        st.title("Account Management")
        action_tab, list_tab = st.tabs(["⚡ Account Operations", "📋 Accounts Registry"])

        with list_tab:
            filter_choice = st.selectbox(
                "Filter View",
                [
                    "all_account",
                    "credit_card_account",
                    "non_credit_card_account",
                    "vault_account",
                    "non_vault_account",
                    "usd_accounts",
                    "bdt_accounts",
                ],
            )
            raw_accs = list_accounts(conn, filter_choice)
            if raw_accs:
                df = pd.DataFrame([dict(r) for r in raw_accs])
                cols_to_show = [
                    c for c in [
                        "acc_num", "acc_type", "currency", "acc_balance", "original_password",
                        "is_frozen", "daily_transfer_limit", "credit_card_limit", "credit_used",
                        "vault_no", "vault_balance", "parent_name"
                    ] if c in df.columns
                ]
                st.caption(f"Displaying {len(df)} account(s). 'original_password' shown for practice/testing.")
                st.dataframe(df[cols_to_show], use_container_width=True)
            else:
                st.info("No accounts match the selected filter.")

        with action_tab:
            crud_tabs = st.tabs([
                "➕ Create Account", "❄️ Freeze / Unfreeze", "🔄 Convert Type", "⚙️ Daily Limit", "🗑️ Delete Account"
            ])

            with crud_tabs[0]:
                st.subheader("Create New Account")
                c1, c2 = st.columns(2)
                with c1:
                    new_acc = st.number_input("New Account Number", min_value=1000, step=1, value=2001)
                    new_pwd = st.text_input("Account Password", value="pass2001")
                    new_curr = st.selectbox("Currency", list(sorted(SUPPORTED)))
                    new_type = st.selectbox("Account Type", ["non_credit_card", "credit_card", "student"])
                    new_bal = st.number_input("Opening Balance (major units)", min_value=0.0, value=500.0, step=50.0)
                with c2:
                    new_dtl = st.number_input("Daily Transfer Limit (major units)", min_value=100.0, value=5000.0, step=500.0)
                    sec_q = st.text_input("Security Question", value="What is your first pet's name?")
                    sec_a = st.text_input("Security Answer", value="Fluffy")
                    p_name = None
                    p_phone = None
                    if new_type == "student":
                        p_name = st.text_input("Parent/Guardian Name", value="Parent Guardian")
                        p_phone = st.text_input("Parent/Guardian Phone", value="+8801700000000")
                    cc_lim = 0
                    cc_pin = None
                    if new_type == "credit_card":
                        cc_lim = st.number_input("Credit Limit (minor units)", min_value=100000, value=2000000, step=100000)
                        cc_pin = st.text_input("Credit Card PIN (4 digits)", value="1234")

                if st.button("Create Account Now", type="primary"):
                    bal_minor = to_minor(new_bal)
                    dtl_minor = to_minor(new_dtl)
                    res = create_account(
                        conn,
                        int(new_acc),
                        new_pwd,
                        new_curr,
                        new_type,
                        bal_minor,
                        sec_q,
                        sec_a,
                        parent_name=p_name,
                        parent_phone=p_phone,
                        daily_transfer_limit=dtl_minor,
                        credit_card_limit=cc_lim,
                        credit_card_pin=cc_pin,
                    )
                    if res["status"] == "success":
                        st.success(res["message"])
                    else:
                        st.error(res["message"])

            with crud_tabs[1]:
                st.subheader("Freeze or Unfreeze Account")
                accs_list = [r["acc_num"] for r in list_accounts(conn)]
                target_f = st.selectbox("Select Account", accs_list, key="freeze_target")
                freeze_action = st.radio("Action", ["Freeze Account", "Unfreeze Account"], horizontal=True)
                is_freeze = (freeze_action == "Freeze Account")
                reason = st.text_input("Reason / Note", value="Administrative compliance review")
                if st.button("Apply Freeze Status", type="primary"):
                    r = freeze_account(conn, logs.freeze, int(target_f), is_freeze)
                    if r["status"] == "success":
                        st.success(r["message"])
                    else:
                        st.error(r["message"])

            with crud_tabs[2]:
                st.subheader("Convert Account Type")
                accs_list = [r["acc_num"] for r in list_accounts(conn)]
                target_c = st.selectbox("Select Account", accs_list, key="conv_target")
                new_t = st.selectbox("Target Type", ["credit_card", "non_credit_card", "student"], key="conv_t")
                if st.button("Convert Type"):
                    r = convert_account_type(conn, int(target_c), new_t)
                    if r["status"] == "success":
                        st.success(r["message"])
                    else:
                        st.error(r["message"])

            with crud_tabs[3]:
                st.subheader("Modify Daily Transfer Limit")
                accs_list = [r["acc_num"] for r in list_accounts(conn)]
                target_l = st.selectbox("Select Account", accs_list, key="limit_target")
                curr_row = conn.execute("SELECT daily_transfer_limit, currency FROM accounts WHERE acc_num=?", (target_l,)).fetchone()
                if curr_row:
                    st.write(f"Current Limit: {format_money(curr_row['daily_transfer_limit'], curr_row['currency'])}")
                new_lim = st.number_input("New Limit (major units)", min_value=1.0, value=10000.0, step=1000.0)
                if st.button("Update Limit"):
                    r = set_daily_limit(conn, int(target_l), to_minor(new_lim))
                    if r["status"] == "success":
                        st.success(r["message"])
                    else:
                        st.error(r["message"])

            with crud_tabs[4]:
                st.subheader("Delete Account")
                accs_list = [r["acc_num"] for r in list_accounts(conn)]
                target_d = st.selectbox("Select Account to Delete", accs_list, key="del_target")
                confirm = st.checkbox(f"Confirm permanent deletion of account {target_d}")
                if st.button("Permanently Delete Account", type="primary"):
                    if confirm:
                        r = delete_account(conn, logs.acc, int(target_d))
                        if r["status"] == "success":
                            st.success(r["message"])
                        else:
                            st.error(r["message"])
                    else:
                        st.warning("Please check the confirmation box.")

    elif menu == "🔐 Vault Management":
        st.title("Vault Management")
        v_tab1, v_tab2, v_tab3 = st.tabs(["Active Vaults", "Create Vault", "Destroy Vault"])

        with v_tab1:
            st.subheader("Existing Vaults")
            vault_rows = conn.execute(
                "SELECT a.acc_num, a.vault_no, a.vault_balance, a.currency, COUNT(vi.item_id) as items_count "
                "FROM accounts a LEFT JOIN vault_items vi ON a.vault_no = vi.vault_no "
                "WHERE a.vault_no IS NOT NULL GROUP BY a.acc_num"
            ).fetchall()
            if vault_rows:
                st.dataframe(pd.DataFrame([dict(r) for r in vault_rows]), use_container_width=True)
            else:
                st.info("No active vaults found.")

        with v_tab2:
            st.subheader("Create Vault for Customer Account")
            accs_no_v = [r["acc_num"] for r in conn.execute("SELECT acc_num FROM accounts WHERE vault_no IS NULL").fetchall()]
            if accs_no_v:
                v_acc = st.selectbox("Select Account", accs_no_v)
                v_no = st.text_input("Vault Number (e.g. V900)", value=f"V{v_acc}")
                v_pw = st.text_input("Vault Password", type="password")
                if st.button("Create Vault", type="primary"):
                    if not v_no or not v_pw:
                        st.warning("Vault Number and Vault Password are required.")
                    else:
                        r = create_vault(conn, int(v_acc), v_no, v_pw)
                        if r["status"] == "success":
                            st.success(r["message"])
                        else:
                            st.error(r["message"])
            else:
                st.info("All accounts currently have a vault assigned.")

        with v_tab3:
            st.subheader("Destroy Vault")
            accs_v = [r["acc_num"] for r in conn.execute("SELECT acc_num FROM accounts WHERE vault_no IS NOT NULL").fetchall()]
            if accs_v:
                d_acc = st.selectbox("Select Account", accs_v, key="dest_v_acc")
                d_vpw = st.text_input("Enter Vault Password to Authorize", type="password", key="dest_v_pw")
                transfer_bal = st.checkbox("Transfer remaining cash balance to account balance", value=True)
                if st.button("Destroy Vault", type="primary"):
                    r = destroy_vault(conn, logs.tx, int(d_acc), d_vpw, transfer_to_balance=transfer_bal)
                    if r["status"] == "success":
                        st.success(r["message"])
                    else:
                        st.error(r["message"])
            else:
                st.info("No active vaults to destroy.")

    elif menu == "⏳ Pending Transfers":
        st.title("Pending Transfers Approval Queue")
        st.caption("Transfers exceeding the compliance limit are held for administrator approval.")
        rows = get_pending_transfers(conn)
        if not rows:
            st.success("🎉 No pending transfers in queue.")
        else:
            for r in rows:
                tid = r["id"]
                with st.container():
                    st.markdown(
                        f"""
                        **Transfer ID:** {tid} | **Timestamp:** {r['timestamp']}  
                        **Sender:** `{r['sender_acc_num']}` ➔ **Receiver:** `{r['receiver_acc_num']}`  
                        **Amount:** {format_money(r['amount'], r['currency'])} | **Via Credit:** `{'Yes' if r['via_credit'] else 'No'}`
                        """
                    )
                    c_app, c_rej = st.columns([1, 1])
                    with c_app:
                        if st.button(f"✅ Approve Transfer #{tid}", key=f"app_{tid}"):
                            res = review_pending(conn, logs.tx, tid, approve=True, pending_conn=logs.pending)
                            if res["status"] == "success":
                                st.success(res["message"])
                                st.rerun()
                            else:
                                st.error(res["message"])
                    with c_rej:
                        if st.button(f"❌ Reject Transfer #{tid}", key=f"rej_{tid}"):
                            res = review_pending(conn, logs.tx, tid, approve=False, pending_conn=logs.pending)
                            if res["status"] == "success":
                                st.warning(res["message"])
                                st.rerun()
                            else:
                                st.error(res["message"])
                    st.markdown("---")

    elif menu == "📜 Audit & Transaction Logs":
        st.title("Audit Trail & Transaction Logs")
        t_choice = st.selectbox(
            "Log Type",
            ["transaction_log", "account_log", "freeze_log", "pending_transfers"],
        )
        col_f1, col_f2 = st.columns([2, 1])
        with col_f1:
            acc_filter = st.text_input("Filter by Account Number (Optional)", value="")
        with col_f2:
            row_limit = st.slider("Max Rows", min_value=10, max_value=200, value=50, step=10)

        acc_int = int(acc_filter.strip()) if acc_filter.strip().isdigit() else None
        log_rows = get_logs(conn, t_choice, acc_num=acc_int, limit=row_limit)
        if log_rows:
            df_logs = pd.DataFrame([dict(r) for r in log_rows])
            st.dataframe(df_logs, use_container_width=True)
        else:
            st.info("No log entries match the selected parameters.")

    elif menu == "🗄️ Database Management":
        st.title("Unified Database Management")
        st.caption("Inspect, query, import, and export all 12 operational tables in central bank.db.")
        db_tabs = st.tabs(["📋 Table Inspector", "📥 Multi-Format Importer", "📤 Data Exporter"])

        all_tables = get_all_table_names(conn)

        with db_tabs[0]:
            st.subheader("Table Schema & Data Inspector")
            target_t = st.selectbox("Select Database Table", all_tables)
            t_info = conn.execute(f"PRAGMA table_info({target_t})").fetchall()
            df_info = pd.DataFrame([dict(r) for r in t_info])
            st.write("**Schema Definitions:**")
            st.dataframe(df_info[["cid", "name", "type", "notnull", "dflt_value", "pk"]], use_container_width=True)

            t_rows = conn.execute(f"SELECT * FROM {target_t} LIMIT 100").fetchall()
            st.write(f"**Table Records (First 100 of {conn.execute(f'SELECT COUNT(*) as c FROM {target_t}').fetchone()['c']} rows):**")
            if t_rows:
                st.dataframe(pd.DataFrame([dict(r) for r in t_rows]), use_container_width=True)
            else:
                st.info("Table contains 0 records.")

        with db_tabs[1]:
            st.subheader("Multi-Format Data Importer")
            st.write("Supports **CSV, XLSX, JSON, XML, and SQL** ingestion.")
            imp_table = st.selectbox("Destination Table", all_tables, key="imp_t")
            uploaded_file = st.file_uploader("Select File to Ingest", type=["csv", "xlsx", "json", "xml", "sql"])
            if uploaded_file and st.button("Start Ingestion", type="primary"):
                ext = os.path.splitext(uploaded_file.name)[1]
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                    tmp.write(uploaded_file.getvalue())
                    tmp_path = tmp.name

                count, errors = import_file_to_table(conn, tmp_path, imp_table)
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

                if count > 0:
                    st.success(f"Successfully imported {count} row(s) into '{imp_table}'.")
                if errors:
                    st.warning(f"Encountered {len(errors)} error(s):")
                    for err in errors[:10]:
                        st.write(f"- {err}")

        with db_tabs[2]:
            st.subheader("Export Account Datasets")
            fmt = st.radio("File Format", ["CSV", "XLSX"], horizontal=True)
            exp_flt = st.selectbox(
                "Export Filter",
                ["all_account", "credit_card_account", "non_credit_card_account", "usd_accounts", "bdt_accounts"],
            )
            if st.button("Generate Export File"):
                tmp_out = tempfile.mktemp(suffix=f".{fmt.lower()}")
                if fmt == "CSV":
                    res = export_accounts_csv(conn, tmp_out, exp_flt)
                else:
                    res = export_accounts_xlsx(conn, tmp_out, exp_flt)

                if res["status"] == "success" and os.path.exists(tmp_out):
                    with open(tmp_out, "rb") as f:
                        file_bytes = f.read()
                    st.download_button(
                        label=f"⬇️ Download {fmt} Dataset ({res['data']['count']} rows)",
                        data=file_bytes,
                        file_name=f"bank_accounts_{exp_flt}.{fmt.lower()}",
                        mime="text/csv" if fmt == "CSV" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                    try:
                        os.remove(tmp_out)
                    except Exception:
                        pass
                else:
                    st.error(res["message"])

    elif menu == "📄 Generate Statements":
        st.title("Generate Customer Account Statement")
        accs = [r["acc_num"] for r in list_accounts(conn)]
        target_stmt = st.selectbox("Select Customer Account", accs)
        if st.button("Generate Statement (PDF)", type="primary"):
            try:
                pdf_path = generate_pdf_statement(conn, int(target_stmt), tx_log_conn=logs.tx)
                with open(pdf_path, "rb") as f:
                    pdf_data = f.read()
                st.download_button(
                    label=f"⬇️ Download Statement for #{target_stmt}",
                    data=pdf_data,
                    file_name=os.path.basename(pdf_path),
                    mime="application/pdf",
                )
                st.success("Official statement rendered successfully.")
            except Exception as e:
                st.error(f"Failed to generate statement: {e}")

    elif menu == "🔑 Reset Password":
        render_reset_password_panel(conn, is_admin=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Customer Portal
# ─────────────────────────────────────────────────────────────────────────────

def render_customer_portal() -> None:
    conn, logs = init_dbs()
    acc_num = st.session_state.identifier

    row = conn.execute("SELECT * FROM accounts WHERE acc_num=?", (acc_num,)).fetchone()
    if not row:
        st.error(f"Account {acc_num} not found.")
        if st.button("Logout"):
            logout()
        return

    currency = row["currency"]
    balance = row["acc_balance"]
    is_cc = (row["acc_type"] == "credit_card")
    is_frozen = bool(row["is_frozen"])

    with st.sidebar:
        _sidebar_brand()
        st.markdown(f"### 👤 Customer Portal\n**Account:** `#{acc_num}`  \n**Type:** `{row['acc_type'].replace('_', ' ').title()}`")
        nav_options = [
            "🏠 Account Overview",
            "💰 Deposit & Withdraw",
            "💸 Transfer Funds",
        ]
        if is_cc:
            nav_options.append("💳 Credit Card Payback")
        nav_options.extend([
            "🔐 Vault Operations",
            "📈 Financial Instruments",
            "💡 Utility Bill Payment",
            "🏛️ Government Tax Settlement",
            "📜 Recent Transactions",
            "📄 PDF Statement",
            "🔑 Reset Password",
        ])

        menu = st.radio("Navigation", nav_options)
        st.markdown("---")
        if st.button("Log Out", use_container_width=True):
            logout()

    _topbar(menu, f"Customer · #{acc_num}")

    if is_frozen:
        st.error("⚠️ **ACCOUNT IS FROZEN.** Transactions and outbound withdrawals are restricted.")

    if menu == "🏠 Account Overview":
        st.title("Account Overview")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.metric("Liquid Available Balance", format_money(balance, currency))
        with col_m2:
            st.metric("Dual-Currency Equivalent", format_money_dual(balance, currency).split("≈")[1].replace(")", "").strip())

        _render_customer_visuals(conn, logs, row, acc_num, currency, is_cc)

        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Account Specifications")
            st.write(f"- **Account Number:** `{acc_num}`")
            st.write(f"- **Account Type:** {row['acc_type'].replace('_', ' ').title()}")
            st.write(f"- **Currency:** {currency}")
            st.write(f"- **Status:** {'FROZEN' if is_frozen else 'Active'}")
            st.write(f"- **Daily Transfer Limit:** {format_money(row['daily_transfer_limit'], currency)}")
            if row["acc_type"] == "student":
                st.write(f"- **Parent / Guardian:** {row['parent_name']} ({row['parent_phone']})")
                st.write("- **Fee Waivers:** Maintenance, SMS Alerts, Card Issuance (All 100% Waived)")

        with c2:
            if is_cc:
                st.subheader("Credit Card Facility")
                st.write(f"- **Card Number:** **** **** **** {row['credit_card_num'][-4:] if row['credit_card_num'] else 'N/A'}")
                st.write(f"- **Credit Limit:** {format_money(row['credit_card_limit'], currency)}")
                st.write(f"- **Credit Used:** {format_money(row['credit_used'], currency)}")
                avail = max(0, row['credit_card_limit'] - row['credit_used'])
                st.write(f"- **Credit Available:** {format_money(avail, currency)}")

            if row["vault_no"]:
                st.subheader("Vault Safe")
                st.write(f"- **Vault Number:** `{row['vault_no']}`")
                st.write(f"- **Vault Cash Balance:** {format_money(row['vault_balance'], currency)}")

    elif menu == "💰 Deposit & Withdraw":
        st.title("Deposit & Withdraw Funds")
        d_tab, w_tab = st.tabs(["📥 Deposit Funds", "📤 Withdraw Funds"])

        with d_tab:
            st.subheader("Add Funds to Account")
            d_amt = st.number_input("Deposit Amount (major units)", min_value=1.0, value=100.0, step=10.0, key="dep_amt")
            d_cat = st.selectbox("Category", ["other", "food", "bills", "shopping", "transfer"], key="dep_cat")
            if st.button("Execute Deposit", type="primary"):
                r = add_funds(conn, logs.tx, acc_num, to_minor(d_amt), d_cat)
                if r["status"] == "success":
                    st.success(f"{r['message']} New balance: {format_money(r['data']['new_balance'], currency)}")
                else:
                    st.error(r["message"])

        with w_tab:
            st.subheader("Withdraw Funds from Account")
            w_amt = st.number_input("Withdrawal Amount (major units)", min_value=1.0, value=50.0, step=10.0, key="wd_amt")
            w_cat = st.selectbox("Category", ["other", "food", "bills", "shopping", "transfer"], key="wd_cat")
            if st.button("Execute Withdrawal", type="primary"):
                r = deduct_funds(conn, logs.tx, acc_num, to_minor(w_amt), w_cat)
                if r["status"] == "success":
                    st.success(f"{r['message']} New balance: {format_money(r['data']['new_balance'], currency)}")
                    if "sms_telemetry" in r["data"]:
                        st.info(f"📱 Mock SMS: {r['data']['sms_telemetry']['message']}")
                else:
                    st.error(r["message"])

    elif menu == "💸 Transfer Funds":
        st.title("Inter-Account Transfer")
        rec_acc = st.number_input("Recipient Account Number", min_value=1, step=1, value=1184)
        t_amt = st.number_input("Transfer Amount (major units)", min_value=1.0, value=100.0, step=10.0)
        t_cat = st.selectbox("Transfer Category", ["transfer", "bills", "shopping", "food", "other"])

        via_credit = False
        if is_cc:
            via_credit = st.checkbox("Fund transfer using Credit Card line", value=False)

        rec_row = conn.execute("SELECT currency FROM accounts WHERE acc_num=?", (int(rec_acc),)).fetchone()
        if rec_row and rec_row["currency"] != currency:
            est_conv = convert_minor(to_minor(t_amt), currency, rec_row["currency"])
            st.info(f"💱 Cross-currency transfer: Recipient will receive approximately {format_money(est_conv, rec_row['currency'])}.")

        if st.button("Send Transfer", type="primary"):
            r = transfer(
                conn,
                logs.tx,
                acc_num,
                int(rec_acc),
                to_minor(t_amt),
                category=t_cat,
                via_credit=via_credit,
                pending_conn=logs.pending,
            )
            if r["status"] == "success":
                st.success(r["message"])
            elif r["status"] == "pending":
                st.warning(f"⚠️ {r['message']} It will process upon administrator verification.")
            else:
                st.error(r["message"])

    elif menu == "💳 Credit Card Payback" and is_cc:
        st.title("Credit Card Balance Payback")
        st.write(f"Current Credit Used: **{format_money(row['credit_used'], currency)}**")
        st.write(f"Available Bank Balance: **{format_money(balance, currency)}**")

        p_amt = st.number_input("Payback Amount (major units)", min_value=1.0, value=from_minor(row['credit_used']) if row['credit_used'] > 0 else 10.0)
        source = st.radio("Payment Source", ["Pay from Account Balance", "Direct Cash Payment"], horizontal=True)
        cc_pin = st.text_input("Enter 4-Digit Credit Card PIN", type="password")

        if st.button("Submit Credit Card Payment", type="primary"):
            from_bal = (source == "Pay from Account Balance")
            r = payback_credit(conn, logs.tx, acc_num, to_minor(p_amt), from_bal, cc_pin)
            if r["status"] == "success":
                st.success(r["message"])
            else:
                st.error(r["message"])

    elif menu == "🔐 Vault Operations":
        st.title("Secure Vault Operations")
        if not row["vault_no"]:
            st.info("You do not have a vault attached to your account.")
            new_vno = st.text_input("Choose Vault Number (e.g. V101)", value=f"V{acc_num}")
            new_vpw = st.text_input("Set Vault Password", type="password")
            if st.button("Establish Vault Now", type="primary"):
                if not new_vno or not new_vpw:
                    st.warning("Please provide both vault number and password.")
                else:
                    r = create_vault(conn, acc_num, new_vno, new_vpw)
                    if r["status"] == "success":
                        st.success(r["message"])
                        st.rerun()
                    else:
                        st.error(r["message"])
        else:
            st.write(f"**Vault Assigned:** `{row['vault_no']}` | **Cash Holding:** {format_money(row['vault_balance'], currency)}")
            v_pw_attempt = st.text_input("Unlock Vault with Password", type="password", key="v_unlock_pw")
            unlocked = verify_vault_auth(conn, acc_num, v_pw_attempt)

            if not unlocked and v_pw_attempt:
                st.error("Incorrect vault password.")

            if unlocked:
                st.success("🔓 Vault Unlocked.")
                vt1, vt2, vt3 = st.tabs(["💰 Cash Movements", "💎 Physical Assets", "⚠️ Close Vault"])

                with vt1:
                    st.subheader("Vault Cash Deposit & Withdrawal")
                    c_v1, c_v2 = st.columns(2)
                    with c_v1:
                        v_dep = st.number_input("Deposit Cash to Vault (major units)", min_value=1.0, value=50.0, step=10.0)
                        if st.button("Deposit to Vault"):
                            r = vault_add(conn, logs.tx, acc_num, to_minor(v_dep), v_pw_attempt)
                            if r["status"] == "success":
                                st.success(r["message"])
                                st.rerun()
                            else:
                                st.error(r["message"])
                    with c_v2:
                        v_wd = st.number_input("Withdraw Cash from Vault (major units)", min_value=1.0, value=25.0, step=10.0)
                        to_cc = False
                        if is_cc:
                            to_cc = st.checkbox("Route directly to Credit Card payback", value=False)
                        if st.button("Withdraw from Vault"):
                            r = vault_deduct(conn, logs.tx, acc_num, to_minor(v_wd), v_pw_attempt, to_credit_payback=to_cc)
                            if r["status"] == "success":
                                st.success(r["message"])
                                st.rerun()
                            else:
                                st.error(r["message"])

                with vt2:
                    st.subheader("Physical Asset Inventory")
                    items = conn.execute("SELECT * FROM vault_items WHERE vault_no=?", (row["vault_no"],)).fetchall()
                    if items:
                        df_items = pd.DataFrame([dict(i) for i in items])
                        st.dataframe(df_items[["item_id", "item_type", "description", "est_value_minor", "added_at"]], use_container_width=True)
                    else:
                        st.info("No physical assets committed yet.")

                    st.markdown("#### Deposit New Physical Asset")
                    i_type = st.selectbox("Asset Category", ["gold", "paper_deeds", "corporate_bonds", "heirlooms"])
                    i_desc = st.text_input("Asset Description", value="10 Tolas of 24K Gold Bar")
                    i_val = st.number_input("Estimated Value (major units)", min_value=1.0, value=150000.0, step=5000.0)
                    if st.button("Commit Asset to Vault"):
                        r = add_vault_item(conn, acc_num, v_pw_attempt, i_type, i_desc, to_minor(i_val))
                        if r["status"] == "success":
                            st.success(r["message"])
                            st.rerun()
                        else:
                            st.error(r["message"])

                with vt3:
                    st.subheader("Destroy Vault")
                    st.warning("Closing this vault will permanently delete its record and release cash assets.")
                    to_bal = st.checkbox("Transfer remaining cash to account balance", value=True, key="dest_to_bal")
                    if st.button("Permanently Destroy Vault", type="primary"):
                        r = destroy_vault(conn, logs.tx, acc_num, v_pw_attempt, transfer_to_balance=to_bal)
                        if r["status"] == "success":
                            st.success(r["message"])
                            st.rerun()
                        else:
                            st.error(r["message"])

    elif menu == "📈 Financial Instruments":
        st.title("Financial Derivatives & Instruments")
        f_tabs = st.tabs(["🏦 Loans", "📜 Bonds", "🖋️ Checks"])

        with f_tabs[0]:
            st.subheader("Loan Facility")
            l_col1, l_col2 = st.columns(2)
            with l_col1:
                st.write("**Disburse New Loan**")
                loan_p = st.number_input("Principal Amount (major units)", min_value=100.0, value=5000.0, step=500.0)
                loan_r = st.number_input("Annual Interest Rate (%)", min_value=1.0, max_value=30.0, value=9.5, step=0.5)
                if st.button("Disburse Loan"):
                    res = execute_loan_disbursal(conn, logs.tx, acc_num, to_minor(loan_p), loan_r / 100.0)
                    if res["status"] == "success":
                        st.success(res["message"])
                    else:
                        st.error(res["message"])

            with l_col2:
                st.write("**Active Loans**")
                loans = conn.execute("SELECT * FROM loans WHERE acc_num=? AND status='active'", (acc_num,)).fetchall()
                if loans:
                    st.dataframe(pd.DataFrame([dict(l) for l in loans]), use_container_width=True)
                    st.write("**Repay Loan**")
                    rep_id = st.selectbox("Select Loan ID to Repay", [l["loan_id"] for l in loans])
                    rep_amt = st.number_input("Repayment Amount (major units)", min_value=10.0, value=500.0, step=50.0)
                    if st.button("Submit Loan Repayment"):
                        r = execute_loan_repayment(conn, logs.tx, int(rep_id), to_minor(rep_amt))
                        if r["status"] == "success":
                            st.success(r["message"])
                        else:
                            st.error(r["message"])
                else:
                    st.info("No active loans.")

        with f_tabs[1]:
            st.subheader("Sovereign & Treasury Bonds")
            b_col1, b_col2 = st.columns(2)
            with b_col1:
                st.write("**Purchase Bond**")
                b_face = st.number_input("Face Value (major units)", min_value=100.0, value=1000.0, step=100.0)
                b_yield = st.number_input("Yield Rate (%)", min_value=1.0, max_value=20.0, value=7.0, step=0.5)
                b_days = st.number_input("Maturity Period (days)", min_value=1, value=30, step=5)
                if st.button("Purchase Bond"):
                    mat_ts = (datetime.now() + timedelta(days=int(b_days))).isoformat()
                    res = execute_bond_purchase(conn, logs.tx, acc_num, to_minor(b_face), b_yield / 100.0, mat_ts)
                    if res["status"] == "success":
                        st.success(res["message"])
                    else:
                        st.error(res["message"])

            with b_col2:
                st.write("**Owned Bonds**")
                bonds = conn.execute("SELECT * FROM bonds WHERE acc_num=?", (acc_num,)).fetchall()
                if bonds:
                    st.dataframe(pd.DataFrame([dict(b) for b in bonds]), use_container_width=True)
                    active_b = [b["bond_id"] for b in bonds if b["status"] == "active"]
                    if active_b:
                        red_id = st.selectbox("Select Bond to Redeem", active_b)
                        if st.button("Redeem Bond"):
                            r = execute_bond_redemption(conn, logs.tx, int(red_id))
                            if r["status"] == "success":
                                st.success(r["message"])
                            else:
                                st.error(r["message"])
                else:
                    st.info("No bonds owned.")

        with f_tabs[2]:
            st.subheader("Check Management")
            chk_col1, chk_col2 = st.columns(2)
            with chk_col1:
                st.write("**Issue New Check**")
                chk_amt = st.number_input("Check Amount (major units)", min_value=10.0, value=250.0, step=25.0)
                payee = st.text_input("Payee Full Name", value="Apex Supplies Ltd")
                memo = st.text_input("Memo / Reference", value="Invoice #4401")
                if st.button("Issue Check"):
                    r = execute_check_issuance(conn, logs.tx, acc_num, to_minor(chk_amt), payee, memo)
                    if r["status"] == "success":
                        st.success(r["message"])
                    else:
                        st.error(r["message"])

            with chk_col2:
                st.write("**Issued Checks Register**")
                chks = conn.execute("SELECT * FROM checks WHERE acc_num=?", (acc_num,)).fetchall()
                if chks:
                    st.dataframe(pd.DataFrame([dict(c) for c in chks]), use_container_width=True)
                    issued_ids = [c["check_id"] for c in chks if c["status"] == "issued"]
                    if issued_ids:
                        target_chk = st.selectbox("Select Check to Process", issued_ids)
                        b1, b2 = st.columns(2)
                        with b1:
                            if st.button("Simulate Clearing"):
                                r = execute_check_clearing(conn, logs.tx, int(target_chk))
                                st.success(r["message"])
                        with b2:
                            if st.button("Simulate Bouncing"):
                                r = execute_check_bouncing(conn, logs.tx, int(target_chk))
                                st.warning(r["message"])
                else:
                    st.info("No checks issued yet.")

    elif menu == "💡 Utility Bill Payment":
        st.title("Utility Bill Payments")
        billers = get_billers_by_category(conn)
        available_billers = []
        for cat in ["gas", "electric", "water"]:
            for b in billers.get(cat, []):
                available_billers.append((b["biller_id"], f"{b['biller_name']} [{cat.upper()}] (Receiving Acc: #{b['receiving_acc_num']})"))

        if available_billers:
            b_choice = st.selectbox("Select Utility Provider", available_billers, format_func=lambda x: x[1])
            u_amt = st.number_input("Bill Amount (major units)", min_value=1.0, value=120.0, step=10.0)
            if st.button("Pay Utility Bill", type="primary"):
                r = pay_biller(conn, logs.tx, acc_num, b_choice[0], to_minor(u_amt))
                if r["status"] == "success":
                    st.success(r["message"])
                else:
                    st.error(r["message"])
        else:
            st.info("No utility billers registered.")

    elif menu == "🏛️ Government Tax Settlement":
        st.title("Government Tax Settlement")
        billers = get_billers_by_category(conn)
        tax_billers = billers.get("tax", [])
        if tax_billers:
            t_choice = st.selectbox("Select Tax Authority", [(b["biller_id"], f"{b['biller_name']} (Acc: #{b['receiving_acc_num']})") for b in tax_billers], format_func=lambda x: x[1])
            tax_amt = st.number_input("Tax Amount (major units)", min_value=1.0, value=500.0, step=50.0)
            if st.button("Settle Tax Liability", type="primary"):
                r = pay_biller(conn, logs.tx, acc_num, t_choice[0], to_minor(tax_amt))
                if r["status"] == "success":
                    st.success(r["message"])
                else:
                    st.error(r["message"])
        else:
            st.info("No tax authorities registered.")

    elif menu == "📜 Recent Transactions":
        st.title("Recent Transactions")
        tx_rows = recent_transactions(conn, acc_num, limit=50, tx_log_conn=logs.tx)
        if tx_rows:
            df = pd.DataFrame([dict(r) for r in tx_rows])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No recorded transactions found.")

    elif menu == "📄 PDF Statement":
        st.title("Official Statement Generation")
        st.write("Generate and download an official stamped account statement.")
        if st.button("Render PDF Statement", type="primary"):
            try:
                pdf_path = generate_pdf_statement(conn, acc_num, tx_log_conn=logs.tx)
                with open(pdf_path, "rb") as f:
                    pdf_data = f.read()
                st.download_button(
                    label="⬇️ Download PDF Statement",
                    data=pdf_data,
                    file_name=os.path.basename(pdf_path),
                    mime="application/pdf",
                )
                st.success("Statement generated.")
            except Exception as e:
                st.error(f"Error generating statement: {e}")

    elif menu == "🔑 Reset Password":
        render_reset_password_panel(conn, is_admin=False)


# ─────────────────────────────────────────────────────────────────────────────
#  Application Root
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(page_title="BankOS Enterprise", page_icon="🏦", layout="wide")
    inject_theme()
    # =====================================================================================
    # ── DISABLED: "Practice project — do not enter real data" warning banner ──
    # Commented out so the amber warning box no longer appears anywhere in the app.
    # To show it again, remove the leading '#' from the line below.
    # ======================================================================================
    # _practice_banner()
    init_dbs()

    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.user_type = None
        st.session_state.identifier = None

    if not st.session_state.logged_in:
        render_login()
    else:
        if st.session_state.user_type == "admin":
            render_admin_portal()
        else:
            render_customer_portal()


if __name__ == "__main__":
    main()
