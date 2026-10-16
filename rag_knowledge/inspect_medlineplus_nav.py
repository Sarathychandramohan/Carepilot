from pathlib import Path
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"

TARGETS = [
    "KB-C02",
    "KB-C03",
    "KB-M03",
]

for document_id in TARGETS:
    matches = list(RAW_DIR.glob(f"{document_id}_*/page.html"))

    if not matches:
        matches = list(RAW_DIR.glob(f"{document_id}_*/*.html"))

    print("=" * 80)
    print(document_id)

    if not matches:
        print("RAW HTML FILE NOT FOUND")
        continue

    path = matches[0]
    print(f"File: {path}")

    html = path.read_text(
        encoding="utf-8",
        errors="replace"
    )

    soup = BeautifulSoup(html, "html.parser")

    for heading_text in [
        "Basics",
        "Learn More",
        "See, Play and Learn",
        "Research",
        "Resources",
        "For You",
    ]:
        heading = soup.find(
            lambda tag:
                tag.name in ["h1", "h2", "h3", "h4", "h5", "h6"]
                and tag.get_text(" ", strip=True) == heading_text
        )

        if heading:
            print()
            print(f"HEADING FOUND: {heading_text}")
            print(f"Tag: {heading.name}")
            print(f"Classes: {heading.get('class')}")
            print(f"ID: {heading.get('id')}")

            parent = heading.parent

            print(
                f"Parent: {parent.name if parent else None}"
            )
            print(
                f"Parent classes: "
                f"{parent.get('class') if parent else None}"
            )
            print(
                f"Parent ID: "
                f"{parent.get('id') if parent else None}"
            )

            print(
                "Parent preview:"
            )
            print(
                parent.get_text(
                    " ",
                    strip=True
                )[:600]
                if parent
                else ""
            )

    print()
