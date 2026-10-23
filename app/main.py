"""
app/main.py -- Streamlit planner UI

Talks ONLY to the FastAPI backend (never to the databases directly).

Run (two terminals):
  uv run uvicorn api.main:app --reload
  uv run streamlit run app/main.py
"""

import os

import httpx
import pandas as pd
import streamlit as st

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="SupplyChain Orchestrator", layout="wide")


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


# ---------------------------------------------------------------------------
# Sidebar: pick an event
# ---------------------------------------------------------------------------

st.title("SupplyChain Orchestrator")
st.caption("Decision support on synthetic data. Numbers come from deterministic engines; "
           "the AI only explains them; a human makes the decision.")

events, err = api("GET", "/events")
if err:
    st.error(err)
    st.stop()
if not events:
    st.warning("No disruption events in the database.")
    st.stop()

with st.sidebar:
    st.header("Disruption event")
    labels = {e["event_id"]: f'{e["event_id"]} [{e["severity"]}, {e["status"]}]' for e in events}
    event_id = st.selectbox("Event", list(labels), format_func=labels.get)
    event = next(e for e in events if e["event_id"] == event_id)
    st.write(md(event["description"]))
    st.caption(f'Type: {event["event_type"]}  |  Detected: {event["detected_at"]}')

    run = st.button("Run analysis", type="primary", width="stretch")
    st.caption("First run can take ~30-60 s (document search + AI explanation).")

if run:
    with st.spinner("Running impact analysis, recovery planning, graph, documents, AI explanation..."):
        data, err = api("POST", f"/events/{event_id}/analyze")
    if err:
        st.session_state.pop("analysis", None)
        st.error(err)
    else:
        st.session_state["analysis"] = data
        st.session_state.pop("decision_result", None)

analysis = st.session_state.get("analysis")
if not analysis or analysis["event_id"] != event_id:
    st.info("Select an event and click **Run analysis**.")
    st.stop()

impact, planning = analysis["impact"], analysis["planning"]
graph, docs = analysis["graph"] or {}, analysis["documents"] or {}

# ---------------------------------------------------------------------------
# Headline numbers
# ---------------------------------------------------------------------------

c1, c2, c3, c4 = st.columns(4)
c1.metric("Delay", f'{impact["delay_days"]} days')
c2.metric("Stock available", f'{impact["total_available"]:.0f} units')
c3.metric("Coverage", f'{impact["coverage_days"]:.1f} days')
c4.metric("Financial exposure", money(impact["total_exposure"]))

if impact["has_shortage"]:
    st.error(md(f'Projected shortage on {impact["shortage_date"]}. {impact.get("verdict", "")}'))
else:
    st.success(md(f'A late shipment is not an actual shortage here. {impact.get("verdict", "")}'))

tab_impact, tab_options, tab_graph, tab_evidence, tab_explain, tab_decide = st.tabs(
    ["Impact", "Recovery options", "Impact chain (graph)", "Evidence", "AI explanation", "Decision"]
)

# --- Impact ---------------------------------------------------------------
with tab_impact:
    st.write(f'**Part:** {impact["part_id"]} ({impact["part_name"]})  |  '
             f'**Supplier:** {impact["supplier_id"]} ({impact["supplier_name"]})')
    st.write(f'**Original ETA:** {impact["original_eta"]}  |  **Revised ETA:** {impact["revised_eta"]}  |  '
             f'**Daily consumption:** {impact["daily_consumption"]:.1f} units/day  |  '
             f'**Theoretical shortage date:** {impact["shortage_date"]}')
    st.write(f'**Affected products:** {", ".join(impact["affected_products"])}')

    st.subheader("Production orders at risk")
    if impact["at_risk_prod_orders"]:
        st.dataframe(pd.DataFrame(impact["at_risk_prod_orders"]), hide_index=True, width="stretch")
    else:
        st.write("None.")
    st.subheader("Customer orders at risk")
    if impact["at_risk_cust_orders"]:
        st.dataframe(pd.DataFrame(impact["at_risk_cust_orders"]), hide_index=True, width="stretch")
    else:
        st.write("None.")

