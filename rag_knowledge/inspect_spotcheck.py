import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CHUNKS_DIR = BASE_DIR / "chunks" / "spotcheck"

for path in sorted(CHUNKS_DIR.glob("*.json")):
    chunks = json.loads(path.read_text(encoding="utf-8"))

    print("=" * 80)
    print(f"DOCUMENT: {path.stem}")
    print(f"CHUNKS: {len(chunks)}")
    print("=" * 80)

    for chunk in chunks:
        text = chunk["text"].replace("\n", " ")

        print()
        print(
            f'{chunk["chunk_id"]} | '
            f'index={chunk["chunk_index"]} | '
            f'tokens={chunk["token_count"]}'
        )
        print(f'Section: {chunk["section_heading"]}')
        print(f'Title: {chunk["title"]}')
        print(f'Text: {text[:500]}')

    print()
