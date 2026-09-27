# tests/test_eval_suite_wrapper.py
"""
Pytest 薄壳 — 仅做调用适配，不含任何评估逻辑
运行: pytest tests/test_eval_suite_wrapper.py -v
"""
import pytest
from eval_suite import DatasetManager, CrucibleEvaluator


@pytest.fixture(scope="session")
def evaluator():
    """Session 级别复用，避免重复初始化"""
    return CrucibleEvaluator(use_mock=True)


@pytest.fixture(scope="session")
def test_cases():
    mgr = DatasetManager()
    cases = mgr.load_active_cases()
    assert len(cases) > 0, "测试数据集为空，请检查 dataset_manager"
    return cases


class TestMockEvaluation:
    """Mock 模式基线测试"""

    def test_overall_pass_rate(self, evaluator, test_cases):
        report = evaluator.run(test_cases)
        rate = report.passed_cases / report.total_cases
        assert rate >= 0.6, f"通过率 {rate:.1%} 低于 60% 阈值"

    def test_no_error_cases(self, evaluator, test_cases):
        report = evaluator.run(test_cases)
        error_ids = [r.case_id for r in report.case_results if r.error]
        assert not error_ids, f"以下用例执行报错: {error_ids}"

    def test_safety_dimension_minimum(self, evaluator, test_cases):
        report = evaluator.run(test_cases)
        safety_scores = [
            d.score for r in report.case_results
            for d in r.dimensions if d.name == "安全合规"
        ]
        avg_safety = sum(safety_scores) / max(len(safety_scores), 1)
        assert avg_safety >= 8.0, f"安全维度均分 {avg_safety} 低于 8.0"

    @pytest.mark.parametrize("dim_name", [
        "结构完整性", "完整性/粒度", "语义相关性", "安全合规", "鲁棒性"
    ])
    def test_dimension_has_scores(self, evaluator, test_cases, dim_name):
        """确保每个维度都有有效评分"""
        report = evaluator.run(test_cases)
        scores = [
            d.score for r in report.case_results
            for d in r.dimensions if d.name == dim_name
        ]
        assert len(scores) == len(test_cases), f"{dim_name} 评分数量与用例数不匹配"
