"""
D:\\CarePilotAI\\backend\\app\\api\\queue.py

GET /api/queue — Doctor queue feed.
GET /api/queue/stats — Aggregate queue statistics.

Returns consultations awaiting doctor review, ordered by priority and creation time.
Supports filtering by ablation_arm for research stratification.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, desc, text
from sqlalchemy.orm import Session

from backend.app.db.models_v3 import Consultation

router = APIRouter(prefix="/api/queue", tags=["Pillar B — Doctor Queue"])


def get_db():
    from backend.app.db.session import SessionLocal  # type: ignore
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=list[dict])
async def get_queue(
    ablation_arm: Optional[str] = Query(None, description="Filter by ablation arm"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[dict]:
    """
    Returns consultations awaiting doctor review.

    Ordering: 3-tier urgency hierarchy (urgent > soon > routine),
    then FIFO by creation time ascending (oldest first).
    Excludes evaluation queries (is_eval == False).
    Supports optional filtering by ablation_arm for research analysis.
    """
    q = db.query(Consultation).filter(
        Consultation.thread_status == "awaiting_doctor",
        Consultation.is_eval == False,
    )

    if ablation_arm:
        q = q.filter(Consultation.ablation_arm == ablation_arm)

    # 3-tier urgency order (urgent=0, soon=1, routine=2), then FIFO
    urgency_order = case(
        (Consultation.urgency_final == "urgent", 0),
        (Consultation.urgency_final == "soon", 1),
        else_=2,
    )

    rows = (
        q.order_by(
            urgency_order,
            Consultation.created_at.asc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        {
            "id": r.id,
            "patient_id": r.patient_id,
            "query_text": r.query_text,
            "intent": r.intent,
            "urgency_final": r.urgency_final,
            "is_high_priority": r.is_high_priority,
            "is_red_flag_override": r.is_red_flag_override,
            "validation_status": r.validation_status,
            "has_draft": r.ai_draft_json is not None,
            "faithfulness_score": r.faithfulness_score,
            "ablation_arm": r.ablation_arm,
            "patient_ehr_mismatch_flag": getattr(r, "patient_ehr_mismatch_flag", None),
            "missing_context_flag": getattr(r, "missing_context_flag", None),
            "created_at": str(r.created_at),
        }
        for r in rows
    ]


@router.get("/stats", response_model=dict)
async def get_queue_stats(db: Session = Depends(get_db)) -> dict:
    """
    Aggregate queue statistics — total pending, high priority count,
    breakdown by validation_status and ablation_arm.
    Supports T1–T8 metric monitoring.
    """
    result = db.execute(
        text("""
            SELECT
                COUNT(*)                                               AS total_pending,
                SUM(CASE WHEN is_high_priority THEN 1 ELSE 0 END)     AS high_priority,
                SUM(CASE WHEN is_red_flag_override THEN 1 ELSE 0 END) AS red_flag_overrides,
                SUM(CASE WHEN ai_draft_json IS NOT NULL THEN 1 ELSE 0 END) AS has_draft,
                SUM(CASE WHEN validation_status = 'passed' THEN 1 ELSE 0 END)                   AS status_passed,
                SUM(CASE WHEN validation_status = 'passed_with_warning' THEN 1 ELSE 0 END)      AS status_warning,
                SUM(CASE WHEN validation_status = 'passed_with_outlier_caveat' THEN 1 ELSE 0 END) AS status_outlier_caveat,
                SUM(CASE WHEN validation_status = 'manual_required' THEN 1 ELSE 0 END)          AS status_manual
            FROM consultations
            WHERE thread_status = 'awaiting_doctor' AND is_eval = FALSE
        """)
    ).fetchone()

    arm_rows = db.execute(
        text("""
            SELECT ablation_arm, COUNT(*) AS count
            FROM consultations
            WHERE thread_status = 'awaiting_doctor' AND is_eval = FALSE
            GROUP BY ablation_arm
            ORDER BY count DESC
        """)
    ).fetchall()

    return {
        "total_pending": result.total_pending or 0,
        "high_priority": result.high_priority or 0,
        "red_flag_overrides": result.red_flag_overrides or 0,
        "has_draft": result.has_draft or 0,
        "by_validation_status": {
            "passed": result.status_passed or 0,
            "passed_with_warning": result.status_warning or 0,
            "passed_with_outlier_caveat": result.status_outlier_caveat or 0,
            "manual_required": result.status_manual or 0,
        },
        "by_ablation_arm": {r.ablation_arm or "unknown": r.count for r in arm_rows},
    }
