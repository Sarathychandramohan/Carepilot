from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer


# ============================================================
# Configuration
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

CHROMA_DIR = BASE_DIR / "chroma_db"
COLLECTION_NAME = "carepilot_medical_knowledge"

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

TOP_K = 5
LLM_CONTEXT_K = 3

# Chroma is returning L2 distances for this collection.
# We convert the distance into a bounded similarity score:
#
# similarity = 1 / (1 + distance)
#
# This is used only as an application-level score.
# Retrieval ranking itself remains based on Chroma distance.
SIMILARITY_THRESHOLD = 0.35


# ============================================================
# Load embedding model
# ============================================================

print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")

embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)

embedding_dimension = embedding_model.get_sentence_embedding_dimension()

if embedding_dimension != 384:
    raise RuntimeError(
        f"Unexpected embedding dimension: {embedding_dimension}. "
        "Expected 384."
    )


# ============================================================
# Connect to ChromaDB
# ============================================================

client = chromadb.PersistentClient(path=str(CHROMA_DIR))

collection = client.get_collection(COLLECTION_NAME)

actual_count = collection.count()

if actual_count != 219:
    raise RuntimeError(
        f"Unexpected Chroma collection size: {actual_count}. "
        "Expected 219."
    )


# ============================================================
# Query embedding
# ============================================================

def embed_query(query: str) -> list[float]:
    """
    Generate a query embedding using the SAME model and
    normalization configuration used during corpus ingestion.
    """

    if not isinstance(query, str):
        raise TypeError("query must be a string")

    query = query.strip()

    if not query:
        raise ValueError("query cannot be empty")

    embedding = embedding_model.encode(
        query,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    if embedding.shape != (384,):
        raise RuntimeError(
            f"Unexpected query embedding shape: {embedding.shape}"
        )

    return embedding.tolist()


# ============================================================
# Distance → application similarity
# ============================================================

def distance_to_similarity(distance: float) -> float:
    """
    Convert Chroma distance to a bounded application score.

    Lower Chroma distance = more similar.

    This conversion is NOT used to rank results.
    """

    return 1.0 / (1.0 + float(distance))


# ============================================================
# Retrieval
# ============================================================

def retrieve(
    query: str,
    top_k: int = TOP_K,
    context_k: int = LLM_CONTEXT_K,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
) -> dict[str, Any]:
    """
    Retrieve medical knowledge chunks for a query.

    Pipeline:

        query
          ↓
        BGE embedding
          ↓
        Chroma top-k
          ↓
        distance → similarity
          ↓
        threshold filtering
          ↓
        top context chunks
    """

    if top_k < 1:
        raise ValueError("top_k must be >= 1")

    if context_k < 1:
        raise ValueError("context_k must be >= 1")

    if context_k > top_k:
        raise ValueError("context_k cannot be greater than top_k")

    query_embedding = embed_query(query)

    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

    ids = result["ids"][0]
    documents = result["documents"][0]
    metadatas = result["metadatas"][0]
    distances = result["distances"][0]

    candidates = []

    for rank, (
        chunk_id,
        document,
        metadata,
        distance,
    ) in enumerate(
        zip(
            ids,
            documents,
            metadatas,
            distances,
        ),
        start=1,
    ):
        similarity = distance_to_similarity(distance)

        candidates.append(
            {
                "rank": rank,
                "chunk_id": chunk_id,
                "document_id": metadata.get("document_id"),
                "title": metadata.get("title"),
                "source": metadata.get("source"),
                "source_url": metadata.get("source_url"),
                "section_heading": metadata.get("section_heading"),
                "document_type": metadata.get("document_type"),
                "chunk_index": metadata.get("chunk_index"),
                "distance": float(distance),
                "similarity": float(similarity),
                "text": document,
            }
        )

    # --------------------------------------------------------
    # Threshold filtering
    # --------------------------------------------------------

    valid_chunks = [
        item
        for item in candidates
        if item["similarity"] >= similarity_threshold
    ]

    # --------------------------------------------------------
    # Unsupported branch
    # --------------------------------------------------------

    unsupported = len(valid_chunks) == 0

    # --------------------------------------------------------
    # Context passed to LLM
    # --------------------------------------------------------

    context_chunks = valid_chunks[:context_k]

    return {
        "query": query,
        "top_k": top_k,
        "context_k": context_k,
        "similarity_threshold": similarity_threshold,
        "unsupported": unsupported,
        "candidate_count": len(candidates),
        "valid_count": len(valid_chunks),
        "results": candidates,
        "context": context_chunks,
    }


# ============================================================
# CLI test
# ============================================================

if __name__ == "__main__":

    TEST_QUERIES = [
        "What is the A1C test?",
        "What tests are used to diagnose chronic kidney disease?",
        "What is albuminuria?",
        "What is high blood pressure?",
        "What does a hemoglobin test measure?",
    ]

    for query in TEST_QUERIES:

        print("\n" + "=" * 80)
        print(f"QUERY: {query}")
        print("=" * 80)

        result = retrieve(query)

        print(f"Unsupported: {result['unsupported']}")
        print(f"Valid chunks: {result['valid_count']}")
        print()

        for item in result["results"]:

            print(
                f"[Rank {item['rank']}] "
                f"{item['chunk_id']} | "
                f"{item['document_id']} | "
                f"distance={item['distance']:.4f} | "
                f"similarity={item['similarity']:.4f}"
            )

            print(
                f"  Section: {item['section_heading']}"
            )

            print(
                f"  Title: {item['title']}"
            )

            print(
                f"  Text: {item['text'][:180].replace(chr(10), ' ')}..."
            )

        print("\nChunks passed to LLM:")

        for item in result["context"]:
            print(
                f"  {item['chunk_id']} "
                f"({item['document_id']})"
            )