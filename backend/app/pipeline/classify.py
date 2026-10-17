"""
D:\\CarePilotAI\\backend\\app\\pipeline\\classify.py

Runtime Intent and Urgency Classifier Module (S6 / P4)
Infers clinical intent and urgency acuity using pre-trained calibrated models.

Public API (Pillar B):
  classify_intent(query_text)               — always runs in every ablation arm
  classify_urgency(query_text, embedding)   — skipped in no_classifier arm only

Legacy wrapper (retained for train_classifiers.py, evaluate_classifiers_rq2.py):
  classify_query(query_text)                — calls both in sequence (unchanged API)

Routing Policy:
- If max P(intent) < tau_intent (0.45), route is 'unsupported' → manual_required
- Urgency predicts 'urgent' if P('urgent') >= tau_high (safety priority)
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import numpy as np
from numpy import ndarray
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = PROJECT_ROOT / "models"
INTENT_MODEL_PATH = MODELS_DIR / "intent_classifier.pkl"
URGENCY_MODEL_PATH = MODELS_DIR / "urgency_classifier.pkl"
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

_EMBEDDER = None
_INTENT_DATA = None
_URGENCY_DATA = None


def get_embedder() -> SentenceTransformer:
    global _EMBEDDER
    if _EMBEDDER is None:
        try:
            _EMBEDDER = SentenceTransformer(EMBEDDING_MODEL_NAME, local_files_only=True)
        except Exception:
            _EMBEDDER = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _EMBEDDER


def load_intent_model():
    global _INTENT_DATA
    if _INTENT_DATA is None:
        if not INTENT_MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Intent model not found at {INTENT_MODEL_PATH}. "
                "Run train_classifiers.py first."
            )
        with open(INTENT_MODEL_PATH, "rb") as f:
            _INTENT_DATA = pickle.load(f)
    return _INTENT_DATA


def load_urgency_model():
    global _URGENCY_DATA
    if _URGENCY_DATA is None:
        if not URGENCY_MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Urgency model not found at {URGENCY_MODEL_PATH}. "
                "Run train_classifiers.py first."
            )
        with open(URGENCY_MODEL_PATH, "rb") as f:
            _URGENCY_DATA = pickle.load(f)
    return _URGENCY_DATA


# ---------------------------------------------------------------------------
# Public Pillar B API — split functions
# ---------------------------------------------------------------------------

def classify_intent(query_text: str) -> dict[str, Any]:
    """
    Always runs in every ablation arm (full / no_ehr / no_classifier / unified_context).

    Returns:
        intent            : str     — one of the 5 supported intent labels
        intent_confidence : float   — max posterior probability
        intent_probs      : dict    — per-class posteriors
        route             : str     — 'draft' | 'unsupported'
        embedding         : ndarray — reusable by classify_urgency() to avoid double-encode
    """
    embedder = get_embedder()
    intent_data = load_intent_model()
    urgency_data = load_urgency_model()  # tau_intent is stored in urgency pkl

    intent_clf = intent_data["model"]
    intent_classes = intent_data["classes"]
    tau_intent: float = urgency_data.get("tau_intent", 0.45)

    emb: ndarray = embedder.encode([query_text], normalize_embeddings=True)

    intent_probs_arr = intent_clf.predict_proba(emb)[0]
    top_idx = int(np.argmax(intent_probs_arr))
    intent_conf = float(intent_probs_arr[top_idx])
    pred_intent: str = intent_classes[top_idx]

    intent_prob_dict = {
        cls: round(float(p), 4)
        for cls, p in zip(intent_classes, intent_probs_arr)
    }

    route = "unsupported" if intent_conf < tau_intent else "draft"

    # ── Dual-Intent Ambiguity Detection (Decision D-007) ──────────────────────
    # For Adverse Drug Reactions (ADRs) or symptoms after taking medications,
    # posterior mass often splits between symptom_report and medication_query.
    is_dual_intent = False
    secondary_intent = None
    p_symptom = float(intent_prob_dict.get("symptom_report", 0.0))
    p_medication = float(intent_prob_dict.get("medication_query", 0.0))

    if pred_intent in ("symptom_report", "medication_query"):
        other_intent = "medication_query" if pred_intent == "symptom_report" else "symptom_report"
        other_prob = p_medication if pred_intent == "symptom_report" else p_symptom
        if other_prob >= 0.02 or abs(p_symptom - p_medication) <= 0.35:
            is_dual_intent = True
            secondary_intent = other_intent

    return {
        "intent": pred_intent,
        "intent_confidence": round(intent_conf, 4),
        "intent_probs": intent_prob_dict,
        "route": route,
        "is_dual_intent": is_dual_intent,
        "secondary_intent": secondary_intent,
        "embedding": emb,  # pass this to classify_urgency() to skip re-encoding
    }


def classify_urgency(
    query_text: str,
    embedding: ndarray | None = None,
) -> dict[str, Any]:
    """
    Skipped in the no_classifier ablation arm.
    Accepts a pre-computed embedding from classify_intent() to avoid double-encoding.

    Returns:
        urgency_classifier : str   — routine | soon | urgent
        urgency_score      : float — winning class posterior
        urgency_probs      : dict  — per-class posteriors
    """
    urgency_data = load_urgency_model()
    urgency_clf = urgency_data["model"]
    urgency_classes: list[str] = urgency_data["classes"]
    tau_high: float = urgency_data.get("tau_high", 0.25)

    if embedding is None:
        embedding = get_embedder().encode([query_text], normalize_embeddings=True)

    urgency_probs_arr = urgency_clf.predict_proba(embedding)[0]

    urgent_idx = urgency_classes.index("urgent") if "urgent" in urgency_classes else 0
    soon_idx = urgency_classes.index("soon") if "soon" in urgency_classes else 1
    routine_idx = urgency_classes.index("routine") if "routine" in urgency_classes else 2

    urgent_prob = float(urgency_probs_arr[urgent_idx])
    soon_prob = float(urgency_probs_arr[soon_idx])
    routine_prob = float(urgency_probs_arr[routine_idx])

    tau_soon: float = float(urgency_data.get("tau_soon", 0.30))

    if urgent_prob >= tau_high:
        pred_urgency = "urgent"
        urgency_score = urgent_prob
    elif soon_prob >= tau_soon:
        pred_urgency = "soon"
        urgency_score = soon_prob
    else:
        pred_urgency = "routine"
        urgency_score = routine_prob

    urgency_prob_dict = {
        cls: round(float(p), 4)
        for cls, p in zip(urgency_classes, urgency_probs_arr)
    }

    return {
        "urgency_classifier": pred_urgency,
        "urgency_score": round(urgency_score, 4),
        "urgency_probs": urgency_prob_dict,
    }


# ---------------------------------------------------------------------------
# Legacy wrapper — unchanged API for train_classifiers.py / evaluate_classifiers_rq2.py
# ---------------------------------------------------------------------------

def classify_query(query_text: str) -> dict[str, Any]:
    """
    Convenience wrapper that calls classify_intent() then classify_urgency()
    sharing the computed embedding. Retained so all existing training and
    evaluation scripts remain unmodified. The orchestrator calls the split
    functions directly.
    """
    intent_result = classify_intent(query_text)
    urgency_result = classify_urgency(query_text, embedding=intent_result["embedding"])

    return {
        "intent": intent_result["intent"],
        "intent_confidence": intent_result["intent_confidence"],
        "intent_probs": intent_result["intent_probs"],
        "urgency_classifier": urgency_result["urgency_classifier"],
        "urgency_score": urgency_result["urgency_score"],
        "urgency_probs": urgency_result["urgency_probs"],
        "route": intent_result["route"],
    }
