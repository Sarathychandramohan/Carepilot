"""
backend/scripts/map_openfda_ids.py

Step 5:
1. Maps old v2 openFDA document IDs to new v3 document IDs by drug name.
2. Audits all query files (gold, silver, relevance, pooled, RQ3).
3. Updates any references pointing to old IDs and archives previous files.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    # Load v2 snapshot
    v2_manifest_p = ROOT / "data" / "manifests" / "kb_snapshot_v2.json"
    v2_data = json.loads(v2_manifest_p.read_text(encoding="utf-8"))
    v2_fda = {
        d["doc_id"]: d["title"].replace(" Drug Information", "").strip()
        for d in v2_data["documents"]
        if d["doc_id"].startswith("KB-FDA")
    }

    # Load v3 snapshot
    v3_manifest_p = ROOT / "data" / "manifests" / "kb_snapshot_v3.json"
    v3_data = json.loads(v3_manifest_p.read_text(encoding="utf-8"))
    v3_fda = {
        d["doc_id"]: d["title"].replace(" Drug Information", "").strip()
        for d in v3_data["documents"]
        if d["doc_id"].startswith("KB-FDA")
    }

    # Drug -> ID
    drug_to_v2 = {drug.lower(): did for did, drug in v2_fda.items()}
    drug_to_v3 = {drug.lower(): did for did, drug in v3_fda.items()}

    # Old to new mapping
    old_to_new = {}
    for did_v2, drug in v2_fda.items():
        d_norm = drug.lower()
        did_v3 = drug_to_v3.get(d_norm)
        old_to_new[did_v2] = {
            "drug": drug,
            "old_id_v2": did_v2,
            "new_id_v3": did_v3,
            "same_id": did_v2 == did_v3,
        }

    print(f"Total v2 openFDA docs: {len(v2_fda)}")
    print(f"Total v3 openFDA docs: {len(v3_fda)}")
    diff_ids = [v for v in old_to_new.values() if not v["same_id"]]
    print(f"Drugs whose doc_id changed: {len(diff_ids)}")
    for d in diff_ids[:15]:
        print(f"  {d['drug']:25s} | v2: {d['old_id_v2']} -> v3: {d['new_id_v3']}")

    # Search query files
    q_dir = ROOT / "data" / "queries"
    archive_q_dir = ROOT / "data" / "queries" / "archive"
    archive_q_dir.mkdir(parents=True, exist_ok=True)

    query_files = sorted(list(q_dir.glob("*.jsonl")) + list(q_dir.glob("*.csv")))
    print("\n=== Query File Audit for KB-FDA IDs ===")

    for qf in query_files:
        content = qf.read_text(encoding="utf-8", errors="replace")
        fda_matches = re.findall(r"KB-FDA\d{4}", content)
        unique_matches = sorted(set(fda_matches))
        print(f"{qf.name:35s}: {len(fda_matches):4d} total FDA references ({len(unique_matches)} unique IDs)")

        if unique_matches:
            replaced_content = content
            replacements = 0
            for old_id in unique_matches:
                info = old_to_new.get(old_id)
                if info and info["new_id_v3"] and info["new_id_v3"] != old_id:
                    new_id = info["new_id_v3"]
                    replaced_content, count = re.subn(rf"\b{old_id}\b", new_id, replaced_content)
                    replacements += count
                    print(f"  - In {qf.name}: replaced {old_id} ({info['drug']}) -> {new_id} ({count} occurrences)")

            if replacements > 0:
                shutil.copy2(qf, archive_q_dir / f"{qf.stem}_pre_fda_remap{qf.suffix}")
                qf.write_text(replaced_content, encoding="utf-8")
                print(f"  -> Updated {qf.name} with {replacements} ID fixes.")

    # Save full mapping manifest
    mapping_report_p = ROOT / "data" / "manifests" / "openfda_v2_to_v3_id_mapping.json"
    mapping_report_p.write_text(json.dumps(old_to_new, indent=2), encoding="utf-8")
    print(f"\nWrote old-to-new mapping report -> {mapping_report_p}")


if __name__ == "__main__":
    main()
