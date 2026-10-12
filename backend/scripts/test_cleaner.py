"""
Test cleaner for both openFDA JSON and HTML documents against verify_real_data containment rules.
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

FDA_SECTIONS = [
    ("boxed_warning", "Boxed Warning"),
    ("indications_and_usage", "Indications and Usage"),
    ("dosage_and_administration", "Dosage and Administration"),
    ("dosage_forms_and_strengths", "Dosage Forms and Strengths"),
    ("contraindications", "Contraindications"),
    ("warnings_and_cautions", "Warnings and Cautions"),
    ("warnings", "Warnings"),
    ("adverse_reactions", "Adverse Reactions"),
    ("drug_interactions", "Drug Interactions"),
    ("use_in_specific_populations", "Use in Specific Populations"),
    ("pregnancy", "Pregnancy"),
    ("pediatric_use", "Pediatric Use"),
    ("geriatric_use", "Geriatric Use"),
    ("overdosage", "Overdosage"),
    ("clinical_pharmacology", "Clinical Pharmacology"),
    ("description", "Description"),
    ("how_supplied", "How Supplied/Storage and Handling"),
    ("patient_counseling_information", "Patient Counseling Information"),
]

def clean_openfda(p: Path, doc_info: dict) -> str:
    data = json.loads(p.read_text(encoding="utf-8"))
    results = data.get("results", [data])
    item = results[0] if results else {}
    
    title = doc_info.get("title", "Drug Information")
    doc_id = doc_info.get("doc_id", p.stem)
    url = doc_info.get("url", "")
    set_id = doc_info.get("set_id", item.get("set_id", ""))
    effective_time = doc_info.get("effective_time", item.get("effective_time", ""))
    
    lines = [
        f"# {title}",
        f"**Document ID:** {doc_id}",
        f"**Source:** openFDA",
        f"**URL:** {url}",
        f"**Set ID:** {set_id}",
        f"**Effective Time:** {effective_time}",
        f"**License:** US Public Domain (openFDA API)",
        "",
    ]
    
    for key, heading in FDA_SECTIONS:
        val = item.get(key)
        if not val:
            continue
        lines.append(f"## {heading}")
        lines.append("")
        if isinstance(val, list):
            for entry in val:
                if isinstance(entry, str):
                    for para in entry.splitlines():
                        para = para.strip()
                        if para:
                            lines.append(para)
                            lines.append("")
        elif isinstance(val, str):
            for para in val.splitlines():
                para = para.strip()
                if para:
                    lines.append(para)
                    lines.append("")
    return "\n".join(lines).strip()

# HTML Cleaner
# Section markers to remove:
REMOVED_SECTION_CLASSES = [
    "nav", "navbar", "footer", "site-footer", "header", "site-header",
    "sidebar", "side-bar", "related", "related-topics", "latest-news",
    "news", "research", "journal", "references", "citations", "social-share",
    "share-buttons", "breadcrumb", "breadcrumbs", "disclaimer", "feedback"
]

REMOVED_HEADING_PATTERNS = [
    r"related\s+topics",
    r"latest\s+news",
    r"research",
    r"journal\s+articles",
    r"clinical\s+trials",
    r"find\s+an\s+expert",
    r"patient\s+handouts",
    r"reference",
    r"topic\s+resources",
    r"for\s+you",
]

def clean_html(p: Path, doc_info: dict) -> str:
    raw_html = p.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw_html, "html.parser")
    
    # Remove script, style, comments
    for elem in soup(["script", "style", "noscript", "svg", "form", "iframe"]):
        elem.decompose()
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
        
    # Remove known non-content tags
    for tag in soup.find_all(["nav", "footer", "header", "aside"]):
        tag.decompose()
        
    # Remove sections matching class/id patterns
    for elem in list(soup.find_all()):
        if not hasattr(elem, "attrs") or not elem.attrs:
            continue
        classes = elem.attrs.get("class", [])
        if isinstance(classes, list):
            cls_str = " ".join(classes).lower()
        else:
            cls_str = str(classes).lower()
        if any(rem in cls_str for rem in ["footer", "header", "nav", "sidebar", "related", "share", "breadcrumb", "disclaimer", "feedback"]):
            elem.decompose()
            
    # Try finding main content container
    main = soup.find("article") or soup.find("main") or soup.find(id=re.compile(r"main|content|body", re.I)) or soup.body or soup
    
    title = doc_info.get("title", "")
    doc_id = doc_info.get("doc_id", p.stem)
    source = doc_info.get("source", "")
    url = doc_info.get("url", "")
    license_ = doc_info.get("license", "")
    
    lines = [
        f"# {title}",
        f"**Document ID:** {doc_id}",
        f"**Source:** {source}",
        f"**URL:** {url}",
        f"**License:** {license_}",
        "",
    ]
    
    # Traverse blocks in document order
    for elem in main.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
        # Check if heading matches removed pattern
        text = elem.get_text().strip()
        if not text:
            continue
        if elem.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            if any(re.search(pat, text, re.I) for pat in REMOVED_HEADING_PATTERNS):
                continue
            level = int(elem.name[1])
            hashes = "#" * max(2, min(6, level))
            lines.append(f"{hashes} {text}")
            lines.append("")
        elif elem.name == "li":
            lines.append(f"- {text}")
        else: # p
            lines.append(text)
            lines.append("")
            
    return "\n".join(lines).strip()

if __name__ == "__main__":
    manifest = json.loads((PROJECT_ROOT / "data" / "manifests" / "kb_snapshot_v3.json").read_text(encoding="utf-8"))
    docs = manifest["documents"]
    print(f"Testing cleaner on all {len(docs)} documents in v3 manifest...")
    
    low_contain = []
    missing_files = []
    
    for d in docs:
        did = d["doc_id"]
        is_fda = did.startswith("KB-FDA")
        raw_p = RAW_DIR / (f"{did}.json" if is_fda else f"{did}.html")
        if not raw_p.exists():
            # Check for alternative extensions
            alts = list(RAW_DIR.glob(f"{did}*"))
            if alts:
                raw_p = alts[0]
            else:
                missing_files.append(did)
                continue
                
        cleaned = clean_openfda(raw_p, d) if is_fda else clean_html(raw_p, d)
        b_text = body_text(cleaned)
        r_text = raw_text(raw_p)
        
        sset = shingles(tokens(b_text))
        rset = shingles(tokens(r_text))
        contain = len(sset & rset) / len(sset) if sset else 1.0
        
        if contain < 0.95:
            low_contain.append((did, d.get("title", ""), contain, len(sset), len(rset)))
            
    print(f"\nResults:")
    print(f"  Total tested: {len(docs) - len(missing_files)}")
    print(f"  Missing raw files: {len(missing_files)}")
    print(f"  Containment >= 0.95: {len(docs) - len(missing_files) - len(low_contain)}")
    print(f"  Containment < 0.95:  {len(low_contain)}")
    
    if low_contain:
        print("\nFirst 10 docs below 0.95:")
        for did, title, c, ss, rs in low_contain[:10]:
            print(f"  {did:12s} ({title[:30]:30s}): contain={c:.4f} (clean_shingles={ss}, raw_shingles={rs})")
