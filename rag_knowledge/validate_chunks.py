import json
from pathlib import Path

BASE_DIR = Path(r".\rag_knowledge")
MANIFEST_PATH = BASE_DIR / "manifest" / "corpus_manifest.json"
CHUNKS_DIR = BASE_DIR / "chunks" / "final"

manifest = json.loads(
    MANIFEST_PATH.read_text(encoding="utf-8-sig")
)

expected_docs = [
    d["document_id"]
    for d in manifest["documents"]
]

files = sorted(CHUNKS_DIR.glob("*.json"))

errors = []
all_chunks = []
file_doc_ids = []

required_fields = {
    "chunk_id",
    "document_id",
    "title",
    "source",
    "source_url",
    "document_type",
    "section_heading",
    "date_added",
    "chunk_index",
    "text",
    "token_count",
}

for path in files:
    try:
        chunks = json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        errors.append(
            f"{path.name}: invalid JSON: {exc}"
        )
        continue

    doc_id = path.stem
    file_doc_ids.append(doc_id)

    if not isinstance(chunks, list):
        errors.append(
            f"{path.name}: root JSON value is not a list"
        )
        continue

    for chunk in chunks:
        all_chunks.append(chunk)

        missing = required_fields - set(chunk.keys())

        if missing:
            errors.append(
                f'{chunk.get("chunk_id", "UNKNOWN")}: '
                f"missing fields {sorted(missing)}"
            )

            continue

        if chunk["document_id"] != doc_id:
            errors.append(
                f'{chunk["chunk_id"]}: '
                f'document_id does not match file name'
            )

        if chunk["date_added"] != "2026-09-18":
            errors.append(
                f'{chunk["chunk_id"]}: '
                f'wrong date_added={chunk["date_added"]}'
            )

        if chunk["token_count"] > 400:
            errors.append(
                f'{chunk["chunk_id"]}: '
                f'token_count={chunk["token_count"]} > 400'
            )

        expected_prefix = f"{chunk['document_id']}_"

        if not chunk["chunk_id"].startswith(
            expected_prefix
        ):
            errors.append(
                f'{chunk["chunk_id"]}: invalid chunk ID prefix'
            )

        if not chunk["text"].strip():
            errors.append(
                f'{chunk["chunk_id"]}: empty text'
            )

        if chunk["section_heading"] is not None:
            if not chunk["text"].startswith(
                chunk["section_heading"]
            ):
                errors.append(
                    f'{chunk["chunk_id"]}: '
                    f'section heading missing from text'
                )

    indexes = [
        c.get("chunk_index")
        for c in chunks
        if "chunk_index" in c
    ]

    expected_indexes = list(range(len(chunks)))

    if indexes != expected_indexes:
        errors.append(
            f"{doc_id}: chunk indexes are not sequential"
        )

    ids = [
        c.get("chunk_id")
        for c in chunks
        if "chunk_id" in c
    ]

    expected_ids = [
        f"{doc_id}_{i:03d}"
        for i in range(len(chunks))
    ]

    if ids != expected_ids:
        errors.append(
            f"{doc_id}: chunk IDs are not deterministic/sequential"
        )

duplicates = []
seen = set()

for chunk in all_chunks:
    chunk_id = chunk.get("chunk_id")

    if chunk_id in seen:
        duplicates.append(chunk_id)

    seen.add(chunk_id)

if duplicates:
    errors.append(
        f"Duplicate chunk IDs: {duplicates}"
    )

missing_files = sorted(
    set(expected_docs) - set(file_doc_ids)
)

unexpected_files = sorted(
    set(file_doc_ids) - set(expected_docs)
)

if missing_files:
    errors.append(
        f"Missing document chunk files: {missing_files}"
    )

if unexpected_files:
    errors.append(
        f"Unexpected document chunk files: {unexpected_files}"
    )

print("=" * 70)
print("CAREPILOT AI — FINAL CHUNK VALIDATION")
print("=" * 70)

print(f"Manifest documents : {len(expected_docs)}")
print(f"Chunk JSON files    : {len(files)}")
print(f"Total chunks        : {len(all_chunks)}")

print()

if all_chunks:
    token_counts = [
        c["token_count"]
        for c in all_chunks
        if "token_count" in c
    ]

    print(f"Minimum tokens      : {min(token_counts)}")
    print(f"Maximum tokens      : {max(token_counts)}")
    print(
        f"Chunks <= 400      : "
        f"{sum(t <= 400 for t in token_counts)}/{len(token_counts)}"
    )

print()

if not errors:
    print("VALIDATION: PASS")
    print("All chunk structure and metadata checks passed.")
else:
    print("VALIDATION: FAIL")
    print(f"Errors: {len(errors)}")

    for error in errors:
        print(f"- {error}")
