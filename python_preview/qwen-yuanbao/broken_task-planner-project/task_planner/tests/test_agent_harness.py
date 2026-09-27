"""
test_agent_harness.py — pytest 测试用例
"""
import pytest
from task_planner.tests.run_eval import TEST_CASES, EXPECTATIONS


@pytest.mark.parametrize("case", TEST_CASES, ids=lambda c: c["id"])
def test_agent_case(harness, case):
    """每个用例独立跑一次"""
    result = harness.run_case(case["id"], case["input"])
    assert result is not None
    assert result.req_id  # 有 req_id


def test_batch_eval(harness, expectations):
    """跑完所有用例后做批量评估"""
    from task_planner.tests.harness.evaluators import eval_batch
    from task_planner.tests.harness.reporters import save_reports
    import os
    from pathlib import Path

    report = eval_batch(harness, expectations)
    out_dir = Path(__file__).resolve().parent / "output"
    paths = save_reports(report, str(out_dir))

    print(f"\n📊 报告: {paths['markdown']}")
    print(f"   JSON: {paths['json']}")

    assert report.get("avg_pass_rate", 0) >= 50, "通过率过低"
