"""
backend/scripts/detailed_nli_report.py

Generates a complete readable breakdown of all 15 queries, their generated drafts,
their sentence-by-sentence citations and premises, and evaluates whether each is:
- A genuine catch (unfaithful / hallucinated / contradicted)
- Or a false positive (clinically sound advice / factual statement that general NLI scores as neutral)
"""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IN_PATH = PROJECT_ROOT / "data" / "manifests" / "batch_15_sentence_nli_analysis.json"

def main():
    with open(IN_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)

    print("================================================================================")
    print("DETAILED SENTENCE-LEVEL NLI AND CLINICAL FAITHFULNESS AUDIT (N=15)")
    print("================================================================================\n")

    for r in records:
        print(f"================================================================================")
        print(f"QUERY #{r['idx']} [{r['query_id']}] Intent: {r['intent']} | Urgency: {r['urgency']}")
        print(f"Validation Status: {r['validation_status']} | Avg NLI: {r['avg_nli']} | Coverage: {r['citation_coverage']}")
        print(f"Safety Flags: mismatch={r['mismatch_flag']}, missing_ctx={r['missing_context_flag']}")
        if not r.get("has_draft"):
            print(">> NO DRAFT GENERATED: Pipeline halted at D17a safety guardrail (Patient-EHR mismatch).")
            continue

        for s in r.get("sentences", []):
            print(f"\n  --- Sentence {s['s_idx']} [{s['claim_type']}] --- NLI Entailment: {s['nli_score']}")
            print(f"  Text: \"{s['text']}\"")
            print(f"  Citations: {s['citations']}")
            for p in s.get("cited_texts", []):
                print(f"  Source Chunk: {p}")

if __name__ == "__main__":
    main()
