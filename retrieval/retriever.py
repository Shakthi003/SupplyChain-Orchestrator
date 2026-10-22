"""
retrieval/retriever.py -- ChromaDB Search Interface

Given a plain English question, searches ChromaDB and returns
the most relevant document chunks.

This is the "read" side of the RAG system.
  embedder.py = write side (loads documents)
  retriever.py = read side (searches documents)

How similarity search works:
  1. Your question is converted to a vector (384 numbers)
  2. ChromaDB compares that vector to all stored chunk vectors
  3. The chunks with the most similar vectors are returned
  4. "Similar" means: semantically related, not just keyword match

Example:
  Query: "Can we use air freight for a 4-day delay?"
  Returns chunks about: air freight policy, expedite criteria, cost thresholds
  Even though the query didn't say "POL-LOG-001" or "expediting policy"

The agent uses this to add evidence to its explanations:
  "Per the Air Freight Policy, expediting requires a delay of 5+ days.
   The current delay is 4 days, so air freight is NOT recommended."
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb
from chromadb.utils import embedding_functions


# ---------------------------------------------------------------------------
# CONFIGURATION -- must match embedder.py
# ---------------------------------------------------------------------------

CHROMA_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "chroma_db"
)

COLLECTION_NAME = "supply_chain_docs"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# How many chunks to return per query (top-k)
DEFAULT_TOP_K = 3

# Relevance threshold: distance below this = relevant
# ChromaDB uses cosine distance: 0.0 = identical, 2.0 = completely different
# Chunks with distance > threshold are filtered out as not relevant enough
MAX_DISTANCE = 1.2


# ---------------------------------------------------------------------------
# MODULE-LEVEL CLIENT (lazy loaded on first use)
# We keep one client open rather than reconnecting on every query
# ---------------------------------------------------------------------------

_client = None
_collection = None


def _get_collection():
    """
    Get or create the ChromaDB collection connection.
    Lazy-loaded: only connects on first call.
    """
    global _client, _collection

    if _collection is not None:
        return _collection

    _client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )

    try:
        _collection = _client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=embed_fn
        )
    except Exception:
        raise RuntimeError(
            f"ChromaDB collection '{COLLECTION_NAME}' not found. "
            f"Run: uv run python retrieval/embedder.py"
        )

    return _collection


# ---------------------------------------------------------------------------
# MAIN SEARCH FUNCTION
# ---------------------------------------------------------------------------

def search(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    category_filter: str = None,
    supplier_filter: str = None
) -> list[dict]:
    """
    Search ChromaDB for document chunks relevant to the query.

    Args:
        query:           Plain English question (e.g. "penalty for SUP-005 delay")
        top_k:           How many results to return (default 3)
        category_filter: Only search within this category
                         ("contract", "policy", "past_decision", "runbook")
        supplier_filter: Only search documents related to this supplier
                         (e.g. "SUP-005")

    Returns:
        List of result dicts, each containing:
          {
            "chunk_id":   "CONTRACT-SUP-005_chunk_1",
            "doc_id":     "CONTRACT-SUP-005",
            "title":      "Supplier Contract -- Apex Hydraulics Ltd",
            "category":   "contract",
            "supplier_id":"SUP-005",
            "text":       "PENALTY CLAUSES: Delay 4-7 days: 5%...",
            "distance":   0.34   (lower = more relevant)
          }
    """
    collection = _get_collection()

    # Build optional metadata filter
    where_clause = None
    if category_filter and supplier_filter:
        where_clause = {
            "$and": [
                {"category": {"$eq": category_filter}},
                {"supplier_id": {"$eq": supplier_filter}}
            ]
        }
    elif category_filter:
        where_clause = {"category": {"$eq": category_filter}}
    elif supplier_filter:
        where_clause = {"supplier_id": {"$eq": supplier_filter}}

    # Run the query
    query_params = {
        "query_texts": [query],
        "n_results": top_k,
        "include": ["documents", "metadatas", "distances"]
    }
    if where_clause:
        query_params["where"] = where_clause

    results = collection.query(**query_params)

    # Parse results into clean dicts
    output = []
    for text, meta, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0]
    ):
        # Filter out results that are not relevant enough
        if distance > MAX_DISTANCE:
            continue

        output.append({
            "chunk_id":    meta.get("chunk_id", ""),
            "doc_id":      meta.get("doc_id", ""),
            "title":       meta.get("title", ""),
            "category":    meta.get("category", ""),
            "supplier_id": meta.get("supplier_id", "none"),
            "text":        text,
            "distance":    round(distance, 4)
        })

    return output


# ---------------------------------------------------------------------------
# CONVENIENCE FUNCTIONS
# Pre-built queries for the most common agent needs
# ---------------------------------------------------------------------------

def get_supplier_contract(supplier_id: str) -> list[dict]:
    """
    Retrieve the most relevant chunks from a supplier's contract.
    Used when the agent needs to cite contract terms.
    """
    return search(
        query=f"supplier contract terms penalties lead time {supplier_id}",
        top_k=3,
        supplier_filter=supplier_id,
        category_filter="contract"
    )


def get_penalty_clause(supplier_id: str, delay_days: int) -> list[dict]:
    """
    Find the penalty clause that applies to a specific delay duration.
    """
    return search(
        query=f"penalty clause delay {delay_days} days supplier {supplier_id}",
        top_k=3,
        supplier_filter=supplier_id
    )


def get_relevant_policies(situation: str) -> list[dict]:
    """
    Find internal policies relevant to a given situation.
    """
    return search(
        query=situation,
        top_k=3,
        category_filter="policy"
    )


def get_similar_past_decisions(situation: str) -> list[dict]:
    """
    Find past decisions that are similar to the current situation.
    Used to show "we handled something similar before."
    """
    return search(
        query=situation,
        top_k=2,
        category_filter="past_decision"
    )


def get_runbook_steps(disruption_type: str) -> list[dict]:
    """
    Get the response runbook steps for a disruption type.
    """
    return search(
        query=f"{disruption_type} response procedure steps",
        top_k=3,
        category_filter="runbook"
    )


def format_results_for_llm(results: list[dict]) -> str:
    """
    Format search results into a clean string for the LLM prompt.

    The LLM needs evidence as plain text, not as a Python dict.
    This function formats the results into readable paragraphs.

    Example output:
      [SOURCE: CONTRACT-SUP-005 | Supplier Contract -- Apex Hydraulics Ltd]
      Delay 4-7 days: 5% of purchase order value deducted from invoice.
      Buyer may request partial shipment of available stock.

      [SOURCE: POLICY-LOGISTICS-001 | Air Freight and Expediting Policy]
      Delay must be confirmed 5 or more days beyond original ETA.
      ...
    """
    if not results:
        return "No relevant documents found."

    formatted = []
    for r in results:
        header = f"[SOURCE: {r['doc_id']} | {r['title']}]"
        formatted.append(f"{header}\n{r['text']}")

    return "\n\n".join(formatted)


# ---------------------------------------------------------------------------
# QUICK TEST (run this file directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\nRetriever Test")
    print("=" * 50)

    test_queries = [
        ("Penalty for SUP-005 delay of 4 days",     None,          "SUP-005"),
        ("Can we use air freight for a 4-day delay", "policy",     None),
        ("Past decisions for similar supplier delays", "past_decision", None),
        ("Emergency sourcing approval thresholds",   "policy",     None),
    ]

    for query, cat, sup in test_queries:
        print(f"\nQuery: '{query}'")
        if cat: print(f"Filter: category={cat}")
        if sup: print(f"Filter: supplier={sup}")
        print("-" * 40)

        results = search(query, top_k=2, category_filter=cat, supplier_filter=sup)

        if not results:
            print("  No results found.")
        else:
            for r in results:
                print(f"  [{r['doc_id']}] distance={r['distance']}")
                print(f"  {r['text'][:150].replace(chr(10), ' ')}...")
                print()
