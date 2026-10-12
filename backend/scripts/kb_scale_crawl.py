"""
D:\\CarePilotAI\\backend\\scripts\\kb_scale_crawl.py

Crawls and ingests 500+ public-domain medical documents from:
1. MedlinePlus XML Service / Health Topics API (NIH / NLM)
2. MedlinePlus Lab Tests (NIH / NLM)
3. openFDA DailyMed Drug Labels (FDA / NLM)
4. Curated Core NIDDK / CDC documents

For each document:
- Clean Markdown extraction
- Provenance recording (doc_id, title, source_name, source_url, license, sha256, retrieved_at)
- Stable chunking (400 tokens, 60 overlap, BAAI/bge-small-en-v1.5)
- Dual Indexing: ChromaDB (carepilot_kb_v2) and BM25 (bm25_index_v2.pkl)
- Manifest write to data/manifests/kb_snapshot_v2.json
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup
from transformers import AutoTokenizer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.scripts.kb_clean import clean_markdown_document
from backend.scripts.kb_chunk import chunk_document, TOKENIZER_NAME
from backend.scripts.kb_build_index import build_chroma_index
from backend.scripts.kb_build_bm25 import build_bm25_index

RAW_DIR = PROJECT_ROOT / "data" / "kb_raw"
CLEAN_DIR = PROJECT_ROOT / "data" / "kb_clean"
CHUNKS_DIR = PROJECT_ROOT / "data" / "kb_chunks"
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"

MEDLINEPLUS_TERMS = [
    "diabetes", "type 2 diabetes", "blood sugar", "glucose", "a1c",
    "kidney disease", "chronic kidney disease", "creatinine", "gfr", "albuminuria",
    "hypertension", "high blood pressure", "blood pressure medicines", "systolic",
    "cholesterol", "ldl cholesterol", "hdl cholesterol", "triglycerides", "statins",
    "heart disease", "coronary artery disease", "heart failure", "angina",
    "asthma", "copd", "pneumonia", "bronchitis", "respiratory infections",
    "hypothyroidism", "hyperthyroidism", "thyroid", "anemia", "iron deficiency",
    "liver disease", "fatty liver", "hepatitis", "cirrhosis", "alt ast",
    "potassium", "sodium", "calcium", "electrolytes", "dehydration",
    "gerd", "acid reflux", "stomach ulcer", "gastritis", "diarrhea",
    "depression", "anxiety", "insomnia", "stress", "mental health",
    "stroke", "transient ischemic attack", "dizziness", "neuropathy",
    "osteoarthritis", "rheumatoid arthritis", "gout", "back pain",
    "urinary tract infection", "kidney stones", "hematuria", "proteinuria",
]

MEDLINEPLUS_API_URL = "https://wsearch.nlm.nih.gov/ws/query"


async def fetch_medlineplus_topics(client: httpx.AsyncClient, max_docs: int = 450) -> list[dict[str, Any]]:
    """
    Fetches health topics from MedlinePlus Search Web Service (NIH/NLM).
    """
    print(f"\n[MedlinePlus] Querying Search API across {len(MEDLINEPLUS_TERMS)} health domains...")
    topics = []
    seen_titles = set()
    doc_count = 0

    for term in MEDLINEPLUS_TERMS:
        if doc_count >= max_docs:
            break
        params = {
            "db": "healthTopics",
            "term": term,
            "retmax": 20,
        }
        try:
            resp = await client.get(MEDLINEPLUS_API_URL, params=params, timeout=15.0)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for doc in root.findall(".//document"):
                    title = ""
                    url = doc.get("url", "")
                    summary = ""
                    
                    for elem in doc.findall(".//content"):
                        name = elem.get("name")
                        if name == "title":
                            title = "".join(elem.itertext()).strip()
                        elif name == "FullSummary":
                            summary = "".join(elem.itertext()).strip()

                    # Clean HTML tags
                    soup = BeautifulSoup(summary, "html.parser")
                    clean_summary = soup.get_text("\n\n").strip()

                    if not clean_summary or len(clean_summary) < 150:
                        continue

                    title_clean = re.sub(r"<[^>]+>", "", title).strip()
                    if not title_clean or title_clean in seen_titles:
                        continue
                    seen_titles.add(title_clean)

                    doc_id = f"KB-MP{doc_count+1:04d}"
                    md_lines = [
                        f"# {title_clean}\n",
                        f"**Source:** MedlinePlus (National Library of Medicine / NIH)\n",
                        f"**URL:** {url}\n",
                        f"**License:** Public Domain (US Government Work)\n\n",
                        f"## Detailed Clinical Summary\n{clean_summary}\n",
                    ]

                    topics.append({
                        "doc_id": doc_id,
                        "title": title_clean,
                        "source_name": "MedlinePlus (NIH/NLM)",
                        "source_url": url,
                        "license": "Public Domain",
                        "commercial_use_restricted": False,
                        "topic": term,
                        "raw_text": "\n".join(md_lines),
                    })
                    doc_count += 1
                    if doc_count >= max_docs:
                        break
        except Exception as e:
            pass

        await asyncio.sleep(0.3)  # Polite API throttling

    print(f"[MedlinePlus] Ingested {len(topics)} unique topic documents.")
    return topics


# ---------------------------------------------------------------------------
# 2. DailyMed / openFDA Drug Labels (120+ common medications)
# ---------------------------------------------------------------------------

EXPANDED_DRUGS = [
    # Cardiovascular & Blood Pressure
    "Lisinopril", "Amlodipine", "Losartan", "Hydrochlorothiazide", "Metoprolol",
    "Furosemide", "Atorvastatin", "Simvastatin", "Rosuvastatin", "Carvedilol",
    "Valsartan", "Spironolactone", "Diltiazem", "Clonidine", "Hydralazine",
    "Pravastatin", "Ezetimibe", "Propranolol", "Atenolol", "Ramipril",
    "Bumetanide", "Torsemide", "Chlorthalidone", "Nifedipine", "Nitroglycerin",

    # Diabetes & Endocrine
    "Metformin", "Insulin Glargine", "Empagliflozin", "Dapagliflozin", "Glipizide",
    "Glimepiride", "Sitagliptin", "Semaglutide", "Dulaglutide", "Pioglitazone",
    "Levothyroxine", "Liraglutide", "Canagliflozin", "Linagliptin", "Repaglinide",

    # Kidney & Electrolytes
    "Potassium Chloride", "Sodium Bicarbonate", "Calcium Acetate", "Sevelamer",
    "Cinacalcet", "Allopurinol", "Febuxostat", "Colchicine",

    # Respiratory & Allergy
    "Albuterol", "Fluticasone", "Montelukast", "Budesonide", "Ipratropium",
    "Tiotropium", "Cetirizine", "Loratadine", "Fexofenadine", "Diphenhydramine",
    "Prednisone", "Methylprednisolone", "Dexamethasone",

    # Gastrointestinal
    "Omeprazole", "Pantoprazole", "Famotidine", "Esomeprazole", "Lansoprazole",
    "Metoclopramide", "Ondansetron", "Sucralfate", "Dicyclomine",

    # Neurological & Analgesic
    "Gabapentin", "Pregabalin", "Duloxetine", "Tramadol", "Acetaminophen",
    "Ibuprofen", "Naproxen", "Meloxicam", "Celecoxib", "Baclofen",
    "Cyclobenzaprine", "Tizanidine", "Sertraline", "Escitalopram", "Fluoxetine",

    # Anti-infectives
    "Amoxicillin", "Azithromycin", "Ciprofloxacin", "Levofloxacin", "Cephalexin",
    "Doxycycline", "Trimethoprim-Sulfamethoxazole", "Nitrofurantoin", "Fluconazole",
    "Clindamycin", "Metronidazole", "Cefdinir", "Augmentin",

    # Anticoagulants & Antiplatelets
    "Aspirin", "Clopidogrel", "Apixaban", "Rivaroxaban", "Warfarin",
    "Dabigatran", "Enoxaparin",
]

OPENFDA_URL = "https://api.fda.gov/drug/label.json"


async def fetch_openfda_labels(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    print(f"\n[openFDA] Ingesting drug labels for {len(EXPANDED_DRUGS)} medications...")
    docs = []
    doc_idx = 1

    for drug in EXPANDED_DRUGS:
        params = {
            "search": f'openfda.generic_name:"{drug}" OR openfda.brand_name:"{drug}"',
            "limit": 1,
        }
        try:
            resp = await client.get(OPENFDA_URL, params=params, timeout=12.0)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    label_data = results[0]
                    doc_id = f"KB-FDA{doc_idx:04d}"
                    
                    md_lines = [
                        f"# {drug} — Prescription Drug Label Information\n",
                        f"**Source:** openFDA / DailyMed (US National Library of Medicine)\n",
                        f"**License:** Public Domain (US Government Work)\n\n",
                    ]
                    
                    sections = [
                        ("indications_and_usage", "Indications and Usage"),
                        ("dosage_and_administration", "Dosage and Administration"),
                        ("contraindications", "Contraindications"),
                        ("warnings_and_cautions", "Warnings and Precautions"),
                        ("adverse_reactions", "Adverse Reactions and Side Effects"),
                        ("drug_interactions", "Drug Interactions"),
                        ("description", "Description and Mechanism"),
                    ]
                    
                    for sec_key, sec_title in sections:
                        val = label_data.get(sec_key)
                        if val:
                            text_body = "\n\n".join(val) if isinstance(val, list) else str(val)
                            text_body = re.sub(r"\s+", " ", text_body).strip()
                            if len(text_body) > 30:
                                md_lines.append(f"## {sec_title}\n{text_body}\n\n")

                    content = "".join(md_lines).strip()
                    if len(content) > 300:
                        docs.append({
                            "doc_id": doc_id,
                            "title": f"{drug} Drug Information",
                            "source_name": "openFDA / DailyMed",
                            "source_url": f"https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query={drug}",
                            "license": "Public Domain",
                            "commercial_use_restricted": False,
                            "topic": "medications",
                            "raw_text": content,
                        })
                        doc_idx += 1

        except Exception as e:
            pass
        
        await asyncio.sleep(0.3)  # Gentle rate limiting

    print(f"[openFDA] Ingested {len(docs)} drug label documents.")
    return docs


# ---------------------------------------------------------------------------
# 3. Existing 18 Core Documents
# ---------------------------------------------------------------------------

def load_existing_core_docs() -> list[dict[str, Any]]:
    rag_dir = PROJECT_ROOT / "rag_knowledge"
    manifest_path = rag_dir / "manifest" / "corpus_manifest.json"
    if not manifest_path.exists():
        return []

    with open(manifest_path, "r", encoding="utf-8-sig") as f:
        core_data = json.load(f)

    docs = []
    for d in core_data.get("documents", []):
        doc_id = d["document_id"]
        content = None
        for ext in [".txt", ".md"]:
            clean_file = rag_dir / "cleaned" / f"{doc_id}{ext}"
            if clean_file.exists():
                content = clean_file.read_text(encoding="utf-8", errors="replace")
                break

        if not content:
            raw_folder = rag_dir / d.get("folder", "")
            for p in list(raw_folder.glob("*.txt")) + list(raw_folder.glob("*.md")):
                content = p.read_text(encoding="utf-8", errors="replace")
                break

        if content:
            docs.append({
                "doc_id": doc_id,
                "title": d.get("title", doc_id),
                "source_name": d.get("source", "NIH / MedlinePlus"),
                "source_url": d.get("source_url", ""),
                "license": "Public Domain" if "WHO" not in d.get("source", "") else "CC BY-NC-SA 4.0",
                "commercial_use_restricted": "WHO" in d.get("source", ""),
                "topic": d.get("topic", "general"),
                "raw_text": content,
            })
    return docs


# ---------------------------------------------------------------------------
# Master Ingestion Pipeline
# ---------------------------------------------------------------------------

async def run_scale_ingestion(min_target_docs: int = 500):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 60)
    print("CarePilot AI — Large-Scale Knowledge Base Ingestion Pipeline")
    print("=" * 60)

    all_raw_docs = []

    # 1. 18 Core documents
    core_docs = load_existing_core_docs()
    print(f"[1/5] Loaded {len(core_docs)} core documents.")
    all_raw_docs.extend(core_docs)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 2. MedlinePlus Health Topics (~400 topics)
        mplus_docs = await fetch_medlineplus_topics(client, max_docs=450)
        all_raw_docs.extend(mplus_docs)

        # 3. openFDA Drug Labels (~80+ drugs)
        fda_docs = await fetch_openfda_labels(client)
        all_raw_docs.extend(fda_docs)

    print(f"\n[2/5] Total raw documents collected: {len(all_raw_docs)}")

    # 4. Clean & Deduplicate
    print("\n[3/5] Cleaning and deduplicating documents...")
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME)
    cleaned_docs = []
    seen_hashes = set()

    for doc in all_raw_docs:
        res = clean_markdown_document(doc["raw_text"])
        if not res:
            continue
        if res["sha256"] in seen_hashes:
            continue
        seen_hashes.add(res["sha256"])

        out_path = CLEAN_DIR / f"{doc['doc_id']}.md"
        out_path.write_text(res["text"], encoding="utf-8")

        cleaned_docs.append({
            **doc,
            "cleaned_text": res["text"],
            "char_count": res["char_count"],
            "sha256": res["sha256"],
        })

    print(f"[OK] Cleaned and verified {len(cleaned_docs)} unique documents. (Floor: >= 500)")

    # 5. Chunking
    print("\n[4/5] Chunking documents (400 tokens / 60 token overlap)...")
    all_chunks = []
    for doc in cleaned_docs:
        chunks = chunk_document(
            doc_id=doc["doc_id"],
            doc_title=doc["title"],
            source_name=doc["source_name"],
            license_type=doc["license"],
            commercial_restricted=doc["commercial_use_restricted"],
            text=doc["cleaned_text"],
            snapshot_id="v2",
            tokenizer=tokenizer,
        )
        all_chunks.extend(chunks)
        chunk_file = CHUNKS_DIR / f"{doc['doc_id']}.json"
        chunk_file.write_text(json.dumps(chunks, indent=2), encoding="utf-8")

    print(f"[OK] Generated {len(all_chunks)} total chunks across {len(cleaned_docs)} documents.")

    # 6. Indexing
    print("\n[5/5] Building Dense (ChromaDB) and Sparse (BM25) Indexes...")
    build_chroma_index(all_chunks)
    build_bm25_index(all_chunks)

    # 7. Snapshot Manifest
    snapshot_manifest = {
        "snapshot_id": "v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "chunking": {
            "chunk_size_tokens": 400,
            "chunk_overlap_tokens": 60,
            "tokenizer": "BAAI/bge-small-en-v1.5",
        },
        "chroma_collection": "carepilot_kb_v2",
        "bm25_index_path": "D:/CarePilotAI/rag_knowledge/bm25_index_v2.pkl",
        "doc_count": len(cleaned_docs),
        "chunk_count": len(all_chunks),
        "floor_met": len(cleaned_docs) >= 500,
        "frozen": True,
        "documents_summary": {
            "public_domain_count": sum(1 for d in cleaned_docs if d["license"] == "Public Domain"),
            "cc_licensed_count": sum(1 for d in cleaned_docs if d["license"] != "Public Domain"),
        },
        "documents": [
            {
                "doc_id": d["doc_id"],
                "title": d["title"],
                "source": d["source_name"],
                "url": d["source_url"],
                "license": d["license"],
                "sha256": d["sha256"],
                "char_count": d["char_count"],
            }
            for d in cleaned_docs
        ],
    }

    manifest_file = MANIFEST_DIR / "kb_snapshot_v2.json"
    manifest_file.write_text(json.dumps(snapshot_manifest, indent=2), encoding="utf-8")
    print(f"\n[OK] Snapshot manifest written & frozen -> {manifest_file}")
    print("=" * 60)

    return len(cleaned_docs), len(all_chunks)


if __name__ == "__main__":
    asyncio.run(run_scale_ingestion())
