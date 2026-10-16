import json
import shutil
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer


BASE_DIR = Path(__file__).resolve().parent

MANIFEST_PATH = BASE_DIR / "manifest" / "corpus_manifest.json"
CLEANED_DIR = BASE_DIR / "cleaned"
CHUNKS_DIR = BASE_DIR / "chunks" / "full"
CHROMA_DIR = BASE_DIR / "chroma_db"

TOKENIZER_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

CHUNK_SIZE = 400
OVERLAP = 60
STRIDE = CHUNK_SIZE - OVERLAP
DATE_ADDED = "2026-09-18"

COLLECTION_NAME = "carepilot_medical_knowledge"


def load_manifest():
    return json.loads(
        MANIFEST_PATH.read_text(encoding="utf-8-sig")
    )


def split_into_sections(text):
    lines = text.splitlines()

    sections = []
    current_heading = None
    current_lines = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("#"):
            if current_lines:
                content = "\n".join(current_lines).strip()

                if content:
                    sections.append(
                        {
                            "section_heading": current_heading,
                            "text": content,
                        }
                    )

            if stripped.startswith("### "):
                current_heading = stripped[4:].strip()
            elif stripped.startswith("## "):
                current_heading = stripped[3:].strip()
            elif stripped.startswith("# "):
                current_heading = stripped[2:].strip()
            else:
                current_heading = None

            current_lines = []

        else:
            current_lines.append(line)

    if current_lines:
        content = "\n".join(current_lines).strip()

        if content:
            sections.append(
                {
                    "section_heading": current_heading,
                    "text": content,
                }
            )

    return sections


def token_windows(text, tokenizer):
    token_ids = tokenizer.encode(
        text,
        add_special_tokens=False,
    )

    if len(token_ids) <= CHUNK_SIZE:
        return [token_ids]

    windows = []
    start = 0

    while start < len(token_ids):
        end = min(
            start + CHUNK_SIZE,
            len(token_ids),
        )

        windows.append(token_ids[start:end])

        if end >= len(token_ids):
            break

        start += STRIDE

    return windows


def decode_tokens(token_ids, tokenizer):
    return tokenizer.decode(
        token_ids,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=True,
    ).strip()


def build_document_chunks(document, tokenizer):
    document_id = document["document_id"]

    cleaned_path = CLEANED_DIR / f"{document_id}.txt"

    if not cleaned_path.exists():
        raise FileNotFoundError(
            f"Missing cleaned document: {cleaned_path}"
        )

    text = cleaned_path.read_text(
        encoding="utf-8"
    )

    sections = split_into_sections(text)

    chunks = []
    chunk_index = 0

    for section in sections:
        section_heading = section["section_heading"]

        if not section_heading:
            raise ValueError(
                f"{document_id}: section without heading found"
            )

        windows = token_windows(
            section["text"],
            tokenizer,
        )

        for window in windows:
            body_text = decode_tokens(
                window,
                tokenizer,
            )

            chunk_text = (
                f"{section_heading}\n\n"
                f"{body_text}"
            )

            chunk_id = (
                f"{document_id}_{chunk_index:03d}"
            )

            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "title": document["title"],
                    "source": document["source"],
                    "source_url": document["source_url"],
                    "document_type": document["document_type"],
                    "section_heading": section_heading,
                    "date_added": DATE_ADDED,
                    "chunk_index": chunk_index,
                    "text": chunk_text,
                    "token_count": len(window),
                }
            )

            chunk_index += 1

    return chunks


def validate_chunks(chunks, document_id):
    expected_ids = [
        f"{document_id}_{i:03d}"
        for i in range(len(chunks))
    ]

    actual_ids = [
        chunk["chunk_id"]
        for chunk in chunks
    ]

    if actual_ids != expected_ids:
        raise ValueError(
            f"{document_id}: chunk IDs are not sequential"
        )

    for chunk in chunks:
        if chunk["token_count"] > CHUNK_SIZE:
            raise ValueError(
                f'{chunk["chunk_id"]}: '
                f'{chunk["token_count"]} > {CHUNK_SIZE}'
            )

        if not chunk["text"].startswith(
            chunk["section_heading"]
        ):
            raise ValueError(
                f'{chunk["chunk_id"]}: '
                f'heading missing from chunk text'
            )


