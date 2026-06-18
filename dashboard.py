"""
dashboard.py — AGENTX Trading Command Center
Bloomberg-terminal-grade UI with 7 tabs, rich analytics charts,
backtester integration, agent orchestrator, and live MT5 data.
"""
import time
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from app_auth import check_auth, sign_out
from app_state import DashboardState, BOT_SCRIPTS

# ── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AGENTX | Trading Command Center",
    page_icon="🐅",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Auth Gate ────────────────────────────────────────────────────────────────
if not check_auth():
    st.stop()

state = DashboardState()
snap  = state.snapshot()
acc   = snap["account"]
stats = snap["stats"]

# ── Global CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body, .stApp {
    background: #020817 !important;
    color: #E2E8F0 !important;
    font-family: 'Inter', sans-serif !important;
}

#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 0 1.5rem 2rem !important; max-width: 100% !important; }

/* ── Header ── */
.inv-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 1rem 1.5rem;
    background: linear-gradient(135deg, rgba(15,23,42,0.97), rgba(7,14,35,0.97));
    border-bottom: 1px solid rgba(59,130,246,0.2);
    margin: 0 -1.5rem 1.5rem;
    backdrop-filter: blur(20px);
    position: sticky; top: 0; z-index: 999;
}
.inv-logo {
    font-size: 1.4rem; font-weight: 900; letter-spacing: 0.12em;
    background: linear-gradient(90deg, #60A5FA 0%, #34D399 50%, #FBBF24 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.inv-account-badge {
    display: flex; align-items: center; gap: 1.5rem;
    font-size: 0.8rem; color: #94A3B8;
}
.inv-account-badge .badge-item { display: flex; flex-direction: column; align-items: flex-end; }
.inv-account-badge .badge-label { font-size: 0.68rem; color: #64748B; text-transform: uppercase; letter-spacing: 0.06em; }
.inv-account-badge .badge-value { color: #E2E8F0; font-weight: 600; font-size: 0.82rem; }
.dot-live { width:8px; height:8px; border-radius:50%; background:#10B981;
    box-shadow: 0 0 6px #10B981, 0 0 12px #10B981;
    animation: pulse-dot 2s infinite; display: inline-block; margin-right: 6px; }
.dot-offline { width:8px; height:8px; border-radius:50%; background:#EF4444; display:inline-block; margin-right:6px; }
@keyframes pulse-dot { 0%,100%{opacity:1} 50%{opacity:0.4} }

/* ── Metric Cards ── */
.metric-grid { display: grid; gap: 1rem; margin-bottom: 1.5rem; }
.metric-grid-6 { grid-template-columns: repeat(6, 1fr); }
.metric-grid-4 { grid-template-columns: repeat(4, 1fr); }
.metric-grid-3 { grid-template-columns: repeat(3, 1fr); }
.metric-grid-5 { grid-template-columns: repeat(5, 1fr); }

.mc {
    background: linear-gradient(145deg, rgba(15,23,42,0.9), rgba(7,14,35,0.9));
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px; padding: 1.1rem 1.3rem;
    backdrop-filter: blur(10px);
    transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s;
    position: relative; overflow: hidden;
}
.mc::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, transparent, rgba(59,130,246,0.6), transparent);
}
.mc:hover { transform: translateY(-2px); border-color: rgba(59,130,246,0.25);
    box-shadow: 0 8px 30px rgba(59,130,246,0.1); }
.mc .mc-label { font-size: 0.72rem; color: #64748B; text-transform: uppercase;
    letter-spacing: 0.08em; margin-bottom: 0.4rem; font-weight: 500; }
.mc .mc-value { font-size: 1.6rem; font-weight: 700; color: #F1F5F9; line-height: 1; }
.mc .mc-sub   { font-size: 0.75rem; color: #64748B; margin-top: 0.3rem; }
.mc .mc-change { font-size: 0.78rem; font-weight: 600; margin-top: 0.2rem; }
.mc.positive .mc-value, .mc.positive .mc-change { color: #10B981; }
.mc.negative .mc-value, .mc.negative .mc-change { color: #EF4444; }
.mc.blue     .mc-value { color: #60A5FA; }
.mc.amber    .mc-value { color: #FBBF24; }
.mc.purple   .mc-value { color: #A78BFA; }
.mc.cyan     .mc-value { color: #22D3EE; }

/* ── Section title ── */
.sec-title {
    font-size: 0.78rem; font-weight: 600; color: #64748B;
    text-transform: uppercase; letter-spacing: 0.1em;
    margin: 1.5rem 0 0.75rem; display: flex; align-items: center; gap: 0.5rem;
}
.sec-title::after { content: ''; flex: 1; height: 1px; background: rgba(255,255,255,0.05); }

/* ── Terminal ── */
.terminal-wrap {
    background: #010B18; border: 1px solid rgba(59,130,246,0.15);
    border-radius: 10px; overflow: hidden;
}
.terminal-titlebar {
    display: flex; align-items: center; gap: 6px;
    padding: 0.5rem 0.75rem; background: rgba(15,23,42,0.8);
    border-bottom: 1px solid rgba(255,255,255,0.05);
}
.t-dot { width:10px; height:10px; border-radius:50%; }
.terminal-body {
    font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
    color: #38BDF8; padding: 0.75rem 1rem;
    height: 340px; overflow-y: auto; line-height: 1.5;
    white-space: pre-wrap; word-break: break-all;
}
.terminal-body .log-warn  { color: #FBBF24; }
.terminal-body .log-error { color: #EF4444; }
.terminal-body .log-info  { color: #38BDF8; }
.terminal-body .log-action{ color: #10B981; }

/* ── Data Tables ── */
.data-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.data-table th {
    background: rgba(15,23,42,0.8); color: #64748B;
    text-transform: uppercase; letter-spacing: 0.06em;
    font-size: 0.68rem; padding: 0.6rem 0.8rem;
    border-bottom: 1px solid rgba(255,255,255,0.06); text-align: left;
}
.data-table td { padding: 0.55rem 0.8rem; border-bottom: 1px solid rgba(255,255,255,0.03); color: #CBD5E1; }
.data-table tr:hover td { background: rgba(59,130,246,0.05); }
.data-table .buy-badge  { color: #10B981; font-weight: 600; }
.data-table .sell-badge { color: #EF4444; font-weight: 600; }
.data-table .profit-pos { color: #10B981; font-weight: 600; }
.data-table .profit-neg { color: #EF4444; font-weight: 600; }
.data-table .mono { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; }

/* ── Position Cards ── */
.pos-card {
    background: rgba(15,23,42,0.7); border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.06); padding: 1rem;
    margin-bottom: 0.75rem;
}
.pos-card.buy-card  { border-left: 3px solid #10B981; }
.pos-card.sell-card { border-left: 3px solid #EF4444; }
.pos-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
.pos-symbol { font-weight: 700; font-size: 1rem; }
.pos-badge  { font-size: 0.72rem; padding: 2px 8px; border-radius: 4px; font-weight: 700; }
.pos-badge.buy  { background: rgba(16,185,129,0.15); color: #10B981; }
.pos-badge.sell { background: rgba(239,68,68,0.15); color: #EF4444; }
.pos-grid   { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem; margin-top: 0.5rem; }
.pos-field  { font-size: 0.72rem; }
.pos-field .pf-label { color: #64748B; margin-bottom: 2px; }
.pos-field .pf-value { color: #E2E8F0; font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; }

/* ── Diagnostic Panel ── */
.diag-panel {
    background: rgba(239,68,68,0.06); border: 1px solid rgba(239,68,68,0.2);
    border-radius: 12px; padding: 1.2rem 1.5rem; margin-bottom: 1.5rem;
}
.diag-panel .diag-title { font-size: 0.9rem; font-weight: 700; color: #EF4444; margin-bottom: 0.75rem; }
.diag-panel .diag-item { font-size: 0.8rem; color: #FCA5A5; padding: 0.2rem 0; font-family: 'JetBrains Mono', monospace; }
.diag-panel .diag-fix { font-size: 0.8rem; color: #10B981; padding: 0.2rem 0; font-family: 'JetBrains Mono', monospace; }

/* ── Agent Cards ── */
.agent-card {
    background: rgba(15,23,42,0.7); border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px; padding: 1rem;
    transition: border-color 0.2s;
}
.agent-card:hover { border-color: rgba(59,130,246,0.25); }
.agent-card .agent-name { font-weight: 700; font-size: 0.85rem; color: #E2E8F0; margin-bottom: 0.3rem; }
.agent-card .agent-role { font-size: 0.68rem; color: #64748B; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; }
.agent-card .agent-stat { font-size: 0.75rem; color: #94A3B8; padding: 0.15rem 0; }
.agent-card .agent-stat b { color: #CBD5E1; }
.agent-badge-active { background: rgba(16,185,129,0.15); color: #10B981; font-size: 0.65rem; padding: 2px 7px; border-radius: 4px; font-weight: 600; }
.agent-badge-idle  { background: rgba(100,116,139,0.15); color: #64748B; font-size: 0.65rem; padding: 2px 7px; border-radius: 4px; font-weight: 600; }

/* ── Buttons ── */
div[data-testid="stButton"] > button {
    border-radius: 8px !important; font-weight: 600 !important;
    font-family: 'Inter', sans-serif !important; transition: all 0.2s !important;
    font-size: 0.85rem !important;
}
div[data-testid="stButton"] > button:hover { transform: translateY(-1px) !important; }

/* ── Tabs ── */
div[data-testid="stTabs"] [role="tablist"] {
    gap: 0 !important; border-bottom: 1px solid rgba(255,255,255,0.06) !important;
    background: transparent !important;
}
div[data-testid="stTabs"] button[role="tab"] {
    font-size: 0.82rem !important; font-weight: 500 !important;
    color: #64748B !important; padding: 0.6rem 1.1rem !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important; background: transparent !important;
}
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: #60A5FA !important; border-bottom-color: #60A5FA !important;
}

/* ── Misc ── */
.stTextArea textarea { font-family: 'JetBrains Mono', monospace !important; font-size: 0.82rem !important;
    background: #010B18 !important; color: #38BDF8 !important; border: 1px solid rgba(59,130,246,0.2) !important; }
div[data-testid="stSelectbox"] > div { border-color: rgba(59,130,246,0.2) !important; }
div[data-testid="stNumberInput"] > div { border-color: rgba(59,130,246,0.2) !important; }
.stSlider .stMarkdown { color: #E2E8F0; }
.empty-state { text-align: center; padding: 3rem; color: #475569; font-size: 0.9rem; }

/* ── Symbol Performance Row ── */
.sym-row {
    display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1rem;
}
.sym-chip {
    background: rgba(15,23,42,0.8); border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px; padding: 0.6rem 0.9rem; min-width: 130px; flex: 1;
}
.sym-chip .sym-name { font-size: 0.75rem; font-weight: 700; color: #E2E8F0; }
.sym-chip .sym-pnl { font-size: 0.85rem; font-weight: 600; margin-top: 0.2rem; }
.sym-chip .sym-meta { font-size: 0.65rem; color: #64748B; margin-top: 0.15rem; }
.sym-chip.win  .sym-pnl { color: #10B981; }
.sym-chip.loss .sym-pnl { color: #EF4444; }

/* ── FTMO Banner ── */
.ftmo-pass {
    background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.3);
    border-radius: 10px; padding: 0.8rem 1.2rem; margin-bottom: 1rem;
    color: #10B981; font-weight: 700; font-size: 0.85rem;
}
.ftmo-fail {
    background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.3);
    border-radius: 10px; padding: 0.8rem 1.2rem; margin-bottom: 1rem;
    color: #EF4444; font-weight: 700; font-size: 0.85rem;
}
</style>
""", unsafe_allow_html=True)


# ── Helper Functions ──────────────────────────────────────────────────────────

def fmt_currency(val, currency=""):
    if val is None: return "—"
    prefix = "+" if val > 0 else ""
    return f"{prefix}${val:,.2f}" if val >= 0 else f"-${abs(val):,.2f}"

def fmt_price(val):
    if val is None: return "—"
    return f"{val:,.5f}"

def pnl_class(val):
    if val is None: return ""
    return "profit-pos" if val >= 0 else "profit-neg"

def color_log_line(line: str) -> str:
    line_h = line.replace("<", "&lt;").replace(">", "&gt;")
    if any(k in line.upper() for k in ["ERROR", "FAIL", "CRITICAL"]):
        return f'<span class="log-error">{line_h}</span>'
    elif any(k in line.upper() for k in ["WARN", "WARNING"]):
        return f'<span class="log-warn">{line_h}</span>'
    elif any(k in line.upper() for k in ["ACTION", "ORDER", "FILL", "BUY", "SELL", "CLOSE", "ENTRY"]):
        return f'<span class="log-action">{line_h}</span>'
    else:
        return f'<span class="log-info">{line_h}</span>'

def render_trade_table(trades: list, max_rows: int = 100):
    if not trades:
        st.markdown('<div class="empty-state">No trade history available for the selected period.</div>', unsafe_allow_html=True)
        return
    rows_html = ""
    for t in trades[:max_rows]:
        direction_cls = "buy-badge" if t["type"] == "BUY" else "sell-badge"
        pc = pnl_class(t["net_profit"])
        pnl_sign = "+" if t["net_profit"] >= 0 else ""
        rows_html += f"""
        <tr>
          <td class="mono">{t['open_time']}</td>
          <td class="mono">{t.get('close_time','—')}</td>
          <td><b>{t['symbol']}</b></td>
          <td class="{direction_cls}">{t['type']}</td>
          <td class="mono">{t['volume']}</td>
          <td class="mono">{fmt_price(t.get('entry_price'))}</td>
          <td class="mono">{fmt_price(t.get('exit_price'))}</td>
          <td class="mono">{t.get('swap',0):.2f}</td>
          <td class="mono">{t.get('commission',0):.2f}</td>
          <td class="mono {pc}"><b>{pnl_sign}${abs(t['net_profit']):.2f}</b></td>
          <td class="mono">{t.get('duration','—')}</td>
        </tr>"""
    st.markdown(f"""
    <div style="overflow-x:auto; border-radius:10px; border:1px solid rgba(255,255,255,0.06);">
    <table class="data-table">
      <thead><tr>
        <th>Open Time</th><th>Close Time</th><th>Symbol</th><th>Type</th>
        <th>Vol</th><th>Entry</th><th>Exit</th>
        <th>Swap</th><th>Comm</th><th>Net PnL</th><th>Duration</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    </div>""", unsafe_allow_html=True)

def render_empty_chart(msg="No data available"):
    fig = go.Figure()
    fig.add_annotation(text=msg, xref="paper", yref="paper", x=0.5, y=0.5,
                       showarrow=False, font=dict(color="#475569", size=14))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=250, margin=dict(l=0,r=0,t=0,b=0),
                      xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                      yaxis=dict(showgrid=False, zeroline=False, showticklabels=False))
    return fig


# ── Header ────────────────────────────────────────────────────────────────────
connected    = snap["connected"]
dot          = '<span class="dot-live"></span>' if connected else '<span class="dot-offline"></span>'
conn_label   = "CONNECTED" if connected else "OFFLINE"
broker_name  = acc.get("broker", "—")
server_name  = acc.get("server", "—")
login_num    = acc.get("login", "—")
balance      = acc.get("balance", 0.0)
equity       = acc.get("equity", 0.0)
currency     = acc.get("currency", "USD")

st.markdown(f"""
<div class="inv-header">
  <div class="inv-logo">🐅 AGENTX</div>
  <div class="inv-account-badge">
    <div class="badge-item">
      <span class="badge-label">Connection</span>
      <span class="badge-value">{dot}{conn_label}</span>
    </div>
    <div class="badge-item">
      <span class="badge-label">Account</span>
      <span class="badge-value">#{login_num}</span>
    </div>
    <div class="badge-item">
      <span class="badge-label">Broker</span>
      <span class="badge-value">{broker_name}</span>
    </div>
    <div class="badge-item">
      <span class="badge-label">Server</span>
      <span class="badge-value">{server_name}</span>
    </div>
    <div class="badge-item">
      <span class="badge-label">Currency</span>
      <span class="badge-value">{currency}</span>
    </div>
    <div class="badge-item">
      <span class="badge-label">User</span>
      <span class="badge-value">{st.session_state.get('authenticated_email','—')}</span>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


# ── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "⚡ Live Overview",
    "📊 Analytics",
    "📋 Trade History",
    "📌 Open Positions",
    "🐆 Backtester",
    "🧠 Agent Network",
    "📝 Editor & Deploy",
])


# ═══════════════════════════════════════════════════════════════════
# TAB 1 — LIVE OVERVIEW
# ═══════════════════════════════════════════════════════════════════
with tab1:
    # ── Diagnostic Panel (show when offline) ──────────────────────────────────
    if not connected:
        diag = snap.get("diagnostic", {})
        suggestions = diag.get("suggestions", [])
        os_name = diag.get("os", "Unknown")
        is_win = diag.get("is_windows", False)
        mt5_err = diag.get("mt5_connect_error", "")
        term_run = diag.get("terminal_running", False)

        reason = "MT5 Python API only works on Windows with the MT5 terminal installed and logged in."
        if not is_win:
            reason = f"🖥️ This machine runs **{os_name}** — MT5 requires **Windows**. The MetaTrader5 Python package only connects to a locally installed MT5 terminal."
        elif not mt5_err:
            reason = "✅ MT5 package is installed but terminal is not reachable."
        else:
            reason = f"MT5 connection error: `{mt5_err}`"

        st.markdown(f"""
        <div class="diag-panel">
          <div class="diag-title">🔴 MT5 Connection Failed</div>
          <div class="diag-item">{reason}</div>
          <div style="margin-top: 0.75rem;">
            {''.join(f'<div class="diag-fix">{s}</div>' for s in suggestions) if suggestions else ''}
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Key Metrics ──────────────────────────────────────────────────────────
    daily_pnl   = stats.get("daily_pnl", 0.0)
    win_rate    = stats.get("win_rate", 0.0)
    open_count  = len(snap["positions"])
    net_profit  = stats.get("net_profit", 0.0)
    float_pnl   = sum(p["profit"] for p in snap["positions"])
    free_margin = acc.get("free_margin", 0.0)
    margin      = acc.get("margin", 0.0)
    margin_pct  = round((margin / balance * 100), 1) if balance > 0 else 0.0

    pnl_cls     = "positive" if daily_pnl >= 0 else "negative"
    net_cls     = "positive" if net_profit >= 0 else "negative"
    float_cls   = "positive" if float_pnl >= 0 else "negative"
    pnl_sign    = "+" if daily_pnl >= 0 else ""
    net_sign    = "+" if net_profit >= 0 else ""
    fl_sign     = "+" if float_pnl >= 0 else ""

    st.markdown('<p class="sec-title">Account Overview</p>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="metric-grid metric-grid-6">
      <div class="mc blue">
        <div class="mc-label">Balance</div>
        <div class="mc-value">${balance:,.2f}</div>
        <div class="mc-sub">{currency} · Leverage {acc.get('leverage','—')}x</div>
      </div>
      <div class="mc blue">
        <div class="mc-label">Equity</div>
        <div class="mc-value">${equity:,.2f}</div>
        <div class="mc-sub">Free: ${free_margin:,.2f} · Margin: {margin_pct}%</div>
      </div>
      <div class="mc {pnl_cls}">
        <div class="mc-label">Today's PnL</div>
        <div class="mc-value">{pnl_sign}${abs(daily_pnl):,.2f}</div>
        <div class="mc-sub">Closed trades today</div>
      </div>
      <div class="mc {net_cls}">
        <div class="mc-label">{snap['history_days']}d Net PnL</div>
        <div class="mc-value">{net_sign}${abs(net_profit):,.2f}</div>
        <div class="mc-sub">Gross: +${stats.get('gross_profit',0):,.2f} / -${abs(stats.get('gross_loss',0)):,.2f}</div>
      </div>
      <div class="mc {'positive' if win_rate >= 50 else 'negative'}">
        <div class="mc-label">Win Rate</div>
        <div class="mc-value">{win_rate}%</div>
        <div class="mc-sub">{stats.get('wins',0)}W / {stats.get('losses',0)}L</div>
      </div>
      <div class="mc {'blue' if open_count == 0 else 'amber'}">
        <div class="mc-label">Open Positions</div>
        <div class="mc-value">{open_count}</div>
        <div class="mc-sub">Float PnL: {fl_sign}${abs(float_pnl):,.2f}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Symbol Quick View ────────────────────────────────────────────────────
    sym_perf = snap.get("symbol_perf", [])
    if sym_perf:
        st.markdown('<p class="sec-title">Symbol Performance</p>', unsafe_allow_html=True)
        sym_html = '<div class="sym-row">'
        for s in sym_perf[:12]:
            win_cls = "win" if s["net_pnl"] >= 0 else "loss"
            pnls = "+" if s["net_pnl"] >= 0 else ""
            sym_html += f"""
            <div class="sym-chip {win_cls}">
              <div class="sym-name">{s['symbol']}</div>
              <div class="sym-pnl">{pnls}${abs(s['net_pnl']):,.2f}</div>
              <div class="sym-meta">{s['trades']} trades · {s['win_rate']}% WR</div>
            </div>"""
        sym_html += '</div>'
        st.markdown(sym_html, unsafe_allow_html=True)

    # ── Equity Curve + Bot Controls ─────────────────────────────────────────
    col_chart, col_ctrl = st.columns([14, 6])

    with col_chart:
        st.markdown('<p class="sec-title">Equity Curve</p>', unsafe_allow_html=True)
        curve = snap["curve"]
        if curve and len(curve) > 1:
            df = pd.DataFrame(curve)
            df["time"] = pd.to_datetime(df["time"])
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df["time"], y=df["equity"],
                mode="lines", name="Equity",
                line=dict(color="#3B82F6", width=2),
                fill="tozeroy", fillcolor="rgba(59,130,246,0.06)",
            ))
            buy_df = df[df["type"].str.contains("BUY", na=False)]
            if not buy_df.empty:
                fig.add_trace(go.Scatter(
                    x=buy_df["time"], y=buy_df["equity"],
                    mode="markers", name="Buy Fill",
                    marker=dict(color="#10B981", size=10, symbol="triangle-up",
                                line=dict(color="#064E3B", width=1)),
                ))
            sell_df = df[df["type"].str.contains("SELL", na=False)]
            if not sell_df.empty:
                fig.add_trace(go.Scatter(
                    x=sell_df["time"], y=sell_df["equity"],
                    mode="markers", name="Sell Fill",
                    marker=dict(color="#EF4444", size=10, symbol="triangle-down",
                                line=dict(color="#7F1D1D", width=1)),
                ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)",
                           tickfont=dict(size=10, color="#64748B"), showline=False),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)",
                           tickfont=dict(size=10, color="#64748B"), showline=False, tickprefix="$"),
                margin=dict(l=10, r=10, t=10, b=10),
                legend=dict(orientation="h", y=1.08, x=0, font=dict(size=11, color="#94A3B8"), bgcolor="rgba(0,0,0,0)"),
                height=310, hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.markdown('<div class="empty-state">No closed trades yet. Equity curve builds from closed trade history.</div>', unsafe_allow_html=True)

    with col_ctrl:
        st.markdown('<p class="sec-title">Bot Control</p>', unsafe_allow_html=True)
        bot_options = state.available_bots()
        current_idx = bot_options.index(snap["active_bot"]) if snap["active_bot"] in bot_options else 0
        selected_bot = st.selectbox("Select Bot:", bot_options, index=current_idx, key="bot_sel")
        is_running = snap["bot_running"]
        if is_running:
            if st.button("⛔ Stop Bot", use_container_width=True, type="secondary", key="stop_btn"):
                msg = state.stop_bot()
                st.info(msg)
                time.sleep(0.5); st.rerun()
        else:
            if st.button("⚡ Start Bot", use_container_width=True, type="primary", key="start_btn"):
                msg = state.start_bot(selected_bot)
                st.info(msg)
                time.sleep(0.5); st.rerun()
        status_color = "#10B981" if is_running else "#EF4444"
        status_text  = "RUNNING" if is_running else "STOPPED"
        st.markdown(f"""
        <div style="text-align:center; margin: 0.5rem 0; padding: 0.5rem;
             background: rgba(15,23,42,0.6); border-radius:8px;
             border: 1px solid rgba(255,255,255,0.05);">
          <span style="color:{status_color}; font-weight:700; font-size:0.85rem;">● {status_text}</span>
        </div>""", unsafe_allow_html=True)
        st.write("")
        if st.button("🚨 PANIC: CLOSE ALL", use_container_width=True, key="panic_btn"):
            msg = state.panic_close()
            st.error(msg)
            time.sleep(1); st.rerun()
        st.write("")
        pf = stats.get("profit_factor", 0.0)
        st.markdown(f"""
        <div style="background:rgba(15,23,42,0.6); border-radius:10px;
             border:1px solid rgba(255,255,255,0.05); padding: 0.8rem;">
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.5rem;">
            <div><div style="font-size:0.65rem;color:#64748B;text-transform:uppercase;letter-spacing:.06em;">Trades</div>
            <div style="font-size:1rem;font-weight:700;color:#E2E8F0;">{stats.get('total_trades',0)}</div></div>
            <div><div style="font-size:0.65rem;color:#64748B;text-transform:uppercase;letter-spacing:.06em;">Profit Factor</div>
            <div style="font-size:1rem;font-weight:700;color:#{'10B981' if pf >= 1.5 else '#FBBF24' if pf >= 1.0 else '#EF4444'};">{pf:.2f}</div></div>
            <div><div style="font-size:0.65rem;color:#64748B;text-transform:uppercase;letter-spacing:.06em;">Best Trade</div>
            <div style="font-size:1rem;font-weight:700;color:#10B981;">+${stats.get('best_trade',0.0):.2f}</div></div>
            <div><div style="font-size:0.65rem;color:#64748B;text-transform:uppercase;letter-spacing:.06em;">Worst Trade</div>
            <div style="font-size:1rem;font-weight:700;color:#EF4444;">${stats.get('worst_trade',0.0):.2f}</div></div>
          </div>
        </div>""", unsafe_allow_html=True)
        if snap.get("last_refresh"):
            dt = datetime.fromtimestamp(snap["last_refresh"], tz=timezone.utc)
            st.markdown(f'<div style="font-size:0.65rem;color:#334155;text-align:right;margin-top:0.5rem;">Refreshed {dt.strftime("%H:%M:%S")} UTC</div>', unsafe_allow_html=True)

    # ── Live Terminal ──────────────────────────────────────────────────────────
    st.markdown('<p class="sec-title">Live Bot Logs</p>', unsafe_allow_html=True)
    log_lines = state.get_log_lines()
    if log_lines:
        body = "\n".join(color_log_line(l) for l in log_lines[-120:])
    else:
        body = '<span class="log-warn">No log output yet. Start a bot to see live logs here.</span>'
    st.markdown(f"""
    <div class="terminal-wrap">
      <div class="terminal-titlebar">
        <div class="t-dot" style="background:#EF4444;"></div>
        <div class="t-dot" style="background:#FBBF24;"></div>
        <div class="t-dot" style="background:#10B981;"></div>
        <span style="margin-left:0.5rem;font-size:0.72rem;color:#475569;font-family:'JetBrains Mono',monospace;">
          logs/{snap['active_bot'].lower().replace(' ','_').replace('(','').replace(')','')}.log
        </span>
      </div>
      <div class="terminal-body" id="term-body">{body}</div>
    </div>
    <script>var el=document.getElementById('term-body');if(el)el.scrollTop=el.scrollHeight;</script>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 2 — ANALYTICS (DEEP CHARTS)
# ═══════════════════════════════════════════════════════════════════
with tab2:
    # ── Row 1: Metrics ───────────────────────────────────────────────────────
    max_dd = stats.get("max_drawdown", 0.0)
    dd_pct = round((max_dd / balance * 100), 2) if balance > 0 else 0.0
    st.markdown('<p class="sec-title">Performance Metrics</p>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="metric-grid metric-grid-5">
      <div class="mc {'positive' if net_profit>=0 else 'negative'}">
        <div class="mc-label">Net Profit ({snap['history_days']}d)</div>
        <div class="mc-value">{net_sign}${abs(net_profit):,.2f}</div>
        <div class="mc-sub">Gross: +${stats.get('gross_profit',0):,.2f} / -${abs(stats.get('gross_loss',0)):,.2f}</div>
      </div>
      <div class="mc amber">
        <div class="mc-label">Profit Factor</div>
        <div class="mc-value">{stats.get('profit_factor',0.0):.2f}</div>
        <div class="mc-sub">Gross profit / gross loss</div>
      </div>
      <div class="mc negative">
        <div class="mc-label">Max Drawdown</div>
        <div class="mc-value">${max_dd:,.2f}</div>
        <div class="mc-sub">{dd_pct}% of balance</div>
      </div>
      <div class="mc purple">
        <div class="mc-label">Avg Trade</div>
        <div class="mc-value">{'+'if stats.get('avg_profit',0)>=0 else ''}${abs(stats.get('avg_profit',0)):,.2f}</div>
        <div class="mc-sub">{stats.get('total_trades',0)} total trades</div>
      </div>
      <div class="mc cyan">
        <div class="mc-label">Expectancy</div>
        <div class="mc-value">{'+'if stats.get('avg_profit',0)>=0 else ''}${abs(round(stats.get('avg_profit',0) * (win_rate/100) - stats.get('avg_profit',0) * (1-win_rate/100) if win_rate else 0, 2)):,.2f}</div>
        <div class="mc-sub">Per-trade expected value</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Row 2: Win/Loss Donut + PnL Distribution ─────────────────────────────
    c1, c2 = st.columns([1, 1])

    with c1:
        st.markdown('<p class="sec-title">Win / Loss Breakdown</p>', unsafe_allow_html=True)
        wl = snap.get("pnl_dist", [])
        if wl:
            wins = sum(1 for v in wl if v > 0)
            losses = sum(1 for v in wl if v <= 0)
            fig = go.Figure(data=[go.Pie(
                labels=["Wins", "Losses"],
                values=[wins, losses],
                hole=0.65,
                marker=dict(colors=["#10B981", "#EF4444"]),
                textinfo="label+value",
                textfont=dict(color="#E2E8F0", size=13),
            )])
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                height=280, margin=dict(l=10, r=10, t=30, b=10),
                showlegend=False,
                annotations=[dict(
                    text=f"{win_rate}%", x=0.5, y=0.5,
                    font=dict(size=28, color="#E2E8F0", family="Inter"),
                    showarrow=False,
                )],
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.plotly_chart(render_empty_chart("No closed trades yet"), use_container_width=True)

    with c2:
        st.markdown('<p class="sec-title">PnL Distribution</p>', unsafe_allow_html=True)
        if wl:
            fig = go.Figure()
            fig.add_trace(go.Histogram(
                x=wl, nbinsx=max(10, min(50, len(wl))),
                marker=dict(color="#3B82F6", line=dict(color="rgba(59,130,246,0.2)", width=1)),
                name="PnL",
            ))
            fig.add_vline(x=0, line_dash="dash", line_color="#475569", line_width=1)
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)",
                           tickfont=dict(size=10, color="#64748B"), title="Net PnL ($)", titlefont=dict(color="#64748B", size=10)),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)",
                           tickfont=dict(size=10, color="#64748B"), title="Count", titlefont=dict(color="#64748B", size=10)),
                margin=dict(l=10, r=10, t=30, b=10),
                height=280, bargap=0.05,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.plotly_chart(render_empty_chart("No closed trades yet"), use_container_width=True)

    # ── Row 3: Daily PnL Bar + Drawdown ──────────────────────────────────────
    c3, c4 = st.columns([1, 1])

    with c3:
        st.markdown('<p class="sec-title">Daily PnL</p>', unsafe_allow_html=True)
        daily = snap.get("daily_pnl", [])
        if daily:
            df = pd.DataFrame(daily)
            df["date"] = pd.to_datetime(df["date"])
            colors = ["#10B981" if v >= 0 else "#EF4444" for v in df["pnl"]]
            fig = go.Figure(data=[go.Bar(
                x=df["date"], y=df["pnl"],
                marker_color=colors,
                text=[f"+${v:,.0f}" if v >= 0 else f"-${abs(v):,.0f}" for v in df["pnl"]],
                textposition="outside",
                textfont=dict(size=9, color="#94A3B8"),
            )])
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=False, tickfont=dict(size=9, color="#64748B")),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)",
                           tickfont=dict(size=9, color="#64748B"), tickprefix="$"),
                margin=dict(l=10, r=10, t=30, b=10),
                height=300, showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.plotly_chart(render_empty_chart("No closed trades yet"), use_container_width=True)

    with c4:
        st.markdown('<p class="sec-title">Drawdown Profile</p>', unsafe_allow_html=True)
        dd_series = snap.get("drawdown_series", [])
        if dd_series and len(dd_series) > 1:
            df_dd = pd.DataFrame(dd_series)
            df_dd["time"] = pd.to_datetime(df_dd["time"])
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_dd["time"], y=df_dd["drawdown"],
                mode="lines", fill="tozeroy",
                line=dict(color="#EF4444", width=1.5),
                fillcolor="rgba(239,68,68,0.08)",
                name="Drawdown ($)",
            ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)",
                           tickfont=dict(size=9, color="#64748B")),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)",
                           tickfont=dict(size=9, color="#64748B"), tickprefix="$", autorange="reversed"),
                margin=dict(l=10, r=10, t=30, b=10),
                height=300, showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.plotly_chart(render_empty_chart("No equity curve data yet"), use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 3 — TRADE HISTORY
# ═══════════════════════════════════════════════════════════════════
with tab3:
    st.markdown('<p class="sec-title">Filters</p>', unsafe_allow_html=True)
    fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 2])
    with fc1:
        all_syms = ["All"] + sorted(list(set(t["symbol"] for t in snap["trades"])))
        sym_filter = st.selectbox("Symbol:", all_syms, key="hist_sym")
    with fc2:
        type_filter = st.selectbox("Direction:", ["All", "BUY", "SELL"], key="hist_type")
    with fc3:
        result_filter = st.selectbox("Result:", ["All", "Win", "Loss"], key="hist_result")
    with fc4:
        month_filter = st.selectbox("Month:", ["All"] + sorted(list(set(t["close_time"][:7] for t in snap["trades"] if t.get("close_time","OPEN") != "OPEN"))), key="hist_month")

    filtered = snap["trades"]
    if sym_filter != "All":
        filtered = [t for t in filtered if t["symbol"] == sym_filter]
    if type_filter != "All":
        filtered = [t for t in filtered if t["type"] == type_filter]
    if result_filter == "Win":
        filtered = [t for t in filtered if t["net_profit"] > 0]
    elif result_filter == "Loss":
        filtered = [t for t in filtered if t["net_profit"] <= 0]
    if month_filter != "All":
        filtered = [t for t in filtered if t.get("close_time","OPEN")[:7] == month_filter]

    st.markdown(f'<p class="sec-title">Trade Log ({len(filtered)} trades)</p>', unsafe_allow_html=True)
    render_trade_table(filtered)


# ═══════════════════════════════════════════════════════════════════
# TAB 4 — OPEN POSITIONS
# ═══════════════════════════════════════════════════════════════════
with tab4:
    positions = snap["positions"]
    st.markdown('<p class="sec-title">Live Open Positions</p>', unsafe_allow_html=True)
    if not positions:
        st.markdown('<div class="empty-state">📭 No open positions. The account is flat.</div>', unsafe_allow_html=True)
    else:
        total_float = sum(p["profit"] for p in positions)
        fl_cls = "positive" if total_float >= 0 else "negative"
        fl_sign = "+" if total_float >= 0 else ""
        st.markdown(f"""
        <div class="metric-grid metric-grid-3" style="margin-bottom:1rem;">
          <div class="mc blue"><div class="mc-label">Open Positions</div><div class="mc-value">{len(positions)}</div></div>
          <div class="mc {fl_cls}"><div class="mc-label">Total Floating PnL</div><div class="mc-value">{fl_sign}${abs(total_float):,.2f}</div></div>
          <div class="mc amber"><div class="mc-label">Symbols Active</div><div class="mc-value">{len(set(p['symbol'] for p in positions))}</div></div>
        </div>""", unsafe_allow_html=True)
        cards_html = ""
        for p in positions:
            side_cls = "buy-card" if p["type"] == "BUY" else "sell-card"
            badge_cls = "buy" if p["type"] == "BUY" else "sell"
            pnl = p["profit"]
            pnl_col = "#10B981" if pnl >= 0 else "#EF4444"
            pnl_sign = "+" if pnl >= 0 else ""
            cards_html += f"""
            <div class="pos-card {side_cls}">
              <div class="pos-header">
                <div><span class="pos-symbol">{p['symbol']}</span>
                <span class="pos-badge {badge_cls}" style="margin-left:8px;">{p['type']}</span></div>
                <div style="font-size:1.2rem;font-weight:700;color:{pnl_col};">{pnl_sign}${abs(pnl):,.2f}</div>
              </div>
              <div class="pos-grid">
                <div class="pos-field"><div class="pf-label">Ticket</div><div class="pf-value">#{p['ticket']}</div></div>
                <div class="pos-field"><div class="pf-label">Volume</div><div class="pf-value">{p['volume']}</div></div>
                <div class="pos-field"><div class="pf-label">Entry</div><div class="pf-value">{p['open_price']}</div></div>
                <div class="pos-field"><div class="pf-label">Current</div><div class="pf-value">{p['current_price']}</div></div>
                <div class="pos-field"><div class="pf-label">SL</div><div class="pf-value">{p['sl'] if p['sl'] else '—'}</div></div>
                <div class="pos-field"><div class="pf-label">TP</div><div class="pf-value">{p['tp'] if p['tp'] else '—'}</div></div>
                <div class="pos-field"><div class="pf-label">Open Time</div><div class="pf-value">{p['open_time']}</div></div>
                <div class="pos-field"><div class="pf-label">Duration</div><div class="pf-value">{p['duration']}</div></div>
              </div>
            </div>"""
        st.markdown(cards_html, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 5 — BACKTESTER
# ═══════════════════════════════════════════════════════════════════
with tab5:
    st.markdown('<p class="sec-title">Quantitative Strategy Backtester</p>', unsafe_allow_html=True)
    st.info("🐆 Backtester runs on Yahoo Finance historical data. Does NOT require MT5 connection.", icon="📊")

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "backtester"))
        from engine import BacktestEngine
        from loader import StrategyLoader
        HAS_BACKTESTER = True
    except ImportError as e:
        HAS_BACKTESTER = False
        st.warning(f"⚠️ Backtester module not available: {e}. Install: `pip install -r backtester/requirements.txt`")

    if HAS_BACKTESTER:
        bt_col1, bt_col2 = st.columns([1, 3])

        with bt_col1:
            st.markdown("#### ⚙️ Configuration")
            symbol = st.selectbox("Instrument:", [
                "XAU/USD", "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD",
                "NAS100", "US30", "BTC/USD", "ETH/USD", "XAG/USD",
            ], index=0)
            tf_map = {"5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
            tf = st.selectbox("Timeframe:", list(tf_map.keys()), index=1)
            years = st.slider("Years of Data:", 1, 10, 3)
            capital = st.number_input("Initial Capital ($):", 1000, 1000000, 10000, 1000)
            risk_pct = st.slider("Risk Per Trade (%):", 0.1, 5.0, 1.0, 0.1)
            ftmo_mode = st.checkbox("FTMO Mode", value=True)

            strategies = ["Session Range Breakout", "M1 Breakout", "EMA Crossover", "RSI Mean Reversion"]
            strategy = st.selectbox("Strategy:", strategies, index=0)

            run_bt = st.button("🚀 RUN BACKTEST", type="primary", use_container_width=True)

        with bt_col2:
            if run_bt:
                with st.spinner(f"Running {strategy} on {symbol} ({tf}, {years}y)..."):
                    try:
                        loader = StrategyLoader()
                        strat_cls = loader.get(strategy)
                        engine = BacktestEngine(
                            symbol=symbol.replace("/", ""),
                            timeframe=tf,
                            years=years,
                            initial_capital=capital,
                            risk_per_trade=risk_pct / 100,
                            ftmo_mode=ftmo_mode,
                        )
                        results = engine.run(strat_cls)

                        metrics = results.get("metrics", {})
                        total_ret = metrics.get("total_return", 0)
                        sharpe = metrics.get("sharpe_ratio", 0)
                        dd = metrics.get("max_drawdown", 0)
                        wr = metrics.get("win_rate", 0)
                        pf = metrics.get("profit_factor", 0)
                        trades_count = metrics.get("total_trades", 0)

                        # FTMO Banner
                        ftmo_pass = results.get("ftmo_pass", True)
                        st.markdown(
                            f'<div class="{"ftmo-pass" if ftmo_pass else "ftmo-fail"}">{"✅ FTMO Compliant" if ftmo_pass else "❌ FTMO Rule Violations"}</div>',
                            unsafe_allow_html=True)

                        # Metrics
                        st.markdown(f"""
                        <div class="metric-grid metric-grid-6" style="margin-bottom:1rem;">
                          <div class="mc {'positive' if total_ret>=0 else 'negative'}"><div class="mc-label">Total Return</div><div class="mc-value">{total_ret:.2f}%</div></div>
                          <div class="mc blue"><div class="mc-label">Sharpe Ratio</div><div class="mc-value">{sharpe:.2f}</div></div>
                          <div class="mc negative"><div class="mc-label">Max Drawdown</div><div class="mc-value">{dd:.2f}%</div></div>
                          <div class="mc {'positive' if wr>=50 else 'negative'}"><div class="mc-label">Win Rate</div><div class="mc-value">{wr:.1f}%</div></div>
                          <div class="mc amber"><div class="mc-label">Profit Factor</div><div class="mc-value">{pf:.2f}</div></div>
                          <div class="mc purple"><div class="mc-label">Total Trades</div><div class="mc-value">{trades_count}</div></div>
                        </div>""", unsafe_allow_html=True)

                        # Equity Curve
                        curve_data = results.get("equity_curve", [])
                        if curve_data:
                            df_eq = pd.DataFrame(curve_data)
                            st.markdown('<p class="sec-title">Equity Curve & Drawdown</p>', unsafe_allow_html=True)
                            fig = go.Figure()
                            fig.add_trace(go.Scatter(
                                x=df_eq.index if "time" not in df_eq.columns else pd.to_datetime(df_eq["time"]),
                                y=df_eq["equity"] if "equity" in df_eq.columns else df_eq.iloc[:,0],
                                mode="lines", name="Equity",
                                line=dict(color="#00d4aa", width=1.5),
                                fill="tozeroy", fillcolor="rgba(0,212,170,0.06)",
                            ))
                            fig.add_hline(y=capital, line_dash="dash", line_color="#475569",
                                          annotation_text=f"Initial ${capital:,.0f}")
                            fig.update_layout(
                                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)"),
                                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickprefix="$"),
                                margin=dict(l=10, r=10, t=10, b=10), height=320, showlegend=False,
                            )
                            st.plotly_chart(fig, use_container_width=True)

                        # Trade Log
                        trades = results.get("trades", [])
                        if trades:
                            st.markdown(f'<p class="sec-title">Trade Log ({len(trades)} trades)</p>', unsafe_allow_html=True)
                            trade_rows = ""
                            for t in trades[-50:]:
                                pnl = t.get("pnl", t.get("net_profit", 0))
                                pc = "profit-pos" if pnl >= 0 else "profit-neg"
                                ps = "+" if pnl >= 0 else ""
                                trade_rows += f"""
                                <tr>
                                  <td class="mono">{t.get('entry_time','—')}</td>
                                  <td class="mono">{t.get('exit_time','—')}</td>
                                  <td>{t.get('side',t.get('type','—'))}</td>
                                  <td class="mono">{t.get('entry_price','—')}</td>
                                  <td class="mono">{t.get('exit_price','—')}</td>
                                  <td class="mono {pc}">{ps}${abs(pnl):.2f}</td>
                                  <td class="mono">{t.get('exit_reason','—')}</td>
                                </tr>"""
                            st.markdown(f"""
                            <div style="overflow-x:auto; border-radius:10px; border:1px solid rgba(255,255,255,0.06);">
                            <table class="data-table">
                              <thead><tr><th>Entry</th><th>Exit</th><th>Side</th><th>Entry$</th><th>Exit$</th><th>PnL</th><th>Reason</th></tr></thead>
                              <tbody>{trade_rows}</tbody>
                            </table></div>""", unsafe_allow_html=True)

                    except Exception as e:
                        st.error(f"Backtest failed: {e}")
            else:
                st.markdown("""
                <div class="empty-state" style="padding:6rem 3rem;">
                  <div style="font-size:3rem; margin-bottom:1rem;">🐆</div>
                  <div style="font-size:1.1rem; color:#94A3B8; margin-bottom:0.5rem;">Configure & Run a Backtest</div>
                  <div style="font-size:0.8rem; color:#475569;">Select instrument, timeframe, strategy, and hit <b>RUN BACKTEST</b>.</div>
                </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 6 — AGENT NETWORK
# ═══════════════════════════════════════════════════════════════════
with tab6:
    st.markdown('<p class="sec-title">Multi-Agent Orchestration Network</p>', unsafe_allow_html=True)
    st.info("🧠 Shows the real-time status of the multi-agent trading system. Agents coordinate to analyze, validate, and execute trades.")

    # Try to load agent orchestrator
    agent_data_available = False
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "agents"))
        from orchestrator import Orchestrator
        orch = Orchestrator()
        agent_statuses = orch.get_agent_statuses() if hasattr(orch, 'get_agent_statuses') else {}
        agent_data_available = bool(agent_statuses)
    except Exception:
        agent_statuses = {}

    # Agent definitions
    AGENTS = [
        {"id": "ta", "name": "📈 Technical Analysis", "role": "Pattern Scanner", "color": "#60A5FA",
         "stats": ["Signal: NEUTRAL", "Last scan: —", "Symbol: —", "Confidence: —"]},
        {"id": "sentiment", "name": "🌊 Market Sentiment", "role": "Volume & Bias", "color": "#A78BFA",
         "stats": ["Bias: NEUTRAL", "Volume ratio: —", "Pressure: —", "Confidence: —"]},
        {"id": "risk", "name": "🛡️ Risk Management", "role": "Drawdown Guard", "color": "#FBBF24",
         "stats": ["Current DD: 0.0%", "Daily limit: OK", "Total limit: OK", "Position cap: —"]},
        {"id": "portfolio", "name": "💼 Portfolio Allocator", "role": "Capital Distribution", "color": "#22D3EE",
         "stats": ["Alloc %: —", "Max risk/sym: —", "Active syms: 0", "Rebalance: IDLE"]},
        {"id": "macro", "name": "📰 Macro Event", "role": "News Hazard Block", "color": "#F472B6",
         "stats": ["Hazards active: 0", "Next event: —", "Blackout: NO", "Impact: LOW"]},
        {"id": "execution", "name": "⚡ Order Execution", "role": "Fill Engine", "color": "#10B981",
         "stats": ["Last fill: —", "Slippage: —", "Latency: — ms", "Status: IDLE"]},
    ]

    # Override with real data if available
    if agent_data_available:
        for agent in AGENTS:
            real = agent_statuses.get(agent["id"], {})
            if real:
                agent["stats"] = real.get("stats", agent["stats"])
                agent["real"] = True

    st.markdown('<div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:1rem; margin-bottom:1.5rem;">', unsafe_allow_html=True)
    for a in AGENTS:
        is_active = agent_data_available and a.get("real")
        badge = '<span class="agent-badge-active">LIVE</span>' if is_active else '<span class="agent-badge-idle">STANDBY</span>'
        stats_html = "".join(f'<div class="agent-stat">{s}</div>' for s in a["stats"])
        st.markdown(f"""
        <div class="agent-card" style="border-top: 2px solid {a['color']};">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div class="agent-name">{a['name']}</div>{badge}
          </div>
          <div class="agent-role">{a['role']}</div>
          {stats_html}
        </div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # Agent activity feed
    st.markdown('<p class="sec-title">Agent Activity Feed</p>', unsafe_allow_html=True)
    if agent_data_available and hasattr(orch, 'get_activity_log'):
        activity = orch.get_activity_log()
        feed_html = "\n".join(color_log_line(line) for line in activity[-80:])
        st.markdown(f"""
        <div class="terminal-wrap">
          <div class="terminal-titlebar">
            <div class="t-dot" style="background:#EF4444;"></div>
            <div class="t-dot" style="background:#FBBF24;"></div>
            <div class="t-dot" style="background:#10B981;"></div>
            <span style="margin-left:0.5rem;font-size:0.72rem;color:#475569;font-family:'JetBrains Mono',monospace;">orchestrator.log</span>
          </div>
          <div class="terminal-body" style="height:250px;">{feed_html}</div>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown('<div class="empty-state" style="padding:2rem;">🧠 Agent orchestrator is in standby. Run the multi-agent bot to see live agent activity.</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 7 — EDITOR & DEPLOY
# ═══════════════════════════════════════════════════════════════════
with tab7:
    e1, e2 = st.columns([3, 2])

    with e1:
        st.markdown('<p class="sec-title">In-Browser Bot Script Editor</p>', unsafe_allow_html=True)
        st.warning("⚠️ Changes are written directly to disk. Stop the bot before editing to avoid conflicts.", icon="⚠️")
        bots_dir = Path(__file__).resolve().parent / "bots"
        if bots_dir.is_dir():
            bot_files = sorted(bots_dir.glob("*.py"))
            if bot_files:
                file_names = [f.name for f in bot_files]
                selected = st.selectbox("Select Script:", file_names, key="editor_file")
                file_path = bots_dir / selected
                try:
                    content = file_path.read_text(encoding="utf-8")
                except Exception as ex:
                    content = f"# Error reading file: {ex}"
                edited = st.text_area("Source Code:", value=content, height=420, key="editor_code")
                if st.button("💾 Save Script", type="primary", use_container_width=True):
                    try:
                        file_path.write_text(edited, encoding="utf-8")
                        st.success(f"✅ Saved {selected}")
                    except Exception as ex:
                        st.error(f"Save failed: {ex}")
            else:
                st.info("No .py scripts found in bots/ directory.")
        else:
            st.error("bots/ directory not found.")

    with e2:
        st.markdown('<p class="sec-title">Deployment Guide</p>', unsafe_allow_html=True)
        st.markdown("#### 📦 1. Update .env")
        st.code('APP_URL=http://inventra.website\nOWNER_EMAIL=whalasahib@gmail.com', language="bash")
        st.markdown("#### 🚀 2. Run Streamlit")
        st.code('python -m streamlit run dashboard.py --server.port 80 --server.address 0.0.0.0', language="powershell")
        st.markdown("#### 🔒 3. AWS Security Group")
        st.table({"Port": ["80", "443", "8501"], "Protocol": ["TCP", "TCP", "TCP"], "Source": ["0.0.0.0/0", "0.0.0.0/0", "0.0.0.0/0"]})
        st.markdown("#### 🌐 4. Cloudflare DNS")
        st.code("Type: A  |  Name: @  |  Value: <AWS_IP>  |  Proxy: DNS Only", language="yaml")
        st.markdown("#### 🔑 5. Google OAuth")
        st.code("""# .env
GOOGLE_CLIENT_ID=your_id
GOOGLE_CLIENT_SECRET=your_secret
APP_URL=http://inventra.website""", language="bash")
        st.caption("Add `http://inventra.website` as authorized redirect URI in Google Cloud Console → Credentials.")

        st.markdown("---")
        st.markdown("#### 📊 MT5 Connection Requirements")
        st.markdown("""
        - ✅ **Windows OS** (required — MT5 API is Windows-only)
        - ✅ **MetaTrader 5 terminal** installed and logged in
        - ✅ **Algo Trading** enabled (Ctrl+E in MT5)
        - ✅ **mt5_config.json** with correct credentials
        - ✅ **XAUUSD** in Market Watch
        """)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    new_days = st.slider("History Period (days):", 7, 90, snap["history_days"], key="days_slider")
    if new_days != snap["history_days"]:
        state.update_config(history_days=new_days)
        st.rerun()
    st.markdown("---")
    st.markdown("### 📊 Quick Stats")
    st.metric("Connected", "✅" if snap["connected"] else "❌")
    st.metric("Bot Running", "✅" if snap["bot_running"] else "❌")
    st.metric("Open Positions", len(snap["positions"]))
    st.markdown("---")
    if st.button("🚪 Sign Out", use_container_width=True):
        sign_out()


# ── Auto-refresh ──────────────────────────────────────────────────────────────
time.sleep(3)
st.rerun()
