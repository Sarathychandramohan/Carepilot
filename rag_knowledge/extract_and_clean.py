from pathlib import Path
from bs4 import BeautifulSoup
import re


BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"
CLEANED_DIR = BASE_DIR / "cleaned"


REMOVE_TAGS = [
    "script",
    "style",
    "noscript",
    "svg",
    "form",
    "nav",
    "footer",
    "header",
    "iframe",
]


EXCLUDED_HEADINGS = {
    "references",
    "related medlineplus health topics",
    "related health topics",
    "related topics",
    "external links",
    "alternative names",
}


MOJIBAKE_REPLACEMENTS = {
    "â€™": "’",
    "â€˜": "‘",
    "â€œ": "“",
    "â€": "”",
    "â€“": "–",
    "â€”": "—",
    "â‰¥": "≥",
    "â‰¤": "≤",
    "Â ": " ",
    "Â": "",
}


def repair_mojibake(text: str) -> str:
    """
    Repair known UTF-8/Windows-1252 mojibake sequences that may have
    entered the previously generated cleaned text.
    """

    for bad, good in MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(bad, good)

    return text


def normalize_text(text: str) -> str:

    text = repair_mojibake(text)

    text = text.replace("\xa0", " ")
    text = text.replace("\r", "\n")

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    return text.strip()


def get_content_container(soup: BeautifulSoup):

    article = soup.find("article")

    if article:
        medline_article = article.find("div", id="d-article")
        if medline_article:
            return medline_article
        return article

    main = soup.find("main")

    if main:
        return main

    if soup.body:
        return soup.body

    return soup


def remove_unwanted_elements(container):

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


def extract_content(container):

    lines = []

    excluded_section = False
    container_classes = container.get("class") or []
    is_niddk_article = (
        container.name == "article"
        and "dk-content" in container_classes
    )
    seen_nidkk_navigation = False

    for element in container.find_all(
        ["h1", "h2", "h3", "p", "li"]
    ):

        text = normalize_text(
            element.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        lower_text = text.lower().strip()

        # Remove the NIDDK "On this page" navigation.
        #
        # We skip everything after H1 until the first H2.
        if element.name == "h1":
            lines.append(f"# {text}")
            lines.append("")

            seen_nidkk_navigation = is_niddk_article
            continue

        if element.name == "h2":

            heading = lower_text

            if heading in EXCLUDED_HEADINGS or heading.startswith("review date"):
                excluded_section = True
                continue

            excluded_section = False
            seen_nidkk_navigation = False

            lines.append(f"## {text}")
            lines.append("")
            continue

        if element.name == "h3":

            heading = lower_text

            if heading in EXCLUDED_HEADINGS or heading.startswith("review date"):
                excluded_section = True
                continue

            if excluded_section:
                continue

            seen_nidkk_navigation = False

            lines.append(f"### {text}")
            lines.append("")
            continue

        # Skip NIDDK navigation between H1 and first H2.
        if seen_nidkk_navigation:
            continue

        if excluded_section:
            continue

        if element.name == "p":

            # Skip obvious provenance/review metadata.
            if re.match(
                r"^Review Date\b",
                text,
                re.IGNORECASE
            ):
                excluded_section = True
                continue

            if re.match(
                r"^Updated by:",
                text,
                re.IGNORECASE
            ):
                continue

            lines.append(text)
            lines.append("")

        elif element.name == "li":

            # Skip nested list items when parent already contains them.
            if element.find_parent("li") is not None:
                continue

            lines.append(f"- {text}")

    return normalize_text(
        "\n".join(lines)
    )


def clean_document(input_path: Path, output_path: Path):

    html = input_path.read_text(
        encoding="utf-8"
    )

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    for tag_name in REMOVE_TAGS:

        for tag in soup.find_all(tag_name):
            tag.decompose()

    container = get_content_container(soup)

    if container is None:
        raise ValueError(
            f"No usable content found: {input_path}"
        )

    remove_unwanted_elements(container)

    cleaned = extract_content(container)

    if not cleaned:
        raise ValueError(
            f"Extraction produced empty output: {input_path}"
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path.write_text(
        cleaned + "\n",
        encoding="utf-8"
    )


def main():

    CLEANED_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    processed = 0

    for folder in sorted(
        RAW_DIR.iterdir()
    ):

        if not folder.is_dir():
            continue

        source_file = folder / "source.html"

        if not source_file.exists():
            print(
                f"SKIP: {folder.name} - "
                f"source.html not found"
            )
            continue

        document_id = folder.name.split("_")[0]

        output_file = (
            CLEANED_DIR /
            f"{document_id}.txt"
        )

        try:

            clean_document(
                source_file,
                output_file
            )

            size_kb = (
                output_file.stat().st_size / 1024
            )

            print(
                f"SUCCESS: {document_id} -> "
                f"{output_file.name} "
                f"({size_kb:.2f} KB)"
            )

            processed += 1

        except Exception as exc:

            print(
                f"FAILED: {document_id} -> {exc}"
            )

    print()
    print(
        f"Documents processed: {processed}"
    )


if __name__ == "__main__":
    main()