# --- Options --------------------------------------------------------------
with tab_options:
    st.write(md(f'Cost of doing nothing: **{money(planning["doing_nothing_cost"])}**  |  '
                f'Recommended: **{planning["recommended_option_id"]}**'))
    for o in planning["options"]:
        rank = f'#{o["rank"]}' if o["rank"] > 0 else "unranked"
        star = " (recommended)" if o["option_id"] == planning["recommended_option_id"] else ""
        with st.expander(md(f'{rank}  {o["option_id"]} - {o["title"]}{star}  |  '
                            f'score {o["score"]:.1f}  |  cost {money(o["cost"])}  |  {o["status"]}'),
                         expanded=(o["rank"] == 1)):
            st.write(md(o["description"]))
            st.write(md(f'**Feasibility:** {o["feasibility_note"]}'))
            st.write(md(f'**Cost basis:** {o["cost_note"]}'))
            if o["recommendation_reason"]:
                st.write(md(f'**Why this rank:** {o["recommendation_reason"]}'))

# --- Graph ----------------------------------------------------------------
with tab_graph:
    chain, spare = graph.get("chain") or {}, graph.get("spare_stock") or {}
    graph_err = graph.get("error") or chain.get("error") or spare.get("error")
    if graph_err or not chain:
        st.warning("Graph data unavailable (is the Neo4j instance running?). "
                   "The rest of the analysis does not depend on it.")
        st.caption(str(graph_err or graph.get("chain_text", ""))[:300])
    else:
        st.code(chain["chain_text"], language=None)
        st.code(spare["spare_text"], language=None)

# --- Evidence -------------------------------------------------------------
with tab_evidence:
    st.write("Documents retrieved for the explanation:")
    for s in docs.get("sources_used", []):
        st.write(f"- {s}")
    if docs.get("error"):
        st.warning(docs["error"])
    with st.expander("Retrieved text"):
        st.code(docs.get("combined_context", ""), language=None)

# --- Explanation ----------------------------------------------------------
with tab_explain:
    explanation = analysis["explanation"]
    if explanation.startswith("[AI explanation unavailable"):
        st.warning("The AI service was unavailable; showing the fallback summary. "
                   "Re-run the analysis to retry.")
    st.write(md(explanation))

# --- Decision -------------------------------------------------------------
with tab_decide:
    feasible = [o for o in planning["options"] if o["status"] == "feasible"]
    ids = [o["option_id"] for o in feasible]
    default_idx = ids.index(planning["recommended_option_id"]) if planning["recommended_option_id"] in ids else 0

    result = st.session_state.get("decision_result")
    if result:
        verb = "APPROVED" if result["approved"] else "REJECTED"
        st.success(f'Decision {result["decision_id"]} saved: {verb} {result["chosen_option_id"]}.')
    else:
        st.write("Nothing is executed. Your decision is recorded in the audit log only.")
        with st.form("decision_form"):
            reviewer = st.text_input("Your name")
            chosen = st.selectbox("Option", ids, index=default_idx,
                                  format_func=lambda i: next(f'{i} - {o["title"]}' for o in feasible if o["option_id"] == i))
            rationale = st.text_area("Rationale (required)")
            col_a, col_r = st.columns(2)
            approve = col_a.form_submit_button("Approve", type="primary", width="stretch")
            reject = col_r.form_submit_button("Reject", width="stretch")

        if approve or reject:
            if not reviewer.strip() or not rationale.strip():
                st.error("Name and rationale are required.")
            else:
                data, err = api("POST", f"/events/{event_id}/decision", json={
                    "approved": bool(approve), "reviewer_name": reviewer,
                    "rationale": rationale, "chosen_option_id": chosen})
                if err:
                    st.error(err)
                else:
                    st.session_state["decision_result"] = data
                    st.rerun()

    st.subheader("Audit log")
    log, err = api("GET", "/decisions", params={"event_id": event_id})
    if err:
        st.error(err)
    elif log:
        st.dataframe(pd.DataFrame(log), hide_index=True, width="stretch")
    else:
        st.write("No decisions recorded yet.")
