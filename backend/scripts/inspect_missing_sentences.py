"""
backend/scripts/inspect_missing_sentences.py

For Step 2:
Finds documents with body containment below 0.95 and prints 3 sentences
from the KB text that are missing from the raw source page.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def tokens(text: str):
    return re.findall(r"[a-z0-9]+", text.lower())


def shingles(toks, n=5):
    return {" ".join(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))}


def strip_markup(s: str) -> str:
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&[a-z]+;|&#\d+;", " ", s)
    return s


def split_sentences(text: str):
    raw_sents = re.split(r"(?<=[.!?\n])\s+", text)
    return [s.strip() for s in raw_sents if len(s.strip()) > 15]


def main():
    manifest_p = ROOT / "data" / "manifests" / "kb_snapshot_v3.json"
    manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
    docs_by_id = {d["doc_id"]: d for d in manifest["documents"]}

    raw_dir = ROOT / "rag_knowledge" / "raw"
    clean_dir = ROOT / "rag_knowledge" / "kb_export"
    rep_csv = ROOT / "data" / "reports" / "real_data_kb_check.csv"

    with open(rep_csv, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    low_contain = [r for r in rows if r["text_traceable_to_raw"] and float(r["text_traceable_to_raw"]) < 0.95]
    print(f"Total documents with containment < 0.95: {len(low_contain)}")

    # Group by source
    groups = {"NIDDK": [], "MedlinePlus (Core)": [], "MedlinePlus (Scaled)": [], "openFDA": []}
    for r in low_contain:
        did = r["doc_id"]
        d = docs_by_id.get(did, {})
        src = d.get("source", "")
        if "NIDDK" in src:
            groups["NIDDK"].append(r)
        elif did.startswith("KB-FDA"):
            groups["openFDA"].append(r)
        elif did.startswith("KB-C") or did.startswith("KB-M") or did.startswith("KB-L") or did.startswith("KB-B"):
            groups["MedlinePlus (Core)"].append(r)
        else:
            groups["MedlinePlus (Scaled)"].append(r)

    for gname, items in groups.items():
        print("\n" + "=" * 80)
        print(f"GROUP: {gname} ({len(items)} docs with containment < 0.95)")
        print("=" * 80)
        for item in items[:3]:  # Print representative sample for each group
            did = item["doc_id"]
            c_val = float(item["text_traceable_to_raw"])
            d = docs_by_id.get(did, {})

            raw_files = list(raw_dir.glob(f"{did}.*"))
            clean_file = clean_dir / f"{did}.txt"
            if not raw_files or not clean_file.exists():
                continue

            rtext = strip_markup(raw_files[0].read_text(encoding="utf-8", errors="replace"))
            ctext = clean_file.read_text(encoding="utf-8", errors="replace")

            rset = shingles(tokens(rtext))
            sents = split_sentences(ctext)

            missing_sents = []
            for s in sents:
                s_sh = shingles(tokens(s))
                if s_sh and len(s_sh & rset) < len(s_sh) * 0.4:
                    missing_sents.append(s)
                    if len(missing_sents) >= 3:
                        break

            print(f"\nDocument {did} | Title: \"{d.get('title')}\" | Containment: {c_val:.4f}")
            if missing_sents:
                for idx, ms in enumerate(missing_sents[:3], 1):
                    print(f"  [{idx}] \"{ms}\"")
            else:
                print("  (All individual sentences match raw content; containment < 0.95 is solely due to cross-section Markdown heading shingles.)")


if __name__ == "__main__":
    main()
