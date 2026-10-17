"""
backend/eval/tools/measure_speed.py

Measures real LLM draft generation speed across 3 real queries:
- Per-draft total seconds
- Generation latency
- Tokens generated and tokens/second
- Checks `ollama ps` PROCESSOR column
"""
import time
import subprocess
import json
from backend.app.db.session import SessionLocal
from backend.eval.query_sets import load_query_split
from backend.app.pipeline.orchestrator import run_pipeline

def main():
    session = SessionLocal()
    try:
        queries = load_query_split("gold-synthetic", db=session, subset_n=3)
        print("=" * 80)
        print(f"MEASURING REAL SPEED: 3 REAL DRAFTS ON LOCAL LLM (qwen3:8b)")
        print("=" * 80)

        for idx, q in enumerate(queries, start=1):
            print(f"\n--- Draft [{idx}/3] ---")
            print(f"Query ID:   {q.query_id}")
            print(f"Patient ID: {q.patient_id}")
            print(f"Query Text: {q.query_text}")

            t0 = time.perf_counter()
            consultation = run_pipeline(
                patient_id=q.patient_id,
                query_text=q.query_text,
                db=session,
                ablation_config="full",
                is_eval=True,
            )
            elapsed_total = time.perf_counter() - t0

            # Check ollama ps
            ps_proc = subprocess.run(["ollama", "ps"], capture_output=True, text=True)
            ollama_ps_out = ps_proc.stdout.strip()

            latency_ms = consultation.generation_latency_ms or int(elapsed_total * 1000)
            latency_sec = latency_ms / 1000.0

            # Extract full draft text
            full_draft = ""
            if consultation.ai_draft_json and "sentences" in consultation.ai_draft_json:
                draft_sentences = [s.get("text", "") for s in consultation.ai_draft_json["sentences"]]
                full_draft = " ".join(draft_sentences)

            # Estimate tokens: 1.3 tokens per word on clinical English
            word_count = len(full_draft.split())
            token_count = int(word_count * 1.33)
            tok_per_sec = (token_count / latency_sec) if latency_sec > 0 else 0.0

            print(f"Total Pipeline Seconds: {elapsed_total:.2f} s")
            print(f"Generation Latency:     {latency_sec:.2f} s ({latency_ms} ms)")
            print(f"Draft Word Count:       {word_count} words")
            print(f"Tokens Generated:       ~{token_count} tokens")
            print(f"Speed (Tokens/Sec):     {tok_per_sec:.2f} tok/s")
            print(f"Validation Status:      {consultation.validation_status}")
            print(f"\nOllama PS Output:")
            print(ollama_ps_out)
            print("-" * 80)

    finally:
        session.close()

if __name__ == "__main__":
    main()
