"""
D:\\CarePilotAI\\docs\\PILLAR_B_DECISIONS.md

Design decision log for Pillar B (RAG Generation Pipeline).
All decisions requiring explicit sign-off are recorded here before implementation.
"""

# Pillar B — Design Decisions Log

---

## D-001: NLI Model Choice for B5b Entailment Check

**Date:** 2026-10-12
**Status:** DECIDED
**Decision:** Use `cross-encoder/nli-deberta-v3-small`

### Options Considered

| Model | NLI Accuracy (MNLI) | Estimated CPU Latency per pair | VRAM |
|---|---|---|---|
| `cross-encoder/nli-MiniLM-L2-mnli` | ~84% | ~0.10 s | 0 MB (CPU) |
| `cross-encoder/nli-deberta-v3-small` | ~88–90% | ~0.30–0.60 s | 0 MB (CPU) |

### Rationale

- DeBERTa-v3-small achieves ~4–6 point MNLI accuracy advantage over MiniLM-L2.
  For a clinical faithfulness check, this accuracy gain directly reduces the risk
  of passing hallucinated drafts to the doctor queue.
- Latency impact is acceptable:
  - RQ3 live batch (60 queries × ≤5 sentences): ≤ 180 s total on CPU — runs offline
  - Scale batch (3,470 queries): ~30 min on CPU — scheduled offline job, not hot-path
- No latency reason to deviate to MiniLM. deberta-v3-small is the correct choice.

### No Deviation

The spec requests deberta-v3-small. No deviation. MiniLM was the v1/v2 plan error.

---

## D-002: LLM Model Choice for B4 Draft Generation

**Date:** TBD — **BLOCKED on Gate 0 benchmark**
**Status:** OPEN
**Decision:** Deferred until `benchmark_real_llm.py` is run on real GGUF files

### Models Under Evaluation

| Model | Quantization | Expected VRAM | Notes |
|---|---|---|---|
| `qwen3-8b-q4_k_m` | Q4_K_M | ~4.5–5.5 GB | May require CPU offload on 4 GB card |
| `qwen2.5-7b-q4_k_m` | Q4_K_M | ~4.2–5.0 GB | Different architecture than Qwen3 |

### Decision Template (fill after Gate 0)

```
Date: ____-__-__
Chosen model: ___________________
GGUF file: ___________________
n_gpu_layers: ___  (measured VRAM peak: ___ MB)
Measured p50 latency: ___ s/draft
Measured p95 latency: ___ s/draft  
Measured tokens/sec: ___
JSON-valid rate: ___ / 5 prompts
Rationale: 
```

### Fallback Ladder (local-only — no cloud API)

1. Winning model from Gate 0 benchmark — primary for batch RQ1/RQ2
2. Larger quantisation (if VRAM permits) — for RQ3 live sessions

> If a cloud API contingency is ever needed, it must be proposed separately
> and receive explicit sign-off before appearing in any plan or code.

---

## D-003: `no_classifier` Arm — Urgency Deferral

**Date:** 2026-10-12
**Status:** DECIDED

`classify_urgency()` is skipped. The LLM's JSON output field `urgency_assessment`
is used as `urgency_final` for the `no_classifier` arm only.

Invariant I3 still applies: a firm red-flag hit forces `urgent` before B4 runs,
regardless of arm. The LLM's self-reported urgency cannot override a red-flag.

---

## D-004: Gemini API — Excluded from Plan

**Date:** 2026-10-12
**Status:** DECIDED — excluded

Gemini 1.5 Flash (and all cloud-hosted LLM APIs) are excluded from the Pillar B
fallback ladder. If burst-compute contingency is ever needed it must be proposed
separately for explicit sign-off.

All references to Gemini API removed from settings.py after Gate 4 confirmation.
