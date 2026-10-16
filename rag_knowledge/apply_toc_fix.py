from pathlib import Path

path = Path("./rag_knowledge/extract_and_clean.py")
text = path.read_text(encoding="utf-8")

old = '''def remove_unwanted_elements(container):

    # Remove obvious UI blocks.
    for element in list(
        container.find_all(
            class_=re.compile(
                r"(breadcrumb|share|social|menu)",
                re.IGNORECASE
            )
        )
    ):
        element.decompose()
'''

new = '''def remove_unwanted_elements(container):

    # Remove obvious UI blocks.
    for element in list(
        container.find_all(
            class_=re.compile(
                r"(breadcrumb|share|social|menu)",
                re.IGNORECASE
            )
        )
    ):
        element.decompose()

    # Remove MedlinePlus table-of-contents/navigation blocks.
    #
    # These blocks contain headings such as "Basics", "Research",
    # "Resources", "Children", etc. They are website navigation,
    # not medical content, and should not enter the RAG corpus.
    for element in list(
        container.find_all(
            class_="toccolumn"
        )
    ):
        element.decompose()
'''

if old not in text:
    raise RuntimeError(
        "Expected remove_unwanted_elements block was not found. "
        "No changes were made."
    )

path.write_text(text.replace(old, new), encoding="utf-8")
print("TOC navigation removal added successfully.")
