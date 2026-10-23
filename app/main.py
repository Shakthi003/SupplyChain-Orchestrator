"""
app/main.py -- Streamlit planner UI

Talks ONLY to the FastAPI backend (never to the databases directly).

Run (two terminals):
  uv run uvicorn api.main:app --reload
  uv run streamlit run app/main.py

Styling notes:
  - Light theme comes from .streamlit/config.toml; the custom look is the CSS below.
  - Any text that can contain '$' is passed through md() (Streamlit markdown) or h()
    (our HTML blocks). h() writes '$' as an HTML entity, so Streamlit never mistakes
    "$20,300 ... $4,800" for LaTeX math.
"""

import html as _html
import os
import re
from datetime import datetime

import httpx
import pandas as pd
import streamlit as st

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="SupplyChain Orchestrator", page_icon="◈", layout="wide")


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api(method: str, path: str, **kwargs):
    """Call the backend. Returns (data, error_message)."""
    try:
        r = httpx.request(method, f"{API_URL}{path}", timeout=300, **kwargs)
    except httpx.HTTPError as e:
        return None, f"Cannot reach the API at {API_URL} ({e.__class__.__name__}). Is uvicorn running?"
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        return None, f"{r.status_code}: {detail}"
    return r.json(), None


def money(x) -> str:
    return f"${x:,.2f}"


def md(text) -> str:
    """Escape '$' so Streamlit does not treat 'US$ ... US$' as LaTeX math."""
    return str(text).replace("$", "\\$")


def h(text) -> str:
    """Make text safe to place inside our own HTML blocks (escapes tags and '$')."""
    return _html.escape(str(text)).replace("$", "&#36;")


