"""
agents/state.py -- Agent State (Working Memory)

Defines what the agent "remembers" as it moves through the workflow.

In LangGraph, state is a TypedDict that gets passed from node to node.
Each node reads what it needs from state and writes its results back.

Think of state as the agent's notepad:
  - Node 1 writes: "event loaded: EVT-001, part PRT-104"
  - Node 2 reads that, runs impact analysis, writes: "PRD-306 at risk, $20,300"
  - Node 3 reads both, runs planning, writes: "OPT-A recommended, score 99.0"
  - ...and so on until the final decision is saved

Why TypedDict?
  TypedDict gives us type hints for every field.
  LangGraph uses these to validate state transitions.
  If a node forgets to set a required field, we catch it early.
"""

from typing import TypedDict, Optional


class AgentState(TypedDict):
    """
    The full state object carried through the agent workflow.
    Every node reads from and writes to this dict.

    Fields are populated progressively:
      After validate_event:      event_id, event_description, part_id, supplier_id
      After run_impact:          impact_result
      After run_planning:        planning_result
      After fetch_graph:         graph_result
      After fetch_documents:     documents_result
      After generate_explanation: explanation

    The human decision is NOT part of this state -- see agents/decision.py.
    """

    # --- Input ---
    event_id: str                          # e.g. "EVT-001" -- set by runner.py

    # --- Set by validate_event node ---
    event_valid: bool                      # False if event not found or already resolved
    event_description: str                 # Short summary of what the event is
    part_id: str                           # e.g. "PRT-104"
    supplier_id: str                       # e.g. "SUP-005"
    delay_days: int                        # e.g. 4

    # --- Set by run_impact node (calls tools/impact_tool.py) ---
    impact_result: Optional[dict]          # Full structured impact analysis result

    # --- Set by run_planning node (calls tools/planning_tool.py) ---
    planning_result: Optional[dict]        # Ranked recovery options

    # --- Set by fetch_graph node (calls tools/graph_tool.py) ---
    graph_result: Optional[dict]           # Impact chain from Neo4j

    # --- Set by fetch_documents node (calls tools/retrieval_tool.py) ---
    documents_result: Optional[dict]       # Relevant contracts, policies, past decisions

    # --- Set by generate_explanation node (calls Gemini) ---
    explanation: str                       # Full plain English explanation from LLM

    # --- Error tracking ---
    error: Optional[str]                   # Set if any node encounters an error
