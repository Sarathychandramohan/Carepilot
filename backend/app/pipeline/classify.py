"""
D:\\CarePilotAI\\backend\\app\\pipeline\\classify.py

Runtime Intent and Urgency Classifier Module (S6 / P4)
Infers clinical intent and urgency acuity using pre-trained calibrated models.

Routing Policy:
- If max P(intent) < tau_intent (0.50), route is 'unsupported' -> triggers manual_required
- Urgency predicts 'urgent' if P('urgent') >= tau_high (safety priority)
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import numpy as np
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
        _EMBEDDER = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _EMBEDDER


def load_intent_model():
    global _INTENT_DATA
    if _INTENT_DATA is None:
        if not INTENT_MODEL_PATH.exists():
            raise FileNotFoundError(f"Intent model not found at {INTENT_MODEL_PATH}. Run train_classifiers.py first.")
        with open(INTENT_MODEL_PATH, "rb") as f:
            _INTENT_DATA = pickle.load(f)
    return _INTENT_DATA


def load_urgency_model():
    global _URGENCY_DATA
    if _URGENCY_DATA is None:
        if not URGENCY_MODEL_PATH.exists():
            raise FileNotFoundError(f"Urgency model not found at {URGENCY_MODEL_PATH}. Run train_classifiers.py first.")
        with open(URGENCY_MODEL_PATH, "rb") as f:
            _URGENCY_DATA = pickle.load(f)
    return _URGENCY_DATA


def classify_query(query_text: str) -> dict[str, Any]:
    """
    Classifies a patient query into Intent and Urgency.
    Returns:
    {
        "intent": str,
        "intent_confidence": float,
        "intent_probs": dict[str, float],
        "urgency_classifier": str,
        "urgency_score": float,
        "urgency_probs": dict[str, float],
        "route": "draft" | "unsupported"
    }
    """
    embedder = get_embedder()
    intent_data = load_intent_model()
    urgency_data = load_urgency_model()

    intent_clf = intent_data["model"]
    intent_classes = intent_data["classes"]

    urgency_clf = urgency_data["model"]
    urgency_classes = urgency_data["classes"]
    tau_high = urgency_data.get("tau_high", 0.30)
    tau_intent = urgency_data.get("tau_intent", 0.50)

    # 1. Encode query
    emb = embedder.encode([query_text], normalize_embeddings=True)

    # 2. Intent Prediction
    intent_probs = intent_clf.predict_proba(emb)[0]
    top_intent_idx = int(np.argmax(intent_probs))
    intent_conf = float(intent_probs[top_intent_idx])
    pred_intent = intent_classes[top_intent_idx]

    intent_prob_dict = {cls_name: round(float(prob), 4) for cls_name, prob in zip(intent_classes, intent_probs)}

    # Check unsupported route
    route = "draft"
    if intent_conf < tau_intent:
        route = "unsupported"

    # 3. Urgency Prediction (with tau_high decision rule)
    urgency_probs = urgency_clf.predict_proba(emb)[0]
    urgent_idx = urgency_classes.index("urgent") if "urgent" in urgency_classes else 0
    urgent_prob = float(urgency_probs[urgent_idx])

    if urgent_prob >= tau_high:
        pred_urgency = "urgent"
        urgency_score = urgent_prob
    else:
        top_urgency_idx = int(np.argmax(urgency_probs))
        pred_urgency = urgency_classes[top_urgency_idx]
        urgency_score = float(urgency_probs[top_urgency_idx])

    urgency_prob_dict = {cls_name: round(float(prob), 4) for cls_name, prob in zip(urgency_classes, urgency_probs)}

    return {
        "intent": pred_intent,
        "intent_confidence": round(intent_conf, 4),
        "intent_probs": intent_prob_dict,
        "urgency_classifier": pred_urgency,
        "urgency_score": round(urgency_score, 4),
        "urgency_probs": urgency_prob_dict,
        "route": route,
    }
