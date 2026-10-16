"""
backend/scripts/extract_draft_readings.py

Dumps full text of all 15 queries and their drafts for clinical review.
"""
from __future__ import annotations

import json
from pathlib import Path
from backend.app.db.session import SessionLocal
from backend.app.db.models_v3 import Consultation

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "pillar_b_batch_eval_15.json"

def main():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    db = SessionLocal()
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

        print(f"\n================================================================================")
        print(f"CASE {idx}: [{item['query_id']}] Intent: {c.intent} | Status: {c.validation_status} | Avg NLI: {c.citation_entailment_score}")
        print(f"Patient ID: {c.patient_id}")
        print(f"Query: \"{c.query_text}\"")
        if not c.ai_draft_json:
            print(f"NO DRAFT (Safety Flag: mismatch={c.patient_ehr_mismatch_flag})")
            continue

        draft = c.ai_draft_json
        print(f"Tone: {draft.get('overall_tone')} | Urgency: {draft.get('urgency_assessment')}")
        print(f"Follow-up: {draft.get('recommended_followup')}")
        print("Sentences:")
        per_sent = (c.faithfulness_details or {}).get("per_sentence", [])
        for s_idx, sent in enumerate(draft.get("sentences", [])):
            nli = per_sent[s_idx].get("entailment_score") if s_idx < len(per_sent) else None
            cites = sent.get("citations", [])
            print(f"  ({s_idx+1}) [NLI: {nli}] Citations: {cites}")
            print(f"      \"{sent.get('text')}\"")
    db.close()

if __name__ == "__main__":
    main()
