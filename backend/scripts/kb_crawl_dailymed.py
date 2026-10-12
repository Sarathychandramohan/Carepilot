"""
D:\\CarePilotAI\\backend\\scripts\\kb_crawl_dailymed.py

Fetches drug labels from DailyMed openFDA API for key medications
present in the CarePilot patient population.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_KB_DIR = PROJECT_ROOT / "data" / "kb_raw"

CORE_DRUGS = [
    "Metformin",
    "Lisinopril",
    "Furosemide",
    "Atorvastatin",
    "Amlodipine",
    "Losartan",
    "Insulin Glargine",
    "Empagliflozin",
    "Albuterol",
    "Omeprazole",
    "Hydrochlorothiazide",
    "Simvastatin",
    "Levothyroxine",
    "Metoprolol",
    "Gabapentin",
]

OPENFDA_URL = "https://api.fda.gov/drug/label.json"


async def fetch_drug_label(client: httpx.AsyncClient, drug_name: str) -> dict[str, Any] | None:
    """Fetches drug label sections from openFDA API."""
    params = {
        "search": f'openfda.generic_name:"{drug_name}" OR openfda.brand_name:"{drug_name}"',
        "limit": 1,
    }
    try:
        resp = await client.get(OPENFDA_URL, params=params, timeout=15.0)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            if results:
                return results[0]
    except Exception as e:
        print(f"  [DailyMed] Failed to fetch {drug_name}: {e}")
    return None


def format_drug_label_markdown(drug_name: str, label_data: dict[str, Any]) -> str:
    """Converts structured openFDA label JSON into clean markdown."""
    md_lines = [f"# {drug_name} — Clinical Drug Information\n"]
    md_lines.append(f"**Source:** openFDA / DailyMed (US National Library of Medicine)\n")
    md_lines.append(f"**License:** Public Domain (US Government Work)\n\n")

    sections_to_extract = [
        ("indications_and_usage", "Indications and Usage"),
        ("dosage_and_administration", "Dosage and Administration"),
        ("contraindications", "Contraindications"),
        ("warnings_and_cautions", "Warnings and Precautions"),
        ("adverse_reactions", "Adverse Reactions and Side Effects"),
        ("drug_interactions", "Drug Interactions"),
        ("description", "Description and Mechanism"),
    ]

    for key, title in sections_to_extract:
        val = label_data.get(key)
        if val:
            if isinstance(val, list):
                text = "\n\n".join(val)
            else:
                text = str(val)
            # Remove extreme whitespace
            text = re.sub(r"\s+", " ", text).strip()
            md_lines.append(f"## {title}\n")
            md_lines.append(f"{text}\n\n")

    return "".join(md_lines).strip()


async def crawl_dailymed(output_dir: Path = RAW_KB_DIR) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries = []

    print(f"\n[DailyMed] Ingesting drug labels for {len(CORE_DRUGS)} medications...")
    async with httpx.AsyncClient() as client:
        doc_idx = 100
        for drug in CORE_DRUGS:
            doc_id = f"KB-M{doc_idx:03d}"
            print(f"  Fetching: {drug} -> {doc_id}")
            label = await fetch_drug_label(client, drug)
            if label:
                md_content = format_drug_label_markdown(drug, label)
                out_path = output_dir / f"{doc_id}.md"
                out_path.write_text(md_content, encoding="utf-8")

                manifest_entries.append({
                    "doc_id": doc_id,
                    "title": f"{drug} Drug Information",
                    "source_name": "DailyMed / openFDA",
                    "source_url": f"https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query={drug}",
                    "license": "Public Domain",
                    "commercial_use_restricted": False,
                    "topic": "medications",
                    "file_path": str(out_path),
                })
                doc_idx += 1
            await asyncio.sleep(1.0)  # Rate limiting

    print(f"[DailyMed] Ingested {len(manifest_entries)} drug documents.")
    return manifest_entries


if __name__ == "__main__":
    asyncio.run(crawl_dailymed())
