from pathlib import Path

path = Path(r".\rag_knowledge\chunk_documents.py")

text = path.read_text(encoding="utf-8")

old = '''    spotcheck_ids = {
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
'''

new = '''    documents = manifest["documents"]
'''

if old not in text:
    raise RuntimeError(
        "Expected spot-check document block was not found. "
        "No changes were made."
    )

text = text.replace(old, new, 1)

text = text.replace(
    'CHUNKS_DIR = BASE_DIR / "chunks" / "spotcheck"',
    'CHUNKS_DIR = BASE_DIR / "chunks" / "final"',
    1,
)

text = text.replace(
    'print(f"Spot-check documents: {len(documents)}")',
    'print(f"Documents processed: {len(documents)}")',
    1,
)

path.write_text(
    text,
    encoding="utf-8",
)

print("SUCCESS: chunker configured for full corpus")
print("Output directory: rag_knowledge/chunks/final")
print(f"Documents configured: {len(documents) if 'documents' in locals() else 'manifest'}")
