"""
backend/scripts/audit_3class_nli.py

Computes all 3 probabilities (contradiction, entailment, neutral) for:
1. The adversarial smoke test sentence
2. All sentences across the 15 batch queries
"""
from __future__ import annotations

import json
from pathlib import Path
from sentence_transformers import CrossEncoder

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IN_PATH = PROJECT_ROOT / "data" / "manifests" / "batch_15_sentence_nli_analysis.json"

def main():
    m = CrossEncoder("cross-encoder/nli-deberta-v3-small", local_files_only=True)

    print("=== ADVERSARIAL CASE AUDIT ===")
    adv_premise = "Amoxicillin is a penicillin-class antibacterial indicated for bacterial infections. Not indicated for viral infections."
    adv_hypo = "Amoxicillin is an over-the-counter vitamin that cures all viral infections instantly at 5,000 mg hourly."
    adv_probs = m.predict([(adv_premise, adv_hypo)], apply_softmax=True)[0]
    print(f"Adv Probs -> Contra: {adv_probs[0]:.4f} | Entail: {adv_probs[1]:.4f} | Neutral: {adv_probs[2]:.4f}")

    print("\n=== BATCH 15 SENTENCES AUDIT ===")
    with open(IN_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)

    for r in records:
        if not r.get("has_draft"):
            continue
        print(f"\nQUERY #{r['idx']} [{r['query_id']}] Intent: {r['intent']}")
        for s in r.get("sentences", []):
            stext = s["text"]
            for ct in s.get("cited_texts", []):
                # Clean prefix [chunk_id]
                premise = ct.split("] ", 1)[-1] if "] " in ct else ct
                if len(premise) > 10 and "not in top" not in premise:
                    probs = m.predict([(premise, stext)], apply_softmax=True)[0]
                    print(f"  S{s['s_idx']} [{s['claim_type']}]: contra={probs[0]:.4f}, entail={probs[1]:.4f}, neutral={probs[2]:.4f}")
                    print(f"      Hypo: \"{stext[:80]}...\"")
                    break

if __name__ == "__main__":
    main()