def main():
    manifest = load_manifest()

    documents = manifest["documents"]

    if len(documents) != 18:
        raise ValueError(
            f"Expected 18 documents, found {len(documents)}"
        )

    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(
        TOKENIZER_NAME
    )

    print("Building full chunk corpus...")
    print()

    all_chunks = []

    CHUNKS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for document in documents:
        document_id = document["document_id"]

        chunks = build_document_chunks(
            document,
            tokenizer,
        )

        validate_chunks(
            chunks,
            document_id,
        )

        output_path = (
            CHUNKS_DIR
            / f"{document_id}.json"
        )

        output_path.write_text(
            json.dumps(
                chunks,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        all_chunks.extend(chunks)

        token_counts = [
            chunk["token_count"]
            for chunk in chunks
        ]

        print(
            f"CHUNKS: {document_id} | "
            f"{len(chunks)} chunks | "
            f"min={min(token_counts)} | "
            f"max={max(token_counts)}"
        )

    print()
    print(
        f"Documents processed: {len(documents)}"
    )
    print(
        f"Total chunks: {len(all_chunks)}"
    )

    print()
    print("Loading BGE embedding model...")

    model = SentenceTransformer(
        EMBEDDING_MODEL_NAME
    )

    embedding_dimension = (
        model.get_sentence_embedding_dimension()
    )

    if embedding_dimension != 384:
        raise ValueError(
            f"Expected 384 dimensions, "
            f"got {embedding_dimension}"
        )

    print(
        f"Embedding dimension: {embedding_dimension}"
    )

    print()
    print("Preparing ChromaDB...")

    if CHROMA_DIR.exists():
        print(
            "Removing existing ChromaDB directory "
            "to ensure a clean deterministic build..."
        )
        shutil.rmtree(CHROMA_DIR)

    CHROMA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    client = chromadb.PersistentClient(
        path=str(CHROMA_DIR)
    )

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={
            "description": (
                "CarePilot AI curated medical knowledge corpus"
            ),
            "embedding_model": EMBEDDING_MODEL_NAME,
            "embedding_dimension": embedding_dimension,
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": OVERLAP,
            "corpus_version": manifest["corpus_version"],
        },
    )

    print()
    print("Generating embeddings...")

    texts = [
        chunk["text"]
        for chunk in all_chunks
    ]

    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True,
    )

    if len(embeddings) != len(all_chunks):
        raise ValueError(
            "Embedding count does not match chunk count"
        )

    print()
    print("Upserting vectors into ChromaDB...")

    ids = [
        chunk["chunk_id"]
        for chunk in all_chunks
    ]

    metadatas = [
        {
            "document_id": chunk["document_id"],
            "title": chunk["title"],
            "source": chunk["source"],
            "source_url": chunk["source_url"],
            "document_type": chunk["document_type"],
            "section_heading": chunk["section_heading"],
            "date_added": chunk["date_added"],
            "chunk_index": chunk["chunk_index"],
        }
        for chunk in all_chunks
    ]

    collection.add(
        ids=ids,
        embeddings=embeddings.tolist(),
        documents=texts,
        metadatas=metadatas,
    )

    stored_count = collection.count()

    print()
    print("=" * 70)
    print("FULL RAG INGESTION COMPLETE")
    print("=" * 70)
    print(f"Corpus version: {manifest['corpus_version']}")
    print(f"Documents: {len(documents)}")
    print(f"Chunks: {len(all_chunks)}")
    print(f"Chroma vectors: {stored_count}")
    print(f"Embedding model: {EMBEDDING_MODEL_NAME}")
    print(f"Embedding dimension: {embedding_dimension}")
    print(f"Chunk size: {CHUNK_SIZE}")
    print(f"Overlap: {OVERLAP}")
    print(f"Chroma path: {CHROMA_DIR}")
    print(f"Collection: {COLLECTION_NAME}")

    if stored_count != len(all_chunks):
        raise ValueError(
            f"Chroma count mismatch: "
            f"{stored_count} != {len(all_chunks)}"
        )

    print("Validation: PASSED")


if __name__ == "__main__":
    main()
