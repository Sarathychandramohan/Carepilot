import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CHUNKS_DIR = BASE_DIR / "chunks" / "full"

THRESHOLD = 50

print("=" * 80)
print("RAG TINY-CHUNK AUDIT")
print("=" * 80)
print(f"Threshold: < {THRESHOLD} tokens")
print()

total = 0

for path in sorted(CHUNKS_DIR.glob("*.json")):
    chunks = json.loads(
        path.read_text(encoding="utf-8")
    )

    tiny = [
        chunk
        for chunk in chunks
        if chunk["token_count"] < THRESHOLD
    ]

    if not tiny:
        continue

    print("-" * 80)
    print(f"{path.stem}: {len(tiny)} tiny chunks")

    for chunk in tiny:
        total += 1

        text = chunk["text"].replace("\n", " ")

        print(
            f'{chunk["chunk_id"]} | '
            f'tokens={chunk["token_count"]} | '
            f'section="{chunk["section_heading"]}"'
        )
        print(f"Text: {text[:350]}")
        print()

print("=" * 80)
print(f"TOTAL TINY CHUNKS: {total}")
print("=" * 80)
