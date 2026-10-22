"""
agents/workflow.py -- LangGraph Workflow Definition

Connects all agent nodes into a pipeline using LangGraph.
This file only defines the MAP -- the order and connections.
The actual work happens in nodes.py.

Pipeline:
  validate_event
       |
       |--(invalid)--> END
       |
       v
  run_impact
       |
       v
  run_planning
       |
       v
  fetch_graph
       |
       v
  fetch_documents
       |
       v
  generate_explanation
       |
       v
  await_approval
       |
       |--(approved)--> save_decision --> END
       |
       |--(rejected)--> save_decision --> END
       (both paths save to audit log -- rejections are also logged)

Why LangGraph?
  Regular Python would work for a linear pipeline.
  LangGraph adds:
    - State management between nodes (no manual passing of dicts)
    - Easy branching (different paths based on approval outcome)
    - Built-in support for human-in-the-loop patterns
    - Can add memory, retries, and streaming in Stage 7
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import StateGraph, END

from agents.state import AgentState
from agents.nodes import (
    validate_event,
    run_impact,
    run_planning,
    fetch_graph,
    fetch_documents,
    generate_explanation,
    await_approval,
    save_decision_node
)


# ---------------------------------------------------------------------------
# ROUTING FUNCTION
# After validate_event, decide whether to continue or stop
# ---------------------------------------------------------------------------

def route_after_validation(state: dict) -> str:
    """
    After validate_event, check if we should continue.
    If the event is invalid or already resolved, stop here.
    Returns: "continue" or "end"
    """
    if not state.get("event_valid", False):
        return "end"
    return "continue"


# ---------------------------------------------------------------------------
# BUILD THE GRAPH
# ---------------------------------------------------------------------------

def build_workflow():
    """
    Create and compile the LangGraph workflow.

    Returns a compiled LangGraph app that can be invoked with:
        app.invoke({"event_id": "EVT-001"})
    """

    # Create the graph with our state definition
    graph = StateGraph(AgentState)

    # --- Add all nodes (name → function) ---
    graph.add_node("validate_event",        validate_event)
    graph.add_node("run_impact",            run_impact)
    graph.add_node("run_planning",          run_planning)
    graph.add_node("fetch_graph",           fetch_graph)
    graph.add_node("fetch_documents",       fetch_documents)
    graph.add_node("generate_explanation",  generate_explanation)
    graph.add_node("await_approval",        await_approval)
    graph.add_node("save_decision",         save_decision_node)

    # --- Define the entry point ---
    graph.set_entry_point("validate_event")

    # --- Add edges (connections between nodes) ---

    # After validation: either continue or stop
    graph.add_conditional_edges(
        "validate_event",
        route_after_validation,
        {
            "continue": "run_impact",
            "end":      END
        }
    )

    # Linear pipeline from impact through to approval
    graph.add_edge("run_impact",           "run_planning")
    graph.add_edge("run_planning",         "fetch_graph")
    graph.add_edge("fetch_graph",          "fetch_documents")
    graph.add_edge("fetch_documents",      "generate_explanation")
    graph.add_edge("generate_explanation", "await_approval")

    # After approval: always save (both approved and rejected are logged)
    graph.add_edge("await_approval",       "save_decision")
    graph.add_edge("save_decision",        END)

    # --- Compile and return ---
    app = graph.compile()
    return app


# Module-level compiled app (created once, reused)
workflow_app = build_workflow()
