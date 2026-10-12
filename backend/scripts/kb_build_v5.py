"""
CarePilot Knowledge Base Snapshot v5 Builder.
Builds strictly from rag_knowledge/raw ONLY (no network access).

Pipeline:
1. Deterministic HTML and openFDA JSON cleaner (identical to v4).
2. Chunking with BAAI/bge-small-en-v1.5 tokenizer (400 tokens, 60 overlap).
3. Chunk naming: kb:{doc_id}:chunk{n:04d}.
4. ChromaDB collection: carepilot_kb_v5.
5. BM25 index: rag_knowledge/bm25_index_v5.pkl.
6. Clean chunk text export: rag_knowledge/kb_export_v5/{doc_id}.txt.
7. Manifest: data/manifests/kb_snapshot_v5.json (frozen = false initially).
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from bs4 import BeautifulSoup, Comment
from transformers import AutoTokenizer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.scripts.kb_chunk import chunk_document, TOKENIZER_NAME, CHUNK_SIZE, OVERLAP
from backend.scripts.kb_build_index import build_chroma_index
from backend.scripts.kb_build_bm25 import build_bm25_index

RAW_DIR = PROJECT_ROOT / "rag_knowledge" / "raw"
EXPORT_DIR = PROJECT_ROOT / "rag_knowledge" / "kb_export_v5"
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"
CHROMA_DIR = PROJECT_ROOT / "rag_knowledge" / "chroma_db"

DUPLICATES_TO_REMOVE = {"KB-MP0055", "KB-MP0059", "KB-MP0080", "KB-MP0795", "KB-FDA0119"}

# openFDA section heading map
FDA_SECTION_HEADINGS = {
    "boxed_warning": "Boxed Warning",
    "active_ingredient": "Active Ingredient",
    "purpose": "Purpose",
    "indications_and_usage": "Indications and Usage",
    "dosage_and_administration": "Dosage and Administration",
    "dosage_forms_and_strengths": "Dosage Forms and Strengths",
    "contraindications": "Contraindications",
    "warnings_and_cautions": "Warnings and Cautions",
    "warnings": "Warnings",
    "precautions": "Precautions",
    "do_not_use": "Do Not Use",
    "ask_doctor": "Ask a Doctor",
    "ask_doctor_or_pharmacist": "Ask a Doctor or Pharmacist",
    "when_using": "When Using This Product",
    "stop_use": "Stop Use",
    "pregnancy_or_breast_feeding": "Pregnancy or Breast Feeding",
    "keep_out_of_reach_of_children": "Keep Out of Reach of Children",
    "adverse_reactions": "Adverse Reactions",
    "drug_interactions": "Drug Interactions",
    "use_in_specific_populations": "Use in Specific Populations",
    "pregnancy": "Pregnancy",
    "pediatric_use": "Pediatric Use",
    "geriatric_use": "Geriatric Use",
    "overdosage": "Overdosage",
    "clinical_pharmacology": "Clinical Pharmacology",
    "description": "Description",
    "how_supplied": "How Supplied/Storage and Handling",
    "storage_and_handling": "Storage and Handling",
    "patient_counseling_information": "Patient Counseling Information",
    "information_for_patients": "Information for Patients",
    "spl_unclassified_section": "Clinical Information",
}

SOURCE_TERMS_MAP = {
    "MedlinePlus": {
        "license": "US Public Domain",
        "terms_url": "https://www.nlm.nih.gov/web_policies.html",
        "review_status": "VERIFIED_US_GOV"
    },
    "NIDDK": {
        "license": "US Public Domain",
        "terms_url": "https://www.niddk.nih.gov/about-niddk/policies",
        "review_status": "VERIFIED_US_GOV"
    },
    "openFDA": {
        "license": "CC0 1.0 Universal / US Public Domain",
        "terms_url": "https://open.fda.gov/terms/",
        "review_status": "VERIFIED_US_GOV"
    },
    "FDA": {
        "license": "US Public Domain",
        "terms_url": "https://open.fda.gov/terms/",
        "review_status": "VERIFIED_US_GOV"
    },
    "WHO": {
        "license": "WHO Copyright (Non-commercial educational use permitted)",
        "terms_url": "https://www.who.int/about/policies/publishing/copyright",
        "review_status": "REVIEW_NEEDED"
    },
    "NHS": {
        "license": "Open Government Licence v3.0",
        "terms_url": "https://www.nhs.uk/our-policies/terms-and-conditions/",
        "review_status": "REVIEW_NEEDED"
    }
}

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

def clean_openfda_json(p: Path, doc_info: dict) -> tuple[str, dict]:
    data = json.loads(p.read_text(encoding="utf-8"))
    results = data.get("results", [data])
    item = results[0] if results else {}
    
    title = doc_info.get("title", "Drug Information")
    set_id = item.get("set_id", doc_info.get("set_id", ""))
    effective_time = item.get("effective_time", doc_info.get("effective_time", ""))
    
    lines = [
        f"# {title}",
        "",
    ]
    
    sections_extracted = []
    for key, val in item.items():
        if key not in FDA_SECTION_HEADINGS or not val:
            continue
        heading = FDA_SECTION_HEADINGS[key]
        sections_extracted.append(key)
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
                    
    cleaned_text = "\n".join(lines).strip()
    metadata = {
        "set_id": set_id,
        "effective_time": effective_time,
        "sections_extracted": sections_extracted,
    }
    return cleaned_text, metadata

def clean_html_document(p: Path, doc_info: dict) -> str:
    raw_html = p.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw_html, "html.parser")
    
    for elem in soup(["script", "style", "noscript", "svg", "form", "iframe"]):
        elem.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()
        
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

    title = doc_info.get("title", "")
    lines = [
        f"# {title}",
        "",
    ]

    for elem in main.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "table"]):
        if elem.find_parent(["ul", "ol", "table"]):
            continue
        if elem.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            text = elem.get_text().strip()
            if text:
                if any(re.search(pat, text, re.I) for pat in REMOVED_HEADING_PATTERNS):
                    continue
                lines.append(f"**{text}**")
                lines.append("")
        elif elem.name in ["ul", "ol"]:
            for li in elem.find_all("li"):
                li_copy = BeautifulSoup(str(li), "html.parser").li
                if li_copy:
                    for sub in li_copy.find_all(["ul", "ol"]):
                        sub.decompose()
                    li_text = " ".join(li_copy.get_text(separator=" ").split())
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

def build_v5_corpus():
    print("=" * 70)
    print("CarePilot KB Snapshot v5 Builder (from rag_knowledge/raw ONLY)")
    print("=" * 70, flush=True)

    fetch_report_p = MANIFEST_DIR / "kb_raw_fetch_report.json"
    fda_prov_p = MANIFEST_DIR / "openfda_ingest_provenance.json"
    v4_manifest_p = MANIFEST_DIR / "kb_snapshot_v4.json"

    fetch_docs = {}
    fetch_hashes = {}
    if fetch_report_p.exists():
        f_data = json.loads(fetch_report_p.read_text(encoding="utf-8-sig"))
        for d in (f_data.get("documents", []) if isinstance(f_data, dict) else f_data):
            did = d.get("doc_id")
            if did:
                fetch_docs[did] = d
                fetch_hashes[did] = d.get("raw_sha256") or d.get("sha256") or d.get("sha256_raw")

    fda_provenance = {}
    if fda_prov_p.exists():
        f_data = json.loads(fda_prov_p.read_text(encoding="utf-8-sig"))
        docs_val = f_data.get("documents", {})
        if isinstance(docs_val, dict):
            for did, info in docs_val.items():
                fda_provenance[did] = info
                if isinstance(info, dict):
                    fetch_hashes[did] = info.get("raw_sha256") or info.get("sha256")

    # Combine documents from v4 and newly fetched documents
    v4_manifest = json.loads(v4_manifest_p.read_text(encoding="utf-8")) if v4_manifest_p.exists() else {}
    docs_to_process = {}
    for d in v4_manifest.get("documents", []):
        docs_to_process[d["doc_id"]] = d

    for did, finfo in fetch_docs.items():
        if did not in docs_to_process:
            is_fda = did.startswith("KB-FDA")
            fda_info = fda_provenance.get(did, {})
            docs_to_process[did] = {
                "doc_id": did,
                "title": finfo.get("title", ""),
                "source": "openFDA" if is_fda else finfo.get("source", "MedlinePlus"),
                "url": fda_info.get("request_url") if is_fda else finfo.get("url", ""),
                "set_id": fda_info.get("set_id") if is_fda else None,
                "effective_time": fda_info.get("effective_time") if is_fda else None,
                "retrieved_at": finfo.get("retrieved_at") or fda_info.get("retrieved_at") or "2026-10-11T13:00:00Z"
            }

    print(f"Total candidate documents to process for v5: {len(docs_to_process)}", flush=True)

    cleaned_documents = []
    for did in sorted(docs_to_process.keys()):
        if did in DUPLICATES_TO_REMOVE:
            continue
        doc_meta = docs_to_process[did]
        title = doc_meta["title"]
        source = doc_meta.get("source", "MedlinePlus")
        url = doc_meta.get("url", "")

        is_fda = did.startswith("KB-FDA")
        raw_p = RAW_DIR / (f"{did}.json" if is_fda else f"{did}.html")
        if not raw_p.exists():
            alts = list(RAW_DIR.glob(f"{did}*"))
            if alts:
                raw_p = alts[0]
            else:
                print(f"  [ERROR] Missing raw file for {did}", flush=True)
                continue

        raw_sha = fetch_hashes.get(did)
        if not raw_sha:
            raw_sha = hashlib.sha256(raw_p.read_bytes()).hexdigest()

        retrieved_at = doc_meta.get("retrieved_at") or "2026-10-11T13:00:00Z"

        terms_info = SOURCE_TERMS_MAP.get(source, SOURCE_TERMS_MAP.get("MedlinePlus"))
        license_name = terms_info["license"]
        terms_url = terms_info["terms_url"]
        review_status = terms_info["review_status"]

        fda_meta = {}
        if is_fda:
            prov = fda_provenance.get(did, {})
            doc_url = prov.get("request_url") or url
            cleaned_text, fda_meta = clean_openfda_json(raw_p, {
                "doc_id": did,
                "title": title,
                "url": doc_url,
                "set_id": prov.get("set_id", doc_meta.get("set_id", "")),
                "effective_time": prov.get("effective_time", doc_meta.get("effective_time", "")),
            })
        else:
            doc_url = url
            cleaned_text = clean_html_document(raw_p, {
                "doc_id": did,
                "title": title,
                "source": source,
                "url": doc_url,
                "license": license_name,
            })

        cleaned_documents.append({
            "doc_id": did,
            "title": title,
            "source": source,
            "url": fda_provenance.get(did, {}).get("request_url") if is_fda else doc_url,
            "license": license_name,
            "license_terms_url": terms_url,
            "license_status": review_status,
            "retrieved_at": retrieved_at,
            "raw_sha256": raw_sha,
            "set_id": fda_meta.get("set_id") if is_fda else None,
            "effective_time": fda_meta.get("effective_time") if is_fda else None,
            "cleaned_text": cleaned_text,
        })

    print(f"Cleaned {len(cleaned_documents)} total documents.", flush=True)

    # Chunking
    print("\n[Step 2: Chunking documents with BGE tokenizer]", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME)
    all_chunks = []
    for doc in cleaned_documents:
        chunks = chunk_document(
            doc_id=doc["doc_id"],
            doc_title=doc["title"],
            source_name=doc["source"],
            license_type=doc["license"],
            commercial_restricted=(doc["license_status"] == "REVIEW_NEEDED"),
            text=doc["cleaned_text"],
            snapshot_id="v5",
            tokenizer=tokenizer,
        )
        doc["chunk_count"] = len(chunks)
        all_chunks.extend(chunks)

    print(f"Generated {len(all_chunks)} total chunks across {len(cleaned_documents)} documents.", flush=True)

    # Export clean chunk text to rag_knowledge/kb_export_v5
    print(f"\n[Step 3: Exporting stored chunk text to {EXPORT_DIR}]", flush=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    from collections import defaultdict
    chunks_by_doc = defaultdict(list)
    for c in all_chunks:
        chunks_by_doc[c["doc_id"]].append(c)

    for doc in cleaned_documents:
        did = doc["doc_id"]
        doc_chunks = chunks_by_doc.get(did, [])
        doc_chunks.sort(key=lambda x: x["chunk_id"])
        joined_text = "\n\n".join(c["text"].strip() for c in doc_chunks if c["text"].strip()) + "\n"
        out_file = EXPORT_DIR / f"{did}.txt"
        out_file.write_text(joined_text, encoding="utf-8")
        doc["text_sha256"] = hashlib.sha256(out_file.read_bytes()).hexdigest()

    # Build ChromaDB collection carepilot_kb_v5
    print("\n[Step 4: Indexing into ChromaDB collection 'carepilot_kb_v5']", flush=True)
    build_chroma_index(all_chunks, collection_name="carepilot_kb_v5", chroma_dir=CHROMA_DIR)

    # Build BM25 index
    bm25_v5_path = PROJECT_ROOT / "rag_knowledge" / "bm25_index_v5.pkl"
    print(f"\n[Step 5: Building sparse BM25 index -> {bm25_v5_path}]", flush=True)
    build_bm25_index(all_chunks, output_path=bm25_v5_path)

    # Write Manifest v5
    print("\n[Step 6: Writing Snapshot v5 Manifest]", flush=True)
    manifest_v5 = {
        "snapshot_id": "v5",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "frozen": False,
        "chroma_collection": "carepilot_kb_v5",
        "bm25_index_path": str(bm25_v5_path.relative_to(PROJECT_ROOT)),
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "tokenizer": TOKENIZER_NAME,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": OVERLAP,
        "total_documents": len(cleaned_documents),
        "total_chunks": len(all_chunks),
        "documents": [
            {
                "doc_id": d["doc_id"],
                "title": d["title"],
                "source": d["source"],
                "url": d["url"],
                "license": d["license"],
                "license_terms_url": d["license_terms_url"],
                "license_status": d["license_status"],
                "retrieved_at": d["retrieved_at"],
                "raw_sha256": d["raw_sha256"],
                "text_sha256": d["text_sha256"],
                "set_id": d["set_id"],
                "effective_time": d["effective_time"],
                "chunk_count": d["chunk_count"],
            }
            for d in cleaned_documents
        ]
    }

    manifest_v5_path = MANIFEST_DIR / "kb_snapshot_v5.json"
    manifest_v5_path.write_text(json.dumps(manifest_v5, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote snapshot v5 manifest -> {manifest_v5_path}", flush=True)
    print("\n[OK] Snapshot v5 build complete.", flush=True)

if __name__ == '__main__':
    build_v5_corpus()
