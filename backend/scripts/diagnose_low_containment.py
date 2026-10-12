"""
Diagnose documents with body containment < 0.95 in Snapshot v4.
Prints 3 missing sentences per low-containment document.
"""
import csv
import json
import re
import html
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_FILE = PROJECT_ROOT / "data" / "reports" / "real_data_kb_check.csv"
RAW_DIR = PROJECT_ROOT / "rag_knowledge" / "raw"
CLEAN_DIR = PROJECT_ROOT / "rag_knowledge" / "kb_export_v4"

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

with open(REPORT_FILE, encoding="utf-8-sig") as f:
    r = csv.DictReader(f)
    flagged = [row for row in r if "TEXT_NOT_TRACEABLE_TO_RAW" in row["flags"]]

print(f"Total documents with TEXT_NOT_TRACEABLE_TO_RAW: {len(flagged)}")
print("=" * 80)

for row in flagged[:10]:
    did = row["doc_id"]
    title = row["title"]
    contain = row["body_traceable_to_raw"]
    
    clean_p = CLEAN_DIR / f"{did}.txt"
    raw_p = RAW_DIR / f"{did}.html"
    if not raw_p.exists():
        raw_p = RAW_DIR / f"{did}.json"
    if not raw_p.exists():
        alts = list(RAW_DIR.glob(f"{did}*"))
        if alts:
            raw_p = alts[0]
            
    if not clean_p.exists() or not raw_p.exists():
        continue
        
    c_text = clean_p.read_text(encoding="utf-8", errors="replace")
    b_text = body_text(c_text)
    r_text = raw_text(raw_p)
    
    sset = shingles(tokens(b_text))
    rset = shingles(tokens(r_text))
    missing = sset - rset
    
    print(f"\nDocument: {did} | Title: {title} | Containment: {contain}")
    print(f"  Clean shingles: {len(sset)}, Missing shingles: {len(missing)}")
    
    # Find sentences containing missing shingles
    sentences = re.split(r"(?<=[.!?])\s+", b_text)
    missing_sentences = []
    for sent in sentences:
        sent_clean = sent.strip()
        if not sent_clean:
            continue
        sent_shingles = shingles(tokens(sent_clean))
        if sent_shingles & missing:
            missing_sentences.append(sent_clean)
            if len(missing_sentences) >= 3:
                break
                
    print(f"  Sample missing sentences/segments ({len(missing_sentences)}):")
    for i, ms in enumerate(missing_sentences, 1):
        print(f"    {i}. {ms[:120]}")
