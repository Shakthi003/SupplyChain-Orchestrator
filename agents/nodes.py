"""
agents/nodes.py -- Agent Workflow Nodes

Each function in this file is one step (node) in the agent workflow.
Nodes are connected together in workflow.py.

Every node:
  - Receives the full AgentState dict
  - Does one specific job
  - Returns a dict with the fields it updated
  - LangGraph merges that return dict back into the state

Node execution order (defined in workflow.py):
  1. validate_event        -- is this event real and open?
  2. run_impact            -- what is the damage?
  3. run_planning          -- what can we do?
  4. fetch_graph           -- show the impact chain
  5. fetch_documents       -- find relevant contracts and policies
  6. generate_explanation  -- Gemini writes the full explanation

(The human approval + audit logging step lives in agents/decision.py.)

Each node prints what it is doing so you can watch the workflow live.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.config import DATABASE_URL, GEMINI_API_KEY, GEMINI_MODEL
from core.models import DisruptionEvent, DisruptionStatus
from tools.impact_tool import run_impact_analysis_tool
from tools.planning_tool import run_recovery_planning_tool
from tools.graph_tool import get_impact_chain_tool, get_spare_stock_tool
from tools.retrieval_tool import get_supporting_documents

from google import genai
from google.genai import types as genai_types

# Worst case wait = attempts x timeout + backoff ~= 66 s. A healthy call takes a few seconds;
# a quick 503 is retried cheaply, a hung connection is cut off after 20 s.
GEMINI_TIMEOUT_MS = 20_000   # per attempt
GEMINI_ATTEMPTS = 3          # including the first try


# ---------------------------------------------------------------------------
# NODE 1: validate_event
# Checks the event exists, is open, and loads basic info into state
# ---------------------------------------------------------------------------

def validate_event(state: dict) -> dict:
    """
    Step 1: Load and validate the disruption event.

    Checks:
      - Event exists in DB
      - Event status is OPEN (not already resolved)
      - Event points to a valid shipment

    Returns updated state fields:
      event_valid, event_description, part_id, supplier_id, delay_days
    """
    print("\n" + "=" * 65)
    print("  AGENT STEP 1: Validating disruption event...")
    print("=" * 65)

    event_id = state["event_id"]

    try:
        db_engine = create_engine(DATABASE_URL)

        with Session(db_engine) as session:
            event = session.get(DisruptionEvent, event_id)

            if not event:
                print(f"  [ERROR] Event {event_id} not found in database.")
                return {
                    "event_valid": False,
                    "error": f"Event {event_id} not found.",
                    "event_description": "",
                    "part_id": "",
                    "supplier_id": "",
                    "delay_days": 0
                }

            if event.status == DisruptionStatus.RESOLVED:
                print(f"  [SKIP] Event {event_id} is already RESOLVED.")
                return {
                    "event_valid": False,
                    "error": f"Event {event_id} is already resolved.",
                    "event_description": event.description,
                    "part_id": "",
                    "supplier_id": "",
                    "delay_days": 0
                }

            # Load the shipment to get part and supplier info
            from core.models import Shipment, PurchaseOrder
            shipment = session.get(Shipment, event.source_entity_id)
            po = session.get(PurchaseOrder, shipment.purchase_order_id)

            print(f"  Event ID  : {event_id}")
            print(f"  Type      : {event.event_type.value}")
            print(f"  Severity  : {event.severity.value}")
            print(f"  Part      : {po.part_id} ({po.part.name})")
            print(f"  Supplier  : {po.supplier_id} ({po.supplier.name})")
            print(f"  Delay     : {shipment.delay_days} days")
            print(f"  [OK] Event validated.")

            return {
                "event_valid":       True,
                "event_description": event.description,
                "part_id":           po.part_id,
                "supplier_id":       po.supplier_id,
                "delay_days":        shipment.delay_days or 0,
                "error":             None
            }

    except Exception as e:
        print(f"  [ERROR] Validation failed: {e}")
        return {
            "event_valid": False,
            "error": str(e),
            "event_description": "",
            "part_id": "",
            "supplier_id": "",
            "delay_days": 0
        }


# ---------------------------------------------------------------------------
# NODE 2: run_impact
# Runs the full impact analysis (Stage 3 engine)
# ---------------------------------------------------------------------------

def run_impact(state: dict) -> dict:
    """
    Step 2: Run the deterministic impact analysis.
    Calls tools/impact_tool.py which wraps core/impact_analysis/engine.py.
    """
    print("\n" + "=" * 65)
    print("  AGENT STEP 2: Running impact analysis...")
    print("=" * 65)

    result = run_impact_analysis_tool(state["event_id"])

    if result.get("error"):
        print(f"  [ERROR] Impact analysis failed: {result['error']}")
        return {"impact_result": result, "error": result["error"]}

    print(f"  Part              : {result['part_id']} ({result['part_name']})")
    print(f"  Supplier          : {result['supplier_id']} ({result['supplier_name']})")
    print(f"  Delay             : {result['delay_days']} days")
    print(f"  Stock available   : {result['total_available']:.0f} units")
    print(f"  Coverage          : {result['coverage_days']:.1f} days")
    print(f"  Has shortage      : {result['has_shortage']}")
    print(f"  At-risk prod orders: {len(result['at_risk_prod_orders'])}")
    print(f"  At-risk cust orders: {len(result['at_risk_cust_orders'])}")
    print(f"  Financial exposure : ${result['total_exposure']:,.2f}")
    print(f"  [OK] Impact analysis complete.")

    return {"impact_result": result, "error": None}


# ---------------------------------------------------------------------------
# NODE 3: run_planning
# Runs the recovery planner (Stage 5)
# ---------------------------------------------------------------------------

def run_planning(state: dict) -> dict:
    """
    Step 3: Run the recovery planning pipeline.
    Calls tools/planning_tool.py which wraps core/optimization/planner.py.
    """
    print("\n" + "=" * 65)
    print("  AGENT STEP 3: Running recovery planning...")
    print("=" * 65)

    result = run_recovery_planning_tool(state["event_id"])

    if result.get("error"):
        print(f"  [ERROR] Planning failed: {result['error']}")
        return {"planning_result": result, "error": result["error"]}

    print(f"  Options generated : {result['total_options']}")
    print(f"  Feasible options  : {result['feasible_options']}")
    print(f"  Cost of inaction  : ${result['doing_nothing_cost']:,.2f}")
    print(f"  Recommended       : {result['recommended_option_id']}")
    print()

    for opt in result["options"]:
        status_tag = "[FEASIBLE]  " if opt["status"] == "feasible" else "[INFEASIBLE]"
        rank_tag = f"Rank #{opt['rank']}" if opt["rank"] > 0 else "Unranked"
        print(f"  {status_tag} {rank_tag} | {opt['option_id']} | {opt['title']}")
        print(f"             Score: {opt['score']:.1f}  Cost: ${opt['cost']:,.2f}")

    print(f"\n  [OK] Recovery planning complete.")

    return {"planning_result": result, "error": None}


# ---------------------------------------------------------------------------
# NODE 4: fetch_graph
# Queries Neo4j for the impact chain
# ---------------------------------------------------------------------------

def fetch_graph(state: dict) -> dict:
    """
    Step 4: Get the visual impact chain from Neo4j.
    Shows: Supplier -> Part -> Production Order -> Customer Order
    """
    print("\n" + "=" * 65)
    print("  AGENT STEP 4: Fetching impact chain from graph...")
    print("=" * 65)

    supplier_id = state.get("supplier_id", "")
    part_id     = state.get("part_id", "")

    if not supplier_id:
        print("  [SKIP] No supplier ID in state. Skipping graph query.")
        return {"graph_result": {"chain_text": "Graph query skipped.", "error": None}}

    try:
        chain_result = get_impact_chain_tool(supplier_id, part_id)
        stock_result = get_spare_stock_tool(part_id)

        print(chain_result["chain_text"])
        print()
        print(stock_result["spare_text"])
        print(f"\n  [OK] Graph queries complete.")

        return {
            "graph_result": {
                "chain": chain_result,
                "spare_stock": stock_result,
                "error": None
            }
        }

    except Exception as e:
        print(f"  [WARN] Graph query failed (Neo4j may not be running): {e}")
        print(f"  Continuing without graph data...")
        return {
            "graph_result": {
                "chain_text": f"Graph unavailable: {str(e)}",
                "error": str(e)
            }
        }


# ---------------------------------------------------------------------------
# NODE 5: fetch_documents
# Searches ChromaDB for relevant contracts, policies, past decisions
# ---------------------------------------------------------------------------

def fetch_documents(state: dict) -> dict:
    """
    Step 5: Retrieve supporting documents from ChromaDB (RAG).
    Finds: penalty clauses, relevant policies, similar past decisions.
    """
    print("\n" + "=" * 65)
    print("  AGENT STEP 5: Fetching supporting documents (RAG)...")
    print("=" * 65)

    supplier_id = state.get("supplier_id", "")
    delay_days  = state.get("delay_days", 0)
    part_id     = state.get("part_id", "")

    situation = (
        f"{supplier_id} delayed {part_id} by {delay_days} days. "
        f"Need to assess penalty clauses, policies, and past decisions."
    )

    result = get_supporting_documents(
        supplier_id=supplier_id,
        delay_days=delay_days,
        situation_summary=situation
    )

    if result.get("error"):
        print(f"  [WARN] Document retrieval had issues: {result['error']}")
    else:
        print(f"  Sources retrieved: {result['sources_used']}")
        print(f"  [OK] Documents retrieved.")

    return {"documents_result": result, "error": None}


# ---------------------------------------------------------------------------
# NODE 6: generate_explanation
# Sends everything to Gemini to write the plain English explanation
# ---------------------------------------------------------------------------

def generate_explanation(state: dict) -> dict:
    """
    Step 6: Use Gemini to generate a plain English explanation.

    Gemini receives:
      - The impact analysis numbers
      - The ranked recovery options
      - The relevant contract clauses and policies
      - Instructions to explain clearly and cite sources

    Gemini returns:
      - A full narrative explanation the human reviewer can read
    """
    print("\n" + "=" * 65)
    print("  AGENT STEP 6: Generating AI explanation (Gemini)...")
    print("=" * 65)

    impact   = state.get("impact_result", {})
    planning = state.get("planning_result", {})
    docs     = state.get("documents_result", {})
    event_id = state.get("event_id", "")

    # Build the prompt
    # The prompt has 3 sections:
    #   1. The numbers (from our deterministic engines)
    #   2. The documents (from ChromaDB)
    #   3. Instructions for what to write

    at_risk_prod = impact.get("at_risk_prod_orders", [])
    at_risk_cust = impact.get("at_risk_cust_orders", [])
    options      = planning.get("options", [])
    recommended  = planning.get("recommended_option_id", "N/A")

    # Format options for the prompt
    options_text = ""
    for opt in options:
        tag = " <-- RECOMMENDED" if opt["option_id"] == recommended else ""
        options_text += (
            f"\n  {opt['option_id']} | {opt['title']}{tag}"
            f"\n    Rank: #{opt['rank']}  Score: {opt['score']:.1f}/100  Cost: ${opt['cost']:,.2f}"
            f"\n    {opt['description'][:200]}"
            f"\n    Feasibility: {opt['feasibility_note'][:150]}"
        )

    # Format at-risk orders
    prod_risk_text = ""
    for p in at_risk_prod:
        prod_risk_text += f"\n  - {p['order_id']} ({p['product_name']}): needs {p['units_needed']:.0f} units, starts {p['planned_start']}"

    cust_risk_text = ""
    for c in at_risk_cust:
        cust_risk_text += f"\n  - {c['order_id']} ({c['customer']}): ${c['value']:,.0f} at risk, delivery {c['delivery_date']}"

    if not prod_risk_text:
        prod_risk_text = "\n  None -- near-term production orders are covered by current stock."
    if not cust_risk_text:
        cust_risk_text = "\n  None -- no customer orders are immediately at risk."

    prompt = f"""You are a Supply Chain Risk Analyst AI assistant.
