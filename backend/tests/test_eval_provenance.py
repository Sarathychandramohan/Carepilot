from types import SimpleNamespace

from backend.eval import config
from backend.eval.metrics.ehr_fact_accuracy import (
    LAB_DATE_WINDOW_DAYS,
    LAB_VALUE_TOLERANCE,
)
from backend.eval.report import _is_reportable_eval_run


def test_eval_thresholds_match_metric_constants():
    assert config.THRESHOLDS["lab_tolerance_relative"] == LAB_VALUE_TOLERANCE
    assert config.THRESHOLDS["lab_date_window_days"] == LAB_DATE_WINDOW_DAYS


def test_report_excludes_dry_run_and_invalid_runs():
    base = {
        "status": "completed",
        "finished_at": "2026-10-17T00:00:00",
        "config": '{"ablation_arm":"full","dry_run":false}',
    }
    assert _is_reportable_eval_run(SimpleNamespace(**base))

    dry_run = dict(base, config='{"ablation_arm":"full","dry_run":true}')
    assert not _is_reportable_eval_run(SimpleNamespace(**dry_run))

    invalid = dict(base, status="invalid_wrong_thresholds")
    assert not _is_reportable_eval_run(SimpleNamespace(**invalid))

    incomplete = dict(base, finished_at=None)
    assert not _is_reportable_eval_run(SimpleNamespace(**incomplete))
