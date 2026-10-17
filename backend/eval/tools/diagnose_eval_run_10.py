"""
backend/eval/tools/diagnose_eval_run_10.py
Runs diagnostic queries on EvalRun 10 in carepilot_v3 DB.
"""
from __future__ import annotations
import json
import sys
from sqlalchemy import text

sys.path.insert(0, ".")
from backend.app.db.session import engine


def main():
    with engine.connect() as conn:
        print("=" * 80)
        print("OVERALL RUN 10 SKIP_REASON BREAKDOWN")
        print("=" * 80)
        q_breakdown = text("""
            SELECT skip_reason, count(*) 
            FROM consultations 
            WHERE eval_run_id = 10 
            GROUP BY skip_reason
            ORDER BY count(*) DESC
        """)
        for r in conn.execute(q_breakdown).fetchall():
            print(f"  skip_reason: {r[0]:<25} | count: {r[1]}")

        print("\n" + "=" * 80)
        print("DIAGNOSIS PART 1: 5 validation_failed rows in EvalRun 10")
        print("=" * 80)
        q1 = text("""
            SELECT id, intent, urgency, urgency_final, skip_reason, validation_status, 
                   faithfulness_score, citation_validity_score, citation_entailment_score,
                   faithfulness_details, query_text
            FROM consultations 
            WHERE eval_run_id = 10 AND skip_reason = 'validation_failed'
            ORDER BY id
            LIMIT 5
        """)
        rows1 = conn.execute(q1).fetchall()
        for idx, r in enumerate(rows1, 1):
            print(f"\n--- Row {idx} (Consult ID: {r[0]}) ---")
            print(f"  Intent:             {r[1]}")
            print(f"  Classifier Urgency: {r[2]} | Final Urgency: {r[3]}")
            print(f"  Skip Reason:        {r[4]} | Val Status: {r[5]}")
            print(f"  Faithfulness Score: {r[6]} | Validity: {r[7]} | Entailment: {r[8]}")
            print(f"  Query Text:         \"{r[10]}\"")
            fd = r[9]
            if isinstance(fd, str):
                try:
                    fd = json.loads(fd)
                except Exception:
                    pass
            print(f"  Faithfulness Details: {json.dumps(fd, indent=4) if isinstance(fd, dict) else fd}")

        print("\n" + "=" * 80)
        print("DIAGNOSIS PART 2: 130 Chest-Pain rows in EvalRun 10 (Firm Red-Flag vs Classifier-Only)")
        print("=" * 80)
        q2 = text("""
            SELECT 
                is_red_flag_override,
                redflag_hit_type,
                redflag_category,
                urgency AS classifier_urgency,
                urgency_final,
                COUNT(*) as count
            FROM consultations
            WHERE eval_run_id = 10 
              AND (
                  query_text ILIKE '%chest%' 
                  OR redflag_category ILIKE '%chest%'
                  OR (intent = 'symptom_report' AND query_text ILIKE '%pressure%')
              )
            GROUP BY is_red_flag_override, redflag_hit_type, redflag_category, urgency, urgency_final
            ORDER BY count DESC
        """)
        rows2 = conn.execute(q2).fetchall()
        for r in rows2:
            print(f"Override={r[0]!s:<5} | HitType={r[1]!s:<6} | Category={r[2]!s:<25} | ClfUrgency={r[3]!s:<8} | FinalUrgency={r[4]!s:<8} | Count={r[5]}")

        q2_tot = text("""
            SELECT COUNT(*) FROM consultations 
            WHERE eval_run_id = 10 
              AND (
                  query_text ILIKE '%chest%' 
                  OR redflag_category ILIKE '%chest%'
                  OR (intent = 'symptom_report' AND query_text ILIKE '%pressure%')
              )
        """)
        tot_cp = conn.execute(q2_tot).scalar()
        print(f"\nTotal Chest Pain Rows in Run 10: {tot_cp}")

        print("\n" + "=" * 80)
        print("DIAGNOSIS PART 3: SF-DEV-LAB-ABNORMAL ehr_mismatch rows in EvalRun 10")
        print("=" * 80)
        q3 = text("""
            SELECT id, patient_id, query_text, skip_reason, patient_ehr_mismatch_flag,
                   ehr_chunks_json, retrieval_trace_json
            FROM consultations
            WHERE eval_run_id = 10 
              AND (skip_reason = 'ehr_mismatch' OR patient_ehr_mismatch_flag = true)
            ORDER BY id
        """)
        rows3 = conn.execute(q3).fetchall()
        print(f"Total ehr_mismatch rows found in Run 10: {len(rows3)} (showing first 5)")
        for idx, r in enumerate(rows3[:5], 1):
            pid = str(r[1])
            print(f"\n--- Mismatch Row {idx} (Consult ID: {r[0]}) ---")
            print(f"  Patient ID:   {pid}")
            print(f"  Skip Reason:  {r[3]} | Mismatch Flag: {r[4]}")
            print(f"  Query:        \"{r[2]}\"")
            trace = r[6]
            if isinstance(trace, str):
                try:
                    trace = json.loads(trace)
                except Exception:
                    pass
            print(f"  Retrieval Trace: {json.dumps(trace) if isinstance(trace, dict) else trace}")
            # Query actual lab rows for this patient
            qlabs = text("""
                SELECT code, description, numeric_value, units, observed_at
                FROM lab_results
                WHERE patient_id = :pid
                ORDER BY observed_at DESC
                LIMIT 5
            """)
            labs = conn.execute(qlabs, {"pid": pid}).fetchall()
            print(f"  Patient lab rows (first {len(labs)}):")
            for l in labs:
                print(f"    Code={l[0]} | Desc={l[1]} | Val={l[2]} {l[3]} | Date={l[4]}")


if __name__ == "__main__":
    main()
