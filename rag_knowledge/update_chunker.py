from pathlib import Path

path = Path(r".\rag_knowledge\chunk_documents.py")

text = path.read_text(encoding="utf-8")

old = '''            chunk_text = decode_tokens(
                window,
                tokenizer,
            )
'''

new = '''            chunk_text = decode_tokens(
                window,
                tokenizer,
            )

            section_heading = section["section_heading"]

            if section_heading:
                chunk_text = (
                    f"{section_heading}\\n\\n"
                    f"{chunk_text}"
                )
'''

if old not in text:
    raise RuntimeError(
        "Expected chunk_text block was not found. "
        "No changes were made."
    )

text = text.replace(old, new, 1)

path.write_text(
    text,
    encoding="utf-8",
)

print("SUCCESS: chunker updated")
print("Section headings will now be included in chunk text.")
