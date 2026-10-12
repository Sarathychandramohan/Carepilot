"""
Test precise container extraction for MedlinePlus, NIDDK, and WHO pages.
"""
import re
import html
import json
from pathlib import Path
from bs4 import BeautifulSoup, Comment

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "rag_knowledge" / "raw"

HEADER_LINE = re.compile(r"^\s*(#{1,6}\s|\*\*[A-Za-z0-9 _/-]+:\*\*|-{10,}\s*$|CHUNK \d+)")

def strip_markup(s: str) -> str:
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&[a-z]+;|&#\d+;", " ", s)
    return s

def tokens(text: str):
    return re.findall(r"[a-z0-9]+", text.lower())

def shingles(toks, n=5):
    return {" ".join(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))}

def body_text(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not HEADER_LINE.match(l))

def raw_text(p: Path) -> str:
    s = p.read_text(encoding="utf-8", errors="replace")
    if p.suffix.lower() == ".json":
        try:
            obj = json.loads(s)
        except ValueError:
            return s
        out = []
        def walk(x):
            if isinstance(x, str):
                out.append(x)
            elif isinstance(x, dict):
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(obj)
        return "\n".join(out)
    return html.unescape(strip_markup(s))

def extract_clean_html(p: Path, doc: dict) -> str:
    raw_html = p.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw_html, "html.parser")
    
    # Remove script, style, comments
    for elem in soup(["script", "style", "noscript", "svg", "form", "iframe"]):
        elem.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    # Find the best content container
    # 1. MedlinePlus Topic Summary
    # 2. MedlinePlus Encyclopedia article
    # 3. NIDDK content body
    # 4. WHO content body
    # 5. Article or main
    main = None
    for selector in [
        "#topic-summary",
        "#ency_summary",
        "#mplus-content",
        ".syndicate",
        "article",
        "main",
        "#main-content",
        "#content",
        ".main-content",
    ]:
        found = soup.select_one(selector)
        if found and len(found.get_text(strip=True)) > 200:
            main = found
            break
    if not main:
        main = soup.body or soup

    # Remove non-content elements inside the container
    for tag in list(main.find_all(["nav", "footer", "header", "aside"])):
        tag.decompose()
        
    for elem in list(main.find_all()):
        if not hasattr(elem, "attrs") or not elem.attrs:
            continue
        classes = elem.attrs.get("class", [])
        cls_str = " ".join(classes).lower() if isinstance(classes, list) else str(classes).lower()
        id_str = str(elem.attrs.get("id", "")).lower()
        if any(rem in cls_str or rem in id_str for rem in [
            "social-share", "share-buttons", "breadcrumb", "disclaimer", "feedback",
            "page-footer", "site-footer", "navigation", "nav-bar"
        ]):
            elem.decompose()

    title = doc.get("title", "")
    doc_id = doc.get("doc_id", p.stem)
    source = doc.get("source", "")
    url = doc.get("url", "")
    license_ = doc.get("license", "")

    lines = [
        f"# {title}",
        f"**Document ID:** {doc_id}",
        f"**Source:** {source}",
        f"**URL:** {url}",
        f"**License:** {license_}",
        "",
    ]

    # Extract text block by block preserving headings in document stream
    for elem in main.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "table"]):
        if elem.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            text = elem.get_text().strip()
            if text:
                lines.append(f"**{text}**")
                lines.append("")
        elif elem.name in ["ul", "ol"]:
            for li in elem.find_all("li", recursive=False):
                li_text = li.get_text().strip()
                if li_text:
                    lines.append(f"- {li_text}")
            lines.append("")
        elif elem.name == "p":
            p_text = elem.get_text().strip()
            if p_text:
                lines.append(p_text)
                lines.append("")
        elif elem.name == "table":
            for tr in elem.find_all("tr"):
                cells = [td.get_text().strip() for td in tr.find_all(["td", "th"])]
                if any(cells):
                    lines.append(" | ".join(cells))
            lines.append("")

    return "\n".join(lines).strip()

if __name__ == "__main__":
    manifest = json.loads((PROJECT_ROOT / "data" / "manifests" / "kb_snapshot_v3.json").read_text(encoding="utf-8"))
    docs = [d for d in manifest["documents"] if not d["doc_id"].startswith("KB-FDA")]
    print(f"Testing HTML cleaner on {len(docs)} documents...")
    
    results = []
    low_contain = []
    for d in docs:
        did = d["doc_id"]
        raw_p = RAW_DIR / f"{did}.html"
        if not raw_p.exists():
            alts = list(RAW_DIR.glob(f"{did}*"))
            if alts:
                raw_p = alts[0]
            else:
                continue
        cleaned = extract_clean_html(raw_p, d)
        b_text = body_text(cleaned)
        r_text = raw_text(raw_p)
        sset = shingles(tokens(b_text))
        rset = shingles(tokens(r_text))
        contain = len(sset & rset) / len(sset) if sset else 1.0
        results.append(contain)
        if contain < 0.95:
            low_contain.append((did, d.get("title", ""), contain, len(sset), len(rset)))
            
    print(f"\nHTML Containment Summary:")
    print(f"  Mean containment: {sum(results)/len(results):.4f}")
    print(f"  Min containment:  {min(results):.4f}")
    print(f"  >= 0.95:          {sum(c >= 0.95 for c in results)} / {len(results)}")
    print(f"  < 0.95:           {len(low_contain)}")
    if low_contain:
        print("\nDocs below 0.95:")
        for did, title, c, ss, rs in low_contain[:10]:
            print(f"  {did:12s} ({title[:30]:30s}): contain={c:.4f} (clean_shingles={ss}, raw_shingles={rs})")