A disruption event has been detected and fully analyzed by deterministic engines.
Your job is to write a clear, professional explanation for the human reviewer.

IMPORTANT RULES:
- Do NOT invent or calculate any numbers. Use ONLY the numbers provided below.
- Cite the source documents when referencing contracts or policies.
- Be concise but complete. Maximum 400 words.
- Use plain English. Avoid jargon.
- End with a clear recommendation statement.

=== DISRUPTION EVENT ===
Event ID     : {event_id}
Part affected: {impact.get('part_id', 'N/A')} ({impact.get('part_name', 'N/A')})
Supplier     : {impact.get('supplier_id', 'N/A')} ({impact.get('supplier_name', 'N/A')})
Delay        : {impact.get('delay_days', 0)} days
Original ETA : {impact.get('original_eta', 'N/A')}
Revised ETA  : {impact.get('revised_eta', 'N/A')}

=== INVENTORY ANALYSIS ===
Total available stock : {impact.get('total_available', 0):.0f} units
Daily consumption rate: {impact.get('daily_consumption', 0):.1f} units/day
Stock coverage        : {impact.get('coverage_days', 0):.1f} days
Theoretical shortage date: {impact.get('shortage_date', 'N/A')}
Actual shortage risk  : {'YES' if impact.get('has_shortage') else 'NO -- shipment arrives before stock runs out'}
Inventory verdict     : {impact.get('verdict', 'N/A')}

