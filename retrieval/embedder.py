"""
retrieval/embedder.py -- Document Embedder (ChromaDB Loader)

Reads all documents from documents.py, splits them into chunks,
converts each chunk to a vector, and saves into ChromaDB.

Think of this as the "generate_data.py" for the RAG system:
  - Run it once to load all documents
  - Run with --reset to wipe and reload from scratch

What is a vector / embedding?
  Text like "penalty clause for delay" cannot be stored in a database directly
  for similarity search. We first convert it to a list of 384 numbers (a vector)
  using a sentence embedding model. Similar sentences produce similar vectors.
  ChromaDB stores these vectors and finds the nearest ones to any query.

Embedding model used:
  all-MiniLM-L6-v2 (from sentence-transformers)
  - Free, runs locally (no API key needed)
  - 384-dimensional vectors
  - Fast: ~1000 sentences per second on CPU
  - Already installed as part of our dependencies

How to run:
  uv run python retrieval/embedder.py           # load all documents
  uv run python retrieval/embedder.py --reset   # wipe and reload
  uv run python retrieval/embedder.py --verify  # check what is stored
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb
from chromadb.utils import embedding_functions

from retrieval.documents import ALL_DOCUMENTS, Document


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

# Where ChromaDB stores its data on disk
# This folder is created automatically if it doesn't exist
CHROMA_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "chroma_db"
)

# The name of our collection inside ChromaDB
# Think of a collection like a table in PostgreSQL
COLLECTION_NAME = "supply_chain_docs"

# The sentence embedding model to use
# This model runs locally -- no API call, no cost
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# How many lines per chunk when splitting documents
# Smaller chunks = more precise retrieval
# Larger chunks = more context per result
CHUNK_SIZE = 15  # lines per chunk
CHUNK_OVERLAP = 3  # lines of overlap between consecutive chunks


# ---------------------------------------------------------------------------
# CHUNKING
# Split a long document into overlapping smaller pieces
# ---------------------------------------------------------------------------

def chunk_document(doc: Document) -> list[dict]:
    """
    Split one document into multiple overlapping text chunks.

    Why overlap?
      If a key sentence falls at the boundary between chunk 1 and chunk 2,
      overlap ensures it appears in at least one chunk fully.

    Returns a list of dicts, each representing one chunk:
      {
        "chunk_id": "CONTRACT-SUP-005_chunk_0",
        "doc_id":   "CONTRACT-SUP-005",
        "text":     "SUPPLIER CONTRACT -- Apex Hydraulics...",
        "metadata": { "category": "contract", "supplier_id": "SUP-005", ... }
      }
    """
    lines = doc.content.split("\n")
    chunks = []
    chunk_index = 0

    start = 0
    while start < len(lines):
        end = min(start + CHUNK_SIZE, len(lines))
        chunk_text = "\n".join(lines[start:end]).strip()

        if chunk_text:  # skip empty chunks
            chunks.append({
                "chunk_id": f"{doc.doc_id}_chunk_{chunk_index}",
                "doc_id": doc.doc_id,
                "text": chunk_text,
                "metadata": {
                    "doc_id": doc.doc_id,
                    "title": doc.title,
                    "category": doc.category,
                    "supplier_id": doc.supplier_id or "none",
                    "chunk_index": chunk_index
                }
            })
            chunk_index += 1

        # Move forward by (CHUNK_SIZE - CHUNK_OVERLAP) to create overlap
        start += max(1, CHUNK_SIZE - CHUNK_OVERLAP)

    return chunks


# ---------------------------------------------------------------------------
# LOAD ALL DOCUMENTS INTO CHROMADB
# ---------------------------------------------------------------------------

def load_documents(reset: bool = False):
    """
    Load all documents from documents.py into ChromaDB.

    Args:
        reset: If True, delete existing collection first (full reload)
    """
    print("\n" + "=" * 60)
    print("  ChromaDB Document Embedder")
    print("=" * 60)
    print(f"  DB path     : {CHROMA_DB_PATH}")
    print(f"  Collection  : {COLLECTION_NAME}")
    print(f"  Model       : {EMBEDDING_MODEL}")
    print(f"  Documents   : {len(ALL_DOCUMENTS)}")

    # ------------------------------------------------------------------
    # Connect to ChromaDB (persistent -- saves to disk)
    # ------------------------------------------------------------------
    print("\n  Connecting to ChromaDB...")
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

    # ------------------------------------------------------------------
    # Reset if requested
    # ------------------------------------------------------------------
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
            print(f"  [OK] Existing collection '{COLLECTION_NAME}' deleted.")
        except Exception:
            print(f"  [OK] No existing collection to delete.")

    # ------------------------------------------------------------------
    # Set up embedding function
    # This tells ChromaDB which model to use to convert text to vectors
    # SentenceTransformerEmbeddingFunction runs locally -- no API needed
    # ------------------------------------------------------------------
    print(f"  Loading embedding model '{EMBEDDING_MODEL}'...")
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    print(f"  [OK] Embedding model loaded.")

    # ------------------------------------------------------------------
    # Get or create collection
    # ------------------------------------------------------------------
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
        metadata={"description": "SupplyChain Orchestrator document library"}
    )
    print(f"  [OK] Collection ready.")

    # ------------------------------------------------------------------
    # Check if already loaded (skip if not reset)
    # ------------------------------------------------------------------
    existing_count = collection.count()
    if existing_count > 0 and not reset:
        print(f"\n  Collection already has {existing_count} chunks.")
        print(f"  Use --reset to reload. Skipping.")
        return collection

    # ------------------------------------------------------------------
    # Chunk all documents
    # ------------------------------------------------------------------
    print(f"\n  Chunking {len(ALL_DOCUMENTS)} documents...")
    all_chunks = []
    for doc in ALL_DOCUMENTS:
        chunks = chunk_document(doc)
        all_chunks.extend(chunks)
        print(f"    {doc.doc_id:<35} : {len(chunks)} chunks")

    print(f"\n  Total chunks to embed: {len(all_chunks)}")

    # ------------------------------------------------------------------
    # Add all chunks to ChromaDB
    # ChromaDB automatically calls the embedding function on the texts
    # ------------------------------------------------------------------
    print(f"  Embedding and storing chunks (this may take 30-60 seconds)...")

    # ChromaDB add() takes parallel lists: ids, documents, metadatas
    ids       = [c["chunk_id"] for c in all_chunks]
    documents = [c["text"]     for c in all_chunks]
    metadatas = [c["metadata"] for c in all_chunks]

    # Add in one batch -- ChromaDB handles it efficiently
    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas
    )

    final_count = collection.count()
    print(f"  [OK] {final_count} chunks stored in ChromaDB.")

    print("\n" + "=" * 60)
    print(f"  LOAD COMPLETE -- {final_count} chunks indexed")
    print(f"  ChromaDB saved to: {CHROMA_DB_PATH}")
    print("=" * 60 + "\n")

    return collection


# ---------------------------------------------------------------------------
# VERIFY -- show what is stored
# ---------------------------------------------------------------------------

def verify_collection():
    """
    Print a summary of what is currently stored in ChromaDB.
    Use this to confirm the load worked correctly.
    """
    print("\n  Verifying ChromaDB contents...")

    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

    try:
        embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL
        )
        collection = client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=embed_fn
        )
    except Exception:
        print("  [ERROR] Collection not found. Run embedder.py first.")
        return

    count = collection.count()
    print(f"\n  Total chunks in ChromaDB: {count}")

    # Do a quick test query to prove search works
    print("\n  Test query: 'penalty for supplier delay'")
    results = collection.query(
        query_texts=["penalty for supplier delay"],
        n_results=3
    )

    print("  Top 3 results:")
    for i, (doc_text, meta) in enumerate(zip(
        results["documents"][0],
        results["metadatas"][0]
    )):
        print(f"\n  Result {i+1}:")
        print(f"    Source  : {meta['doc_id']} (chunk {meta['chunk_index']})")
        print(f"    Category: {meta['category']}")
        preview = doc_text[:120].replace("\n", " ")
        print(f"    Preview : {preview}...")

    print("\n  [OK] ChromaDB is working correctly.")


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SupplyChain Orchestrator -- ChromaDB Document Embedder"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe existing ChromaDB collection and reload from scratch"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Check what is currently stored in ChromaDB"
    )
    args = parser.parse_args()

    if args.verify:
        verify_collection()
    else:
        load_documents(reset=args.reset)
        verify_collection()