def html(block: str):
    """Render an HTML block. Newlines + indentation are removed first, because
    Streamlit's markdown would turn indented lines into a code block."""
    st.markdown(re.sub(r"\n\s*", "", block.strip()), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Look & feel (light "control tower" theme)
# ---------------------------------------------------------------------------

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Inter:wght@400;500;600;700&display=swap');
:root{--ink:#0F1B2D;--muted:#5B6B80;--line:#E3E0D8;--paper:#F7F5F0;--indigo:#2F3FD0;--signal:#E5484D;--ok:#0E9F6E;--amber:#D98A0B;}
.stApp{background-color:var(--paper);background-image:linear-gradient(rgba(15,27,45,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(15,27,45,.045) 1px,transparent 1px);background-size:34px 34px;}
html,body,[class*="css"],.stApp{font-family:'Inter','Segoe UI',system-ui,sans-serif;color:var(--ink);}
header[data-testid="stHeader"]{background:transparent;}
.block-container{padding-top:1.6rem;max-width:1280px;}
h1,h2,h3{font-family:'Fraunces',Georgia,serif;letter-spacing:-.01em;color:var(--ink);}
[data-testid="stSidebar"]{background:#FFFFFF;border-right:1px solid var(--line);}
[data-testid="stSidebar"] .block-container{padding-top:1.2rem;}
.stButton>button{border-radius:10px;font-weight:600;border:1px solid var(--line);padding:.55rem 1rem;transition:all .15s ease;}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"]{background:linear-gradient(135deg,#2F3FD0,#5B3FD0);color:#fff;border:none;box-shadow:0 6px 18px rgba(47,63,208,.28);}
.stButton>button[kind="primary"]:hover,.stFormSubmitButton>button[kind="primary"]:hover{transform:translateY(-1px);box-shadow:0 10px 24px rgba(47,63,208,.34);}
.stFormSubmitButton>button{border-radius:10px;font-weight:600;}
[data-baseweb="tab-list"]{gap:6px;background:#fff;border:1px solid var(--line);padding:5px;border-radius:14px;width:fit-content;max-width:100%;}
[data-baseweb="tab"]{border-radius:10px;padding:8px 16px;height:auto;color:var(--muted);font-weight:600;}
[data-baseweb="tab"][aria-selected="true"]{background:var(--ink);color:#fff;}
[data-baseweb="tab-highlight"],[data-baseweb="tab-border"]{display:none;}
[data-baseweb="tab-panel"]{padding-top:1.1rem;}
[data-testid="stForm"]{background:#fff;border:1px solid var(--line);border-radius:16px;padding:1.2rem;}
.stTextInput input,.stTextArea textarea,[data-baseweb="select"]>div{border-radius:10px;}
[data-testid="stExpander"]{background:#fff;border:1px solid var(--line);border-radius:14px;}
[data-testid="stCode"]{border:1px solid var(--line);border-radius:12px;}
[data-testid="stVerticalBlockBorderWrapper"]{border-radius:16px;}
.sc-hero{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap;padding:6px 2px 18px 2px;}
.sc-brand{display:flex;align-items:center;gap:14px;}
.sc-mark{width:46px;height:46px;border-radius:14px;background:conic-gradient(from 210deg,#2F3FD0,#5B3FD0,#E5484D,#2F3FD0);display:flex;align-items:center;justify-content:center;box-shadow:0 8px 20px rgba(47,63,208,.28);}
.sc-mark b{display:block;width:20px;height:20px;border-radius:6px;background:#fff;transform:rotate(45deg);}
.sc-title{font-family:'Fraunces',Georgia,serif;font-size:30px;font-weight:600;line-height:1.1;margin:0;}
.sc-sub{color:var(--muted);font-size:13.5px;margin-top:3px;}
.sc-rule{display:flex;gap:8px;flex-wrap:wrap;}
.sc-pill{background:#fff;border:1px solid var(--line);border-radius:999px;padding:6px 12px;font-size:12px;color:var(--muted);}
.sc-pill b{color:var(--ink);}
.sc-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:6px 0 16px 0;}
.sc-metric{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px 18px;position:relative;overflow:hidden;}
.sc-metric:before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:var(--accent,var(--indigo));}
.sc-metric .k{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);}
.sc-metric .v{font-family:'Fraunces',Georgia,serif;font-size:34px;font-weight:600;line-height:1.15;margin-top:4px;}
.sc-metric .s{font-size:12.5px;color:var(--muted);margin-top:2px;}
.sc-flow{display:flex;align-items:stretch;margin:6px 0 16px 0;}
.sc-node{flex:1;background:#fff;border:1px solid var(--line);border-radius:14px;padding:13px 15px;min-width:0;}
.sc-node .k{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);display:flex;align-items:center;gap:7px;}
.sc-node .v{font-weight:650;font-size:14.5px;margin-top:4px;overflow:hidden;text-overflow:ellipsis;}
.sc-node .s{font-size:12px;color:var(--muted);margin-top:2px;}
.sc-node.bad{border-color:#F1B4B6;background:linear-gradient(180deg,#FFF6F6,#fff);}
.sc-node.warn{border-color:#EBCB8B;background:linear-gradient(180deg,#FFFAF0,#fff);}
.sc-dot{width:8px;height:8px;border-radius:50%;background:var(--ok);display:inline-block;}
.sc-dot.bad{background:var(--signal);animation:scpulse 1.6s infinite;}
.sc-dot.warn{background:var(--amber);}
@keyframes scpulse{0%{box-shadow:0 0 0 0 rgba(229,72,77,.55);}100%{box-shadow:0 0 0 10px rgba(229,72,77,0);}}
.sc-link{width:84px;flex:none;display:flex;flex-direction:column;align-items:center;justify-content:center;font-size:11px;color:var(--muted);gap:5px;}
.sc-link i{display:block;width:100%;height:2px;background:repeating-linear-gradient(90deg,#9AA6B6 0 6px,transparent 6px 10px);}
.sc-link.bad{color:var(--signal);font-weight:700;}
.sc-link.bad i{background:repeating-linear-gradient(90deg,#E5484D 0 6px,transparent 6px 10px);}
.sc-verdict{display:flex;align-items:center;gap:12px;border-radius:14px;padding:13px 16px;margin:0 0 16px 0;border:1px solid;}
.sc-verdict.bad{background:#FFF1F1;border-color:#F1B4B6;}
.sc-verdict.ok{background:#EAF8F2;border-color:#A8DEC7;}
.sc-verdict .tag{font-size:11px;font-weight:700;letter-spacing:.1em;padding:4px 10px;border-radius:999px;color:#fff;white-space:nowrap;}
.sc-verdict.bad .tag{background:var(--signal);}
.sc-verdict.ok .tag{background:var(--ok);}
.sc-verdict .tx{font-size:14px;}
.sc-card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:18px 20px;margin-bottom:14px;}
.sc-card h4{margin:0 0 4px 0;font-size:13px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:600;}
.sc-tl{position:relative;height:112px;margin:10px 18px 4px 18px;}
.sc-track{position:absolute;left:0;right:0;top:50px;height:12px;border-radius:7px;background:#ECE9E1;overflow:hidden;}
.sc-seg{position:absolute;top:0;bottom:0;}
.sc-mk{position:absolute;transform:translateX(-50%);text-align:center;font-size:11.5px;line-height:1.3;white-space:nowrap;}
.sc-mk b{display:block;font-size:12px;}
.sc-mk span{color:var(--muted);}
.sc-mk i{display:block;width:2px;background:var(--ink);margin:0 auto;}
.sc-mk.up{top:0;}
.sc-mk.up i{height:20px;}
.sc-mk.dn{top:64px;}
.sc-mk.dn i{height:12px;}
.sc-legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:6px;}
.sc-legend em{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px;}
.sc-facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;}
.sc-fact .k{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);}
.sc-fact .v{font-weight:600;font-size:14.5px;margin-top:2px;}
.sc-table{width:100%;border-collapse:separate;border-spacing:0;background:#fff;border:1px solid var(--line);border-radius:14px;overflow:hidden;font-size:13.5px;}
.sc-table th{background:#F2F0EA;text-align:left;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);padding:10px 14px;}
.sc-table td{padding:11px 14px;border-top:1px solid var(--line);vertical-align:top;}
.sc-table td.num{text-align:right;font-variant-numeric:tabular-nums;}
.sc-opt{background:#fff;border:1px solid var(--line);border-radius:18px;padding:18px 20px;margin-bottom:14px;position:relative;}
.sc-opt.rec{border-color:var(--indigo);box-shadow:0 10px 30px rgba(47,63,208,.13);}
.sc-opt.no{background:#FBFAF7;}
.sc-opt.no .ttl{color:var(--muted);}
.sc-opt .top{display:flex;align-items:center;gap:14px;}
.sc-rank{width:38px;height:38px;border-radius:12px;background:var(--ink);color:#fff;font-weight:700;display:flex;align-items:center;justify-content:center;flex:none;}
.sc-opt.rec .sc-rank{background:linear-gradient(135deg,#2F3FD0,#5B3FD0);}
.sc-opt.no .sc-rank{background:#C9C5BA;}
.sc-opt .ttl{font-weight:650;font-size:16px;}
.sc-opt .id{font-size:12px;color:var(--muted);}
.sc-chip{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.06em;padding:3px 10px;border-radius:999px;margin-left:8px;vertical-align:2px;}
.sc-chip.rec{background:#E7E9FB;color:var(--indigo);}
.sc-chip.ok{background:#E3F6EE;color:#0B7A55;}
.sc-chip.no{background:#F6E3E3;color:#B03A3F;}
.sc-opt .stats{margin-left:auto;display:flex;gap:22px;text-align:right;}
.sc-opt .stats .k{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);}
.sc-opt .stats .v{font-weight:650;font-size:16px;font-variant-numeric:tabular-nums;}
.sc-bar{height:6px;border-radius:4px;background:#ECE9E1;margin:14px 0 12px 0;overflow:hidden;}
.sc-bar span{display:block;height:100%;background:linear-gradient(90deg,#2F3FD0,#5B3FD0);}
.sc-opt p{margin:6px 0;font-size:13.5px;color:#27364B;}
.sc-opt p b{color:var(--ink);}
.sc-src{display:inline-block;background:#fff;border:1px solid var(--line);border-radius:10px;padding:8px 14px;margin:0 8px 8px 0;font-size:13px;font-weight:600;}
.sc-src:before{content:"";display:inline-block;width:8px;height:8px;border-radius:2px;background:var(--indigo);margin-right:9px;}
@media (max-width:900px){.sc-metrics{grid-template-columns:repeat(2,1fr);}.sc-flow{flex-direction:column;}.sc-link{width:100%;height:30px;}}
"""
html(f"<style>{CSS}</style>")


# ---------------------------------------------------------------------------
# Small rendering helpers
# ---------------------------------------------------------------------------

def parse_day(s):
    """'2026-10-29' or ISO datetime -> datetime (midnight). None if unparseable."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def fmt_day(d) -> str:
    return d.strftime("%b %d") if d else "n/a"


def metric(label, value, sub, accent="var(--indigo)") -> str:
    return (f'<div class="sc-metric" style="--accent:{accent}"><div class="k">{h(label)}</div>'
            f'<div class="v">{h(value)}</div><div class="s">{h(sub)}</div></div>')


def node(label, value, sub, state="", dot="") -> str:
    return (f'<div class="sc-node {state}"><div class="k"><span class="sc-dot {dot}"></span>{h(label)}</div>'
            f'<div class="v">{h(value)}</div><div class="s">{h(sub)}</div></div>')


def runway(imp: dict, detected) -> str:
    """Signature visual: stock runway vs. the late shipment, on one timeline."""
    start = detected
    stock_out = parse_day(imp.get("shortage_date"))
    eta0 = parse_day(imp.get("original_eta"))
    eta1 = parse_day(imp.get("revised_eta"))
    days = [d for d in (start, stock_out, eta0, eta1) if d]
    if not start or len(days) < 2:
        return ""
    end = max(days)
    span = max((end - start).days, 1)

    def pct(d):
        return min(max((d - start).days / span * 100, 0), 100)

    segs = ""
    if stock_out and eta1 and stock_out < eta1:
        a, b = pct(stock_out), pct(eta1)
        segs += f'<div class="sc-seg" style="left:0;width:{a:.1f}%;background:#34B58A"></div>'
        segs += (f'<div class="sc-seg" style="left:{a:.1f}%;width:{b - a:.1f}%;'
                 'background:repeating-linear-gradient(135deg,#E5484D 0 6px,#F4A5A8 6px 12px)"></div>')
    else:
        segs += '<div class="sc-seg" style="left:0;width:100%;background:#34B58A"></div>'

    marks = [("Detected", start, "up")]
    if stock_out:
        marks.append(("Stock-out", stock_out, "dn"))
    if eta0:
        marks.append(("Original ETA", eta0, "up"))
    if eta1 and eta1 != eta0:
        marks.append(("Revised ETA", eta1, "dn"))
    mk = "".join(
        f'<div class="sc-mk {pos}" style="left:{pct(d):.1f}%">'
        + (f'<b>{h(name)}</b><span>{fmt_day(d)}</span><i></i>' if pos == "up"
           else f'<i></i><b>{h(name)}</b><span>{fmt_day(d)}</span>')
        + '</div>'
        for name, d, pos in marks
    )
    gap = ""
    if stock_out and eta1 and stock_out < eta1:
        gap = f" · {(eta1 - stock_out).days} days with no stock"
    return (
        '<div class="sc-card"><h4>Stock runway</h4>'
        f'<div class="sc-tl"><div class="sc-track">{segs}</div>{mk}</div>'
        '<div class="sc-legend"><span><em style="background:#34B58A"></em>Stock covers demand</span>'
        '<span><em style="background:#E5484D"></em>No stock, waiting for shipment</span>'
        f'<span>{h(gap.strip(" ·"))}</span></div></div>'
    )


def orders_table(rows, cols) -> str:
    """cols: list of (header, key, formatter-or-None, css-class)."""
    head = "".join(f"<th>{h(c[0])}</th>" for c in cols)
    body = ""
    for r in rows:
        tds = ""
        for _, key, fn, cls in cols:
            v = r.get(key, "")
            tds += f'<td class="{cls}">{h(fn(v) if fn else v)}</td>'
        body += f"<tr>{tds}</tr>"
    return f'<table class="sc-table"><tr>{head}</tr>{body}</table>'


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

html("""
<div class="sc-hero">
  <div class="sc-brand"><div class="sc-mark"><b></b></div>
    <div><div class="sc-title">SupplyChain Orchestrator</div>
    <div class="sc-sub">Explainable disruption risk &amp; recovery planning</div></div></div>
  <div class="sc-rule">
    <span class="sc-pill"><b>Numbers</b> = engines</span>
    <span class="sc-pill"><b>Words</b> = AI</span>
    <span class="sc-pill"><b>Decisions</b> = you</span>
  </div>
</div>
""")

# ---------------------------------------------------------------------------
# Sidebar: pick an event, run the analysis
# ---------------------------------------------------------------------------

events, err = api("GET", "/events")
if err:
    st.error(err)
    st.stop()
if not events:
    st.warning("No events found. Run the data scripts first.")
    st.stop()

with st.sidebar:
    st.markdown("### Disruption event")
    labels = {f"{e['event_id']} [{e['severity']}, {e['status']}]": e for e in events}
    chosen = labels[st.selectbox("Event", list(labels), label_visibility="collapsed")]
    event_id = chosen["event_id"]
    st.write(md(chosen["description"]))
    st.caption(f"Type: {chosen['event_type']} · Detected: {chosen['detected_at']}")
    run = st.button("Run analysis", type="primary", width="stretch")
    st.caption("First run can take ~30-60 s")
    st.caption("Decision support on synthetic data. Nothing is executed.")

if run:
    with st.spinner("Running impact analysis, planning, graph, retrieval and AI explanation..."):
        data, err = api("POST", f"/events/{event_id}/analyze")
    if err:
        st.session_state.pop("analysis", None)
        st.error(err)
    else:
        st.session_state["analysis"] = data
        st.session_state.pop("decision_result", None)

analysis = st.session_state.get("analysis")
if not analysis or analysis.get("event_id") != event_id:
    st.info("Select an event and click **Run analysis**.")
    st.stop()

imp = analysis["impact"]
plan = analysis["planning"]
graph = analysis.get("graph") or {}
docs = analysis.get("documents") or {}
detected = parse_day(analysis["event"]["detected_at"])
shortage = bool(imp.get("has_shortage"))


# ---------------------------------------------------------------------------
# Top summary: KPIs, disruption flow, verdict, runway
# ---------------------------------------------------------------------------

cov = imp.get("coverage_days", 0)
html('<div class="sc-metrics">' + "".join([
    metric("Delay", f"{imp.get('delay_days', 0)} days", f"{imp.get('supplier_name', '')} shipment", "var(--amber)"),
    metric("Stock coverage", f"{cov} days", f"{imp.get('total_available', 0):,.0f} units on hand",
           "var(--signal)" if shortage else "var(--ok)"),
    metric("Exposure", money(imp.get("total_exposure", 0)), "orders actually at risk", "var(--indigo)"),
    metric("Cost of doing nothing", money(plan.get("doing_nothing_cost", 0)), "engine estimate", "var(--ink)"),
]) + '</div>')

bad = "bad" if shortage else ""
html('<div class="sc-flow">'
     + node("Supplier", imp.get("supplier_name", ""), imp.get("supplier_id", ""), "warn", "warn")
     + f'<div class="sc-link {bad}"><span>+{imp.get("delay_days", 0)}d late</span><i></i></div>'
     + node("Part", imp.get("part_name", ""), imp.get("part_id", ""), bad, bad)
     + f'<div class="sc-link {bad}"><span>{len(imp.get("affected_products", []))} products</span><i></i></div>'
     + node("Verdict", imp.get("verdict", ""),
            f"Stock-out {imp['shortage_date']}" if imp.get("shortage_date") else "No stock-out",
            bad, bad)
     + '</div>')

html(f'<div class="sc-verdict {"bad" if shortage else "ok"}">'
     f'<span class="tag">{"SHORTAGE" if shortage else "OK"}</span>'
     f'<span class="tx">{h(imp.get("verdict", ""))}</span></div>')

rw = runway(imp, detected)
if rw:
    html(rw)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_impact, tab_opts, tab_graph, tab_docs, tab_ai, tab_dec = st.tabs(
    ["Impact", "Recovery options", "Impact chain", "Evidence", "AI explanation", "Decision"]
)

# --- Impact -----------------------------------------------------------------
with tab_impact:
    html('<div class="sc-card"><h4>Disruption facts</h4><div class="sc-facts">'
         + "".join(
             f'<div class="sc-fact"><div class="k">{h(k)}</div><div class="v">{h(v)}</div></div>'
             for k, v in [
                 ("Part", f"{imp.get('part_name', '')} ({imp.get('part_id', '')})"),
                 ("Supplier", f"{imp.get('supplier_name', '')} ({imp.get('supplier_id', '')})"),
                 ("Original ETA", imp.get("original_eta") or "n/a"),
                 ("Revised ETA", imp.get("revised_eta") or "n/a"),
                 ("Daily consumption", f"{imp.get('daily_consumption', 0):,.1f} units"),
                 ("Shortage date", imp.get("shortage_date") or "none"),
                 ("Affected products", ", ".join(imp.get("affected_products", [])) or "none"),
             ])
         + '</div></div>')

    st.markdown("##### Production orders at risk")
    if imp.get("at_risk_prod_orders"):
        html(orders_table(imp["at_risk_prod_orders"], [
            ("Order", "order_id", None, ""), ("Product", "product_name", None, ""),
            ("Qty", "quantity", lambda v: f"{v:,.0f}", "num"), ("Starts", "planned_start", None, ""),
            ("Units needed", "units_needed", lambda v: f"{v:,.0f}", "num"), ("Why", "risk_reason", None, ""),
        ]))
    else:
        st.write("None.")

    st.markdown("##### Customer orders at risk")
    if imp.get("at_risk_cust_orders"):
        html(orders_table(imp["at_risk_cust_orders"], [
            ("Order", "order_id", None, ""), ("Customer", "customer", None, ""),
            ("Value", "value", money, "num"), ("Promised", "delivery_date", None, ""),
            ("Production order", "linked_prod_order", None, ""),
        ]))
    else:
        st.write("None.")

# --- Recovery options ---------------------------------------------------------
with tab_opts:
    options = plan.get("options", [])
    rec_id = plan.get("recommended_option_id")
    st.caption("Every figure below comes from the deterministic planner. Infeasible options are shown muted.")
    for o in sorted(options, key=lambda x: x.get("rank", 99)):
        feasible = o.get("status") == "feasible"
        is_rec = o["option_id"] == rec_id
        cls = "rec" if is_rec else ("" if feasible else "no")
        chips = ('<span class="sc-chip rec">RECOMMENDED</span>' if is_rec else "") + \
                (f'<span class="sc-chip {"ok" if feasible else "no"}">{h(o.get("status", "").upper())}</span>')
        score = max(0, min(float(o.get("score", 0)), 100))
        rows = ""
        for lab, key in [("Description", "description"), ("Feasibility", "feasibility_note"),
                         ("Cost", "cost_note"), ("Why", "recommendation_reason")]:
            if o.get(key):
                rows += f"<p><b>{lab}:</b> {h(o[key])}</p>"
        html(f'<div class="sc-opt {cls}"><div class="top">'
             f'<div class="sc-rank">{h(o.get("rank", "-"))}</div>'
             f'<div><div class="ttl">{h(o.get("title", ""))}{chips}</div>'
             f'<div class="id">{h(o["option_id"])}</div></div>'
             f'<div class="stats"><div><div class="k">Cost</div><div class="v">{h(money(o.get("cost", 0)))}</div></div>'
             f'<div><div class="k">Score</div><div class="v">{score:.1f}</div></div></div></div>'
             f'<div class="sc-bar"><span style="width:{score:.0f}%"></span></div>{rows}</div>')

# --- Impact chain (graph) -------------------------------------------------------
with tab_graph:
    chain = (graph.get("chain") or {}).get("chain_text")
    if graph.get("error") or not chain:
        st.warning("Graph data unavailable (is the Neo4j instance running?). The other tabs are unaffected.")
    else:
        st.caption(
            "Shows every customer order that depends on this supplier through the BOM (structure only). "
            "The Impact tab shows only the orders actually at risk given current stock, so the totals differ by design."
        )
        st.code(chain, language=None)
        spare = (graph.get("spare_stock") or {}).get("spare_text")
        if spare:
            st.code(spare, language=None)

# --- Evidence ---------------------------------------------------------------------
with tab_docs:
    sources = docs.get("sources_used") or []
    if sources:
        html("".join(f'<span class="sc-src">{h(s)}</span>' for s in sources))
    else:
        st.write("No sources retrieved.")
    if docs.get("error"):
        st.error(docs["error"])
    if docs.get("combined_context"):
        with st.expander("Retrieved text"):
            st.text(docs["combined_context"])

# --- AI explanation -----------------------------------------------------------------
with tab_ai:
    text = analysis.get("explanation") or ""
    if text.startswith("[AI explanation unavailable"):
        st.warning("The AI service was unavailable; showing the fallback summary. Re-run the analysis to retry.")
    st.caption("Written by the language model from the engine's numbers. It never calculates.")
    st.write(md(text))

# --- Decision ---------------------------------------------------------------------------
with tab_dec:
    feasible_opts = [o for o in plan.get("options", []) if o.get("status") == "feasible"]
    result = st.session_state.get("decision_result")
    if result:
        verb = "APPROVED" if result["approved"] else "REJECTED"
        st.success(f'Decision {result["decision_id"]} saved: {verb} {result["chosen_option_id"]}.')
    else:
        st.info("Nothing is executed. Your decision is recorded in the audit log only.")
        ids = [o["option_id"] for o in feasible_opts]
        default = ids.index(plan["recommended_option_id"]) if plan.get("recommended_option_id") in ids else 0
        titles = {o["option_id"]: f"{o['option_id']} - {o['title']}" for o in feasible_opts}
        with st.form("decision_form"):
            name = st.text_input("Your name")
            choice = st.selectbox("Option", ids, index=default if ids else None, format_func=lambda i: titles[i])
            rationale = st.text_area("Rationale (required)")
            c1, c2 = st.columns(2)
            approve = c1.form_submit_button("Approve", type="primary", width="stretch")
            reject = c2.form_submit_button("Reject", width="stretch")
        if approve or reject:
            if not name.strip() or not rationale.strip():
                st.error("Name and rationale are required.")
            else:
                saved, err = api("POST", f"/events/{event_id}/decision", json={
                    "approved": bool(approve), "reviewer_name": name.strip(),
                    "rationale": rationale.strip(), "chosen_option_id": choice,
                })
                if err:
                    st.error(err)
                else:
                    st.session_state["decision_result"] = saved
                    st.rerun()

    st.markdown("##### Audit log")
    log, err = api("GET", f"/decisions?event_id={event_id}")
    if err:
        st.error(err)
    elif log:
        st.dataframe(pd.DataFrame(log), width="stretch", hide_index=True)
    else:
        st.write("No decisions recorded yet.")