=== PRODUCTION ORDERS AT RISK ===
{prod_risk_text}

=== CUSTOMER ORDERS AT RISK ===
{cust_risk_text}

Total financial exposure: ${impact.get('total_exposure', 0):,.2f}

=== RECOVERY OPTIONS (ranked) ===
{options_text}

Cost of doing nothing: ${planning.get('doing_nothing_cost', 0):,.2f}

=== SUPPORTING DOCUMENTS (cite these) ===
{docs.get('combined_context', 'No documents retrieved.')[:1500]}

=== YOUR TASK ===
Write a professional supply chain risk briefing for the human reviewer.
Structure it as:
1. Situation Summary (2-3 sentences: what happened, what is at risk)
2. Inventory Position (1-2 sentences: how long stock lasts, shortage risk)
3. Contract and Policy Implications (cite relevant clauses from the documents above)
4. Recovery Options Summary (briefly explain the top 2 ranked options)
5. Recommendation (clear statement of what you recommend and why)
"""

    try:
        # Bounded wait: never let a slow/overloaded Gemini hang the whole analysis.
        # Each attempt times out after GEMINI_TIMEOUT_MS; 503/429/5xx are retried.
        client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=genai_types.HttpOptions(
                timeout=GEMINI_TIMEOUT_MS,
                retry_options=genai_types.HttpRetryOptions(
                    attempts=GEMINI_ATTEMPTS, initial_delay=2.0, max_delay=8.0
                ),
            ),
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        explanation = response.text
        print(f"  [OK] Explanation generated ({len(explanation)} characters).")
        return {"explanation": explanation, "error": None}

    except Exception as e:
        fallback = (
            f"[AI explanation unavailable: {str(e)}]\n\n"
            f"MANUAL SUMMARY:\n"
            f"Event {event_id}: {impact.get('supplier_name','?')} delayed {impact.get('part_name','?')} "
            f"by {impact.get('delay_days',0)} days. "
            f"Stock covers {impact.get('coverage_days',0):.1f} days. "
            f"Financial exposure: ${impact.get('total_exposure',0):,.2f}. "
            f"Recommended action: {recommended}."
        )
        print(f"  [WARN] Gemini call failed: {e}")
        print(f"  Using fallback summary.")
        return {"explanation": fallback, "error": None}
