"""
backend/scripts/inspect_kb_duplicates.py

Inspects:
1. Duplicate title groups with their URLs and content differences.
2. Fetch status for the 18 core documents.
3. Provenance and URLs for openFDA and MedlinePlus.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "manifests" / "kb_snapshot_v2.json"
FETCH_REPORT = ROOT / "data" / "manifests" / "kb_raw_fetch_report.json"


def main():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    fetch_rep = json.loads(FETCH_REPORT.read_text(encoding="utf-8")) if FETCH_REPORT.exists() else {}
    fetch_map = {d["doc_id"]: d for d in fetch_rep.get("documents", [])}

    docs = m.get("documents", [])
    print(f"Total documents in manifest: {len(docs)}")

    # 1. Duplicate title groups
    print("\n" + "=" * 80)
    print("1. DUPLICATE TITLE GROUPS (4 GROUPS)")
    print("=" * 80)
    by_title = collections.defaultdict(list)
    for d in docs:
        t = d["title"].strip().lower()
        by_title[t].append(d)

    dup_count = 0
    for t, group in by_title.items():
        if len(group) > 1:
            dup_count += 1
            print(f"\nGroup {dup_count}: '{group[0]['title']}' ({len(group)} docs)")
            for d in group:
                print(f"  - doc_id: {d['doc_id']:12s} | source: {d.get('source', ''):20s} | url: {d.get('url', '')}")

    # 2. 18 Core Docs Fetch Status
    print("\n" + "=" * 80)
    print("2. 18 CORE DOCUMENTS FETCH STATUS")
    print("=" * 80)
    core_ids = [
        "KB-D01", "KB-D02", "KB-D03", "KB-D04",
        "KB-K01", "KB-K02", "KB-K03", "KB-K04",
        "KB-C01", "KB-C02", "KB-C03",
        "KB-L01",
        "KB-B01", "KB-B02", "KB-B03", "KB-B04",
        "KB-M01", "KB-M02", "KB-M03", "KB-M04",
    ]
    core_docs = [d for d in docs if d["doc_id"] in core_ids]
    print(f"Found {len(core_docs)} core documents:")
    for d in core_docs:
        did = d["doc_id"]
        f_info = fetch_map.get(did, {})
        status = f_info.get("http_status", "not_checked")
        verified = f_info.get("verified", False)
        sha = f_info.get("sha256_raw", "")
        sha_str = sha[:12] + "..." if sha else "none"
        print(f"  {did:10s} | HTTP {str(status):3s} | verified={str(verified):5s} | sha_raw={sha_str:15s} | {d['title']:35s} | {d.get('url')}")


if __name__ == "__main__":
    main()
