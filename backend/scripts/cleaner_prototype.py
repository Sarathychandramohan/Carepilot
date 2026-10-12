"""
Test cleaner prototype and verify containment against verify_real_data's exact logic.
"""
import re
import html
import json
from pathlib import Path
from bs4 import BeautifulSoup

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

def clean_openfda_json(p: Path, doc_info: dict) -> str:
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
                    for para in entry.split("\n"):
                        para = para.strip()
                        if para:
                            lines.append(para)
                            lines.append("")
        elif isinstance(val, str):
            for para in val.split("\n"):
                para = para.strip()
                if para:
                    lines.append(para)
                    lines.append("")
    return "\n".join(lines).strip()

print("Prototype module loaded.")
