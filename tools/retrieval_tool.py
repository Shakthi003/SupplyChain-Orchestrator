"""
tools/retrieval_tool.py -- RAG Retrieval Tool (Wrapper for ChromaDB)

Wraps retrieval/retriever.py for use by the AI agent.
Takes a plain English question, returns relevant document text.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.retriever import (
    search,
    get_penalty_clause,
    get_relevant_policies,
    get_similar_past_decisions,
    format_results_for_llm
)


def get_supporting_documents(
    supplier_id: str,
    delay_days: int,
    situation_summary: str
) -> dict:
    """
    Retrieve all supporting documents relevant to a disruption event.

    This is the main function the agent calls.
    It runs 4 targeted searches and combines the results.

    Args:
        supplier_id:       The delayed supplier (e.g. "SUP-005")
        delay_days:        How many days delayed (e.g. 4)
        situation_summary: One-line description of the situation

    Returns:
        {
          "penalty_clause":    "Delay 4-7 days: 5% of PO value...",
          "relevant_policies": "Air freight requires 5-day minimum...",
          "past_decisions":    "In Aug 2023 a similar delay was resolved by...",
          "combined_context":  (all of the above joined for the LLM prompt),
          "sources_used":      ["CONTRACT-SUP-005", "POLICY-LOGISTICS-001", ...],
          "error":             None
        }
    """
    try:
        all_results = []

        # Search 1: Penalty clause for this supplier and delay
        penalty_results = get_penalty_clause(supplier_id, delay_days)
        penalty_text = format_results_for_llm(penalty_results)
        all_results.extend(penalty_results)

        # Search 2: Relevant internal policies for this situation
        policy_results = get_relevant_policies(situation_summary)
        policy_text = format_results_for_llm(policy_results)
        all_results.extend(policy_results)

        # Search 3: Similar past decisions
        past_results = get_similar_past_decisions(
            f"supplier delay {delay_days} days recovery decision"
        )
        past_text = format_results_for_llm(past_results)
        all_results.extend(past_results)

        # Search 4: General context for this supplier
        general_results = search(
            query=f"{supplier_id} supplier performance reliability history",
            top_k=2,
            supplier_filter=supplier_id
        )
        general_text = format_results_for_llm(general_results)
        all_results.extend(general_results)

        # Combine all into one context block for the LLM
        combined_context = "\n\n".join([
            "=== PENALTY CLAUSES ===\n" + penalty_text,
            "=== RELEVANT POLICIES ===\n" + policy_text,
            "=== SIMILAR PAST DECISIONS ===\n" + past_text,
            "=== SUPPLIER BACKGROUND ===\n" + general_text,
        ])

        # Collect unique source doc IDs
        sources_used = list({r["doc_id"] for r in all_results})

        return {
            "penalty_clause":    penalty_text,
            "relevant_policies": policy_text,
            "past_decisions":    past_text,
            "supplier_background": general_text,
            "combined_context":  combined_context,
            "sources_used":      sources_used,
            "error":             None
        }

    except Exception as e:
        return {
            "penalty_clause":    "",
            "relevant_policies": "",
            "past_decisions":    "",
            "supplier_background": "",
            "combined_context":  f"Document retrieval failed: {str(e)}",
            "sources_used":      [],
            "error":             str(e)
        }


if __name__ == "__main__":
    result = get_supporting_documents(
        supplier_id="SUP-005",
        delay_days=4,
        situation_summary="SUP-005 delayed PRT-104 hydraulic valve by 4 days"
    )
    print("\n=== PENALTY CLAUSE ===")
    print(result["penalty_clause"][:400])
    print("\n=== POLICIES ===")
    print(result["relevant_policies"][:400])
    print("\n=== PAST DECISIONS ===")
    print(result["past_decisions"][:400])
    print(f"\nSources used: {result['sources_used']}")
