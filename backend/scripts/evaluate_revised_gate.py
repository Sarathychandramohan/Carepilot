"""
backend/scripts/evaluate_revised_gate.py

Evaluates revised validation gate logic on the N=15 batch:
Option A: Pure scalar threshold reduction (e.g. tau_warn = 0.005, tau_pass = 0.10)
Option B: Tiered claim-type validation with Contradiction Ceiling:
   - Contradiction check: Any sentence with P(contradiction) > 0.05 -> manual_required (catches adversarial, hallucinations, inversions)
   - Patient Fact: P(entailment) >= 0.01 or non-contradiction
   - Citation Coverage: >= 0.80
"""
from __future__ import annotations

import json
from pathlib import Path
from sentence_transformers import CrossEncoder

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IN_PATH = PROJECT_ROOT / "data" / "manifests" / "batch_15_sentence_nli_analysis.json"

def main():
    m = CrossEncoder("cross-encoder/nli-deberta-v3-small", local_files_only=True)
    with open(IN_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)

    print("================================================================================")
    print("EVALUATING REVISED VALIDATION GATES ON N=15 BATCH")
    print("================================================================================")

    # Let's test Option A: Tuning scalar threshold
    print("\n--- OPTION A: Scalar Threshold Tuning ---")
    for twarn in [0.30, 0.15, 0.05, 0.01, 0.005, 0.002]:
        statuses = []
        for r in records:
            if not r.get("has_draft"):
                statuses.append("manual_required (safety guardrail)")
                continue
            scores = [s["nli_score"] for s in r.get("sentences", []) if s.get("nli_score") is not None]
            avg_nli = sum(scores) / len(scores) if scores else 0.0
            cov = r.get("citation_coverage", 1.0) or 0.0

            if cov < 0.80 or avg_nli < twarn:
                statuses.append("manual_required")
            elif avg_nli < 0.50:
                statuses.append("passed_with_warning")
            else:
                statuses.append("passed")

        from collections import Counter
        c = Counter(statuses)
        print(f"tau_warn={twarn:.3f}: manual_req={c.get('manual_required',0)+c.get('manual_required (safety guardrail)',0)} (safety={c.get('manual_required (safety guardrail)',0)}), warn={c.get('passed_with_warning',0)}, pass={c.get('passed',0)}")

    # Let's test Option B: Tiered Threshold + Contradiction Intercept
    print("\n--- OPTION B: Tiered Claim-Type + Contradiction Intercept Gate ---")
    # Rule:
    # 1. Any sentence with P(contra) >= 0.05 -> manual_required (immediate safety interception)
    # 2. Citation coverage >= 0.80
    # 3. For patient_fact: P(contra) < 0.02
    # 4. Status determination:
    #    - If any sentence has contra >= 0.05 -> manual_required
    #    - If avg_nli >= 0.15 -> passed
    #    - If avg_nli >= 0.002 and contra < 0.05 -> passed_with_warning
    #    - Else -> manual_required

    opt_b_results = []
    for r in records:
        qid = r["query_id"]
        if not r.get("has_draft"):
            opt_b_results.append((qid, "manual_required", "D17a Patient-EHR Mismatch (no draft)"))
            continue

        cov = r.get("citation_coverage", 1.0) or 0.0
        if cov < 0.80:
            opt_b_results.append((qid, "manual_required", f"Citation coverage {cov:.2f} < 0.80"))
            continue

        # Check sentence contra and entailment
        has_high_contra = False
        contra_reasons = []
        scores = []

        for s in r.get("sentences", []):
            stext = s["text"]
            scores.append(s.get("nli_score", 0.0))
            for ct in s.get("cited_texts", []):
                premise = ct.split("] ", 1)[-1] if "] " in ct else ct
                if len(premise) > 10 and "not in top" not in premise:
                    probs = m.predict([(premise, stext)], apply_softmax=True)[0]
                    p_contra = probs[0]
                    p_entail = probs[1]
                    if p_contra >= 0.05:
                        has_high_contra = True
                        contra_reasons.append(f"S{s['s_idx']} contra={p_contra:.3f}: '{stext[:50]}...'")
                    break

        avg_nli = sum(scores) / len(scores) if scores else 0.0

        if has_high_contra:
            opt_b_results.append((qid, "manual_required", f"High Contradiction: {'; '.join(contra_reasons)}"))
        elif avg_nli >= 0.15:
            opt_b_results.append((qid, "passed", f"High entailment avg_nli={avg_nli:.4f}"))
        elif avg_nli >= 0.001:
            opt_b_results.append((qid, "passed_with_warning", f"Clinically sound advice, low contra, avg_nli={avg_nli:.4f}"))
        else:
            opt_b_results.append((qid, "manual_required", f"Very low entailment avg_nli={avg_nli:.4f}"))

    print("\nOption B Breakdown per query:")
    for qid, status, reason in opt_b_results:
        print(f"  [{qid}] -> {status:20s} | {reason}")

    from collections import Counter
    b_counts = Counter(s for _, s, _ in opt_b_results)
    print(f"\nOption B Distribution: {dict(b_counts)}")

if __name__ == "__main__":
    main()
