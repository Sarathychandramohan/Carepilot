"""
D:\\CarePilotAI\\backend\\scripts\\verify_redflag.py

Verifies the Red-Flag Rule Engine against all 30 test cases in
data/queries/redflag_test_table.json.

Evaluates:
- Firm hit recall on acute emergency positives
- Negation detection (no false escalation on negated queries)
- Historical / hypothetical handling (routed to soft hits, no false override)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.pipeline.redflag import evaluate_red_flags

TEST_TABLE_PATH = PROJECT_ROOT / "data" / "queries" / "redflag_test_table.json"


def run_redflag_verification() -> bool:
    if not TEST_TABLE_PATH.exists():
        print(f"ERROR: Red-flag test table not found at {TEST_TABLE_PATH}")
        return False

    with open(TEST_TABLE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data.get("cases", [])
    print("\n" + "=" * 60)
    print(f"CarePilot AI — Red-Flag Safety Verification ({len(cases)} Cases)")
    print("=" * 60)

    passed = 0
    failed = 0

    for c in cases:
        case_id = c["case_id"]
        q_text = c["query_text"]
        exp_hit = c["expected_hit_type"]
        exp_urgency = c.get("expected_urgency", "routine")

        res = evaluate_red_flags(q_text)
        act_hit = res["hit_type"]
        act_override = res["urgency_override"]

        # Verification criterion:
        # 1. Hit type matches (firm / soft / none)
        # 2. If firm, urgency_override must be 'urgent'
        match_hit = (act_hit == exp_hit)
        match_override = (act_override == "urgent") if exp_hit == "firm" else (act_override is None)

        is_correct = match_hit and match_override

        status_str = "[PASS]" if is_correct else "[FAIL]"
        if is_correct:
            passed += 1
        else:
            failed += 1

        print(f"\n{status_str} {case_id} [{c['category']} / {c['variant']}]:")
        print(f"  Query:    '{q_text}'")
        print(f"  Expected: hit_type='{exp_hit}'")
        print(f"  Actual:   hit_type='{act_hit}', firm={len(res['firm_hits'])}, soft={len(res['soft_hits'])}, negated={len(res['negated_hits'])}")

        if not is_correct:
            print(f"  --> MISMATCH details: {res}")

    print("\n" + "-" * 60)
    print(f"Summary: {passed}/{len(cases)} cases passed. ({failed} failed)")
    all_passed = (failed == 0)

    if all_passed:
        print("[OK] Pillar B Red-Flag Safety Gate: PASS")
    else:
        print("[FAIL] Pillar B Red-Flag Safety Gate: FAIL")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = run_redflag_verification()
    sys.exit(0 if success else 1)
