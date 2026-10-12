"""
backend/scripts/kb_build_v3.py

CarePilot v3 Knowledge Base Builder & Snapshot v3 Generator.

Actions:
1. Preserves 18 core documents (from raw/cleaned sources).
2. Preserves MedlinePlus health topics, excluding exact duplicates (KB-MP0055, KB-MP0059, KB-MP0080).
3. Rebuilds openFDA drug label corpus:
   - Queries api.fda.gov for 105 active ingredients.
   - Saves full raw JSON response to rag_knowledge/raw/KB-FDA{index:04d}.json.
   - Records request URL, set_id, effective_time, HTTP status, and SHA-256 at ingest time.
   - Cleans deterministically into standard Markdown drug label format.
4. Chunks all documents using stable tokenizer (400 tokens, 60 overlap).
5. Builds ChromaDB collection: carepilot_kb_v3 (preserves v2 untouched).
6. Builds BM25 sparse index: rag_knowledge/bm25_index_v3.pkl.
7. Exports chunk text to rag_knowledge/kb_export/{doc_id}.txt.
8. Writes frozen manifest: data/manifests/kb_snapshot_v3.json.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import chromadb
import httpx
from bs4 import BeautifulSoup
from transformers import AutoTokenizer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.scripts.kb_chunk import chunk_document, TOKENIZER_NAME
from backend.scripts.kb_build_index import build_chroma_index
from backend.scripts.kb_build_bm25 import build_bm25_index

RAW_DIR = PROJECT_ROOT / "rag_knowledge" / "raw"
EXPORT_DIR = PROJECT_ROOT / "rag_knowledge" / "kb_export"
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"
CHROMA_DIR = PROJECT_ROOT / "rag_knowledge" / "chroma_db"

DUPLICATES_TO_REMOVE = {"KB-MP0055", "KB-MP0059", "KB-MP0080"}

# 105 expanded drugs (unique active ingredients)
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

OPENFDA_API_BASE = "https://api.fda.gov/drug/label.json"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


async def fetch_openfda_labels(client: httpx.AsyncClient) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    print(f"\n[openFDA] Ingesting drug labels for {len(EXPANDED_DRUGS)} active ingredients from api.fda.gov...")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    docs = []
    meta_records = {}
    doc_idx = 1
    
    # Selection rule:
    # 1. Exact match on openfda.generic_name or brand_name or substance_name
    # 2. Limit 1 result (first FDA-approved label)
    # 3. Save raw JSON to disk immediately at ingest time
    for drug in EXPANDED_DRUGS:
        q_exact = f'openfda.generic_name.exact:"{drug}" OR openfda.brand_name.exact:"{drug}" OR openfda.substance_name.exact:"{drug}"'
        query_url = f"{OPENFDA_API_BASE}?search={quote_plus(q_exact)}&limit=1"
        
        doc_id = f"KB-FDA{doc_idx:04d}"
        raw_file_path = RAW_DIR / f"{doc_id}.json"
        
        try:
            if raw_file_path.exists():
                raw_bytes = raw_file_path.read_bytes()
                data = json.loads(raw_bytes)
                results = data.get("results", [])
                resp_status = 200
            else:
                resp = await client.get(query_url, timeout=15.0)
                if resp.status_code != 200:
                    q_broad = f'openfda.generic_name:"{drug}" OR openfda.brand_name:"{drug}"'
                    query_url = f"{OPENFDA_API_BASE}?search={quote_plus(q_broad)}&limit=1"
                    resp = await client.get(query_url, timeout=15.0)
                    if resp.status_code != 200 and "-" in drug:
                        d_split = drug.split("-")[0]
                        q_split = f'openfda.generic_name:"{d_split}"'
                        query_url = f"{OPENFDA_API_BASE}?search={quote_plus(q_split)}&limit=1"
                        resp = await client.get(query_url, timeout=15.0)
                resp_status = resp.status_code
                if resp_status == 200:
                    raw_bytes = resp.content
                    raw_file_path.write_bytes(raw_bytes)
                    data = resp.json()
                    results = data.get("results", [])
                else:
                    results = []
                
            if resp_status == 200 and results:
                raw_sha = sha256_bytes(raw_bytes)
                label = results[0]
                set_id = label.get("set_id") or label.get("id") or "unknown_set_id"
                effective_time = label.get("effective_time") or "unknown_time"
                
                # Deterministic markdown extraction
                md_lines = [
                    f"# {drug} — Prescription Drug Label Information\n",
                    f"**Source:** openFDA / DailyMed (US National Library of Medicine & FDA)\n",
                    f"**URL:** {query_url}\n",
                    f"**Set ID:** {set_id}\n",
                    f"**Effective Time:** {effective_time}\n",
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
                    val = label.get(sec_key)
                    if val:
                        body = "\n\n".join(val) if isinstance(val, list) else str(val)
                        body = re.sub(r"\s+", " ", body).strip()
                        if len(body) > 30:
                            md_lines.append(f"## {sec_title}\n{body}\n\n")
                            
                cleaned_content = "".join(md_lines).strip()
                if len(cleaned_content) > 300:
                    doc_record = {
                        "doc_id": doc_id,
                        "title": f"{drug} Drug Information",
                        "source_name": "openFDA / DailyMed",
                        "source_url": query_url,
                        "license": "Public Domain",
                        "commercial_use_restricted": False,
                        "topic": "medications",
                        "raw_text": cleaned_content,
                        "char_count": len(cleaned_content),
                        "sha256": sha256_text(cleaned_content),
                        "raw_sha256": raw_sha,
                        "set_id": set_id,
                        "effective_time": effective_time,
                    }
                    docs.append(doc_record)
                    meta_records[doc_id] = {
                        "drug": drug,
                        "request_url": query_url,
                        "set_id": set_id,
                        "effective_time": effective_time,
                        "http_status": resp_status,
                        "raw_sha256": raw_sha,
                        "clean_sha256": doc_record["sha256"],
                    }
                    print(f"  [{doc_idx:3d}/105] {doc_id} {drug:25s} set_id={set_id[:8]}... raw_len={len(raw_bytes):,}B")
                    doc_idx += 1
            else:
                print(f"  [WARN] Failed to fetch {drug}: HTTP {resp.status_code}")
        except Exception as e:
            print(f"  [ERROR] Exception on {drug}: {e}")
            
        await asyncio.sleep(0.25)
        
    print(f"[openFDA] Successfully ingested {len(docs)} drug label documents.")
    return docs, meta_records


def build_v3_corpus():
    print("=" * 80)
    print("Building CarePilot Knowledge Base Snapshot v3")
    print("=" * 80)

    # 1. Load previous manifest to get 18 core docs and MedlinePlus topics
    v2_manifest_path = MANIFEST_DIR / "kb_snapshot_v2.json"
    v2_data = json.loads(v2_manifest_path.read_text(encoding="utf-8"))
    v2_docs = v2_data.get("documents", [])

    # Filter out duplicate URLs
    medline_and_core_docs = []
    removed_docs = []
    for d in v2_docs:
        did = d["doc_id"]
        if did in DUPLICATES_TO_REMOVE:
            removed_docs.append(d)
            continue
        if d.get("source") == "openFDA / DailyMed" or did.startswith("KB-FDA"):
            continue  # Will be replaced with rebuilt openFDA
        # Load cleaned text from kb_export or raw
        exp_file = EXPORT_DIR / f"{did}.txt"
        if exp_file.exists():
            text = exp_file.read_text(encoding="utf-8").strip()
            medline_and_core_docs.append({
                "doc_id": did,
                "title": d["title"],
                "source_name": d.get("source", "MedlinePlus"),
                "source_url": d["url"],
                "license": d["license"],
                "commercial_use_restricted": False,
                "topic": "health_topics",
                "raw_text": text,
                "char_count": len(text),
                "sha256": sha256_text(text),
            })

    print(f"[Core & MedlinePlus] Retained {len(medline_and_core_docs)} docs (Removed {len(removed_docs)} duplicate docs: {[d['doc_id'] for d in removed_docs]})")

    # 2. Fetch new openFDA labels asynchronously
    async def _fetch():
        async with httpx.AsyncClient(headers={"User-Agent": "CarePilotAI/1.0 (academic provenance)"}) as client:
            return await fetch_openfda_labels(client)

    openfda_docs, openfda_meta = asyncio.run(_fetch())

    # Combine all documents
    all_documents = medline_and_core_docs + openfda_docs
    print(f"\n[Total Corpus] {len(all_documents)} documents ({len(medline_and_core_docs)} Medline/Core + {len(openfda_docs)} openFDA)")

    # 3. Chunk documents
    print("\n[Chunking] Chunking all documents with BGE tokenizer (400 tokens, 60 overlap)...")
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME)
    all_chunks = []
    for doc in all_documents:
        chunks = chunk_document(
            doc_id=doc["doc_id"],
            doc_title=doc["title"],
            source_name=doc["source_name"],
            license_type=doc["license"],
            commercial_restricted=doc.get("commercial_use_restricted", False),
            text=doc["raw_text"],
            snapshot_id="v3",
            tokenizer=tokenizer,
        )
        all_chunks.extend(chunks)

    print(f"[Chunking] Generated {len(all_chunks)} total chunks.")

    # 4. Build ChromaDB collection: carepilot_kb_v3
    print("\n[ChromaDB] Indexing into collection 'carepilot_kb_v3'...")
    build_chroma_index(all_chunks, collection_name="carepilot_kb_v3", chroma_dir=CHROMA_DIR)

    # 5. Build BM25 index: bm25_index_v3.pkl
    bm25_v3_path = PROJECT_ROOT / "rag_knowledge" / "bm25_index_v3.pkl"
    print(f"\n[BM25] Building sparse BM25 index -> {bm25_v3_path}...")
    build_bm25_index(all_chunks, output_path=bm25_v3_path)

    # 6. Export chunk text to kb_export
    print("\n[Export] Exporting clean chunk text to rag_knowledge/kb_export/...")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Group chunks by doc_id
    from collections import defaultdict
    chunks_by_doc = defaultdict(list)
    for c in all_chunks:
        chunks_by_doc[c["doc_id"]].append(c)

    for did, doc_chunks in chunks_by_doc.items():
        doc_chunks.sort(key=lambda x: x["chunk_id"])
        text_joined = "\n\n".join(c["text"].strip() for c in doc_chunks if c["text"].strip())
        (EXPORT_DIR / f"{did}.txt").write_text(text_joined.strip() + "\n", encoding="utf-8")

    # 7. Write Manifest v3
    manifest_v3 = {
        "snapshot_id": "v3",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "chroma_collection": "carepilot_kb_v3",
        "bm25_index_path": str(bm25_v3_path.relative_to(PROJECT_ROOT)),
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "tokenizer": TOKENIZER_NAME,
        "doc_count": len(all_documents),
        "chunk_count": len(all_chunks),
        "removed_documents": [
            {"doc_id": d["doc_id"], "title": d["title"], "url": d["url"], "reason": "Exact URL duplicate"}
            for d in removed_docs
        ],
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
            for d in all_documents
        ],
    }

    manifest_v3_path = MANIFEST_DIR / "kb_snapshot_v3.json"
    manifest_v3_path.write_text(json.dumps(manifest_v3, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[Manifest] Wrote snapshot v3 manifest -> {manifest_v3_path}")

    # Save openFDA provenance metadata report
    fda_report_path = MANIFEST_DIR / "openfda_ingest_provenance.json"
    fda_report_path.write_text(json.dumps({
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "total_active_ingredients": len(EXPANDED_DRUGS),
        "ingested_count": len(openfda_docs),
        "documents": openfda_meta,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[Provenance] Wrote openFDA ingestion provenance -> {fda_report_path}")

    print("\n[OK] Snapshot v3 build complete.")


if __name__ == "__main__":
    build_v3_corpus()
