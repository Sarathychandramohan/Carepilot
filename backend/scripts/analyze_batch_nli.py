"""
backend/scripts/analyze_batch_nli.py

Analyzes sentence-level NLI scores across all 15 queries in the Pillar B batch eval.
Extracts:
1. Sentence text
2. Citation IDs
3. Cited source texts (EHR vs KB)
4. NLI entailment score
5. Sentence claim category: patient_fact vs general_info vs advice_lifestyle
"""
from __future__ import annotations

import json
from pathlib import Path
from backend.app.db.session import SessionLocal
from backend.app.db.models_v3 import Consultation

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "pillar_b_batch_eval_15.json"

def classify_claim_type(text: str, cited_ids: list[str]) -> str:
    text_lower = text.lower()
    # Advice / Action / Lifestyle indicators
    advice_triggers = [
        "should", "you can", "you should", "it is important to", "make sure to",
        "schedule", "contact your", "reach out", "call your", "discuss with",
        "recommend", "consider", "avoid", "ensure you", "try to", "take your medicine",
        "monitor", "keep track", "adjust"
    ]
    if any(trig in text_lower for trig in advice_triggers):
        return "advice_lifestyle"
    
    # Patient fact: cites EHR or reports personal clinical findings
    has_ehr = any(cid.startswith("ehr:") for cid in cited_ids)
    if has_ehr or any(w in text_lower for w in ["your test", "your lab", "your result", "was recorded", "your condition", "you were diagnosed"]):
        return "patient_fact"
    
    # Otherwise general medical info / definition
    return "general_info"


def main():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    db = SessionLocal()
    records = []

    for idx, item in enumerate(manifest["results"], start=1):
        qtext = item["query_text"]
        c = (
            db.query(Consultation)
            .filter(Consultation.query_text == qtext)
            .order_by(Consultation.query_received_at.desc())
            .first()
        )
        if not c:
            continue

        q_info = {
            "idx": idx,
            "query_id": item["query_id"],
            "intent": c.intent,
            "urgency": c.urgency_final,
            "validation_status": c.validation_status,
            "avg_nli": c.citation_entailment_score,
            "citation_coverage": c.faithfulness_score,
            "mismatch_flag": c.patient_ehr_mismatch_flag,
            "missing_context_flag": c.missing_context_flag,
            "has_draft": c.ai_draft_json is not None,
            "sentences": []
        }

        if not c.ai_draft_json:
            records.append(q_info)
            continue

        sentences = c.ai_draft_json.get("sentences", [])
        faith_details = c.faithfulness_details or {}
        per_sent_faith = faith_details.get("per_sentence", [])

        # Build mapping of citation texts from ehr_chunks_json and kb_chunks_json
        ehr_chunks = {chunk["chunk_id"]: chunk["text"] for chunk in (c.ehr_chunks_json or []) if "chunk_id" in chunk}
        kb_chunks = {chunk["chunk_id"]: chunk["text"] for chunk in (c.kb_chunks_json or []) if "chunk_id" in chunk}

        for s_idx, s in enumerate(sentences):
            stext = s.get("text", "")
            cites = s.get("citations", [])

            nli_score = None
            for pf in per_sent_faith:
                pf_text = pf.get("text", "")
                if pf_text and (pf_text[:30] in stext or stext[:30] in pf_text):
                    nli_score = pf.get("entailment_score")
                    break
            if nli_score is None and s_idx < len(per_sent_faith):
                nli_score = per_sent_faith[s_idx].get("entailment_score")

            claim_type = classify_claim_type(stext, cites)

            # Get cited chunk text snippets
            cited_texts = []
            for cid in cites:
                if cid in ehr_chunks:
                    cited_texts.append(f"[{cid}] {ehr_chunks[cid][:120]}...")
                elif cid in kb_chunks:
                    cited_texts.append(f"[{cid}] {kb_chunks[cid][:120]}...")
                else:
                    cited_texts.append(f"[{cid}] (source text not in top ehr/kb json)")

            q_info["sentences"].append({
                "s_idx": s_idx + 1,
                "text": stext,
                "citations": cites,
                "nli_score": nli_score,
                "claim_type": claim_type,
                "cited_texts": cited_texts
            })

        records.append(q_info)

    db.close()

    # Save detailed JSON
    out_path = PROJECT_ROOT / "data" / "manifests" / "batch_15_sentence_nli_analysis.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    print(f"Analysis saved to {out_path}")

    # Print summary statistics by claim_type
    by_type = {"patient_fact": [], "general_info": [], "advice_lifestyle": []}
    for q in records:
        for s in q.get("sentences", []):
            ct = s["claim_type"]
            score = s["nli_score"]
            if score is not None:
                by_type[ct].append(score)

    print("\n================== NLI SCORES BY CLAIM TYPE ==================")
    for ct, scores in by_type.items():
        if scores:
            scores.sort()
            avg = sum(scores) / len(scores)
            med = scores[len(scores)//2]
            p90 = scores[int(0.9 * len(scores))]
            print(f"Claim Type '{ct}' (N={len(scores)}):")
            print(f"  Min: {min(scores):.4f} | Median: {med:.4f} | Mean: {avg:.4f} | Max: {max(scores):.4f}")
            print(f"  Scores < 0.10: {sum(1 for sc in scores if sc < 0.10)} / {len(scores)} ({sum(1 for sc in scores if sc < 0.10)/len(scores)*100:.1f}%)")
            print(f"  Scores < 0.30: {sum(1 for sc in scores if sc < 0.30)} / {len(scores)} ({sum(1 for sc in scores if sc < 0.30)/len(scores)*100:.1f}%)")
        else:
            print(f"Claim Type '{ct}': N=0")


if __name__ == "__main__":
    main()
