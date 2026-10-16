import json
from pathlib import Path

from transformers import AutoTokenizer


BASE_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = BASE_DIR / "manifest" / "corpus_manifest.json"
CLEANED_DIR = BASE_DIR / "cleaned"
CHUNKS_DIR = BASE_DIR / "chunks" / "spotcheck"

TOKENIZER_NAME = "BAAI/bge-small-en-v1.5"

CHUNK_SIZE = 400
OVERLAP = 60
STRIDE = CHUNK_SIZE - OVERLAP
DATE_ADDED = "2026-09-18"


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

        windows = token_windows(
            section["text"],
            tokenizer,
        )

        for window in windows:
            body_text = decode_tokens(
                window,
                tokenizer,
            )

            if section_heading:
                chunk_text = (
                    f"{section_heading}\n\n"
                    f"{body_text}"
                )
            else:
                chunk_text = body_text

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
        if chunk["document_id"] != document_id:
            raise ValueError(
                f"{document_id}: incorrect document_id"
            )

        if not chunk["title"]:
            raise ValueError(
                f"{document_id}: missing manifest title"
            )

        if not chunk["source_url"]:
            raise ValueError(
                f"{document_id}: missing source_url"
            )

        if not chunk["section_heading"]:
            raise ValueError(
                f"{document_id}: missing section_heading"
            )

        if chunk["token_count"] > CHUNK_SIZE:
            raise ValueError(
                f'{document_id}: {chunk["chunk_id"]} '
                f'exceeds {CHUNK_SIZE} tokens'
            )

        if not chunk["text"].startswith(
            chunk["section_heading"]
        ):
            raise ValueError(
                f'{document_id}: {chunk["chunk_id"]} '
                f'does not start with section heading'
            )


def main():
    manifest = load_manifest()

    tokenizer = AutoTokenizer.from_pretrained(
        TOKENIZER_NAME
    )

    spotcheck_ids = {
        "KB-D01",
        "KB-K01",
        "KB-C01",
        "KB-M01",
    }

    documents = [
        document
        for document in manifest["documents"]
        if document["document_id"] in spotcheck_ids
    ]

    if len(documents) != 4:
        raise ValueError(
            f"Expected 4 spot-check documents, "
            f"found {len(documents)}"
        )

    CHUNKS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    total_chunks = 0

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

        total_chunks += len(chunks)

        token_counts = [
            chunk["token_count"]
            for chunk in chunks
        ]

        print(
            f"SUCCESS: {document_id} "
            f"-> {len(chunks)} chunks | "
            f"min={min(token_counts)} | "
            f"max={max(token_counts)}"
        )

    print()
    print(f"Spot-check documents: {len(documents)}")
    print(f"Total chunks: {total_chunks}")
    print("Validation: PASSED")
    print("Section headings included in chunk text: YES")
    print("Manifest titles used: YES")
    print("Sequential chunk IDs: YES")
    print(f"Maximum chunk size: {CHUNK_SIZE} tokens")


if __name__ == "__main__":
    main()
