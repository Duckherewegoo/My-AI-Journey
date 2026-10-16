"""
run_eval.py — 独立运行 Agent 评估（不用 pytest）
══════════════════════════════════════════
用法：
  cd /app
  python -m task_planner.tests.run_eval
  # 或
  python task_planner/tests/run_eval.py

环境变量：
  USE_MOCK_LLM=false（默认走真实 LLM）
  DASHSCOPE_API_KEY=...（必须）
"""
import os
import sys
from pathlib import Path

# 确保项目根在 path 里
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 强制真实模式
os.environ["USE_MOCK_LLM"] = "false"

from task_planner.tests.harness.agent_harness import AgentHarness
from task_planner.tests.harness.evaluators import eval_batch
from task_planner.tests.harness.reporters import save_reports

# ═════════════════════════════════════════════
#  测试用例集（可扩展）
# ═════════════════════════════════════════════
TEST_CASES = [
    # ── 烹饪类（期望：需要规划，多步骤） ──
    {"id": "cook_001", "input": "教我做甜口西红柿炒鸡蛋"},
    {"id": "cook_002", "input": "怎么做红烧肉？要详细的火候和调料"},
    {"id": "cook_003", "input": "我想学做麻婆豆腐，零基础"},

    # ── 工程类（期望：需要规划，复杂 DAG） ──
    {"id": "eng_001", "input": "帮我部署一个 Python FastAPI 服务到生产环境，要 HTTPS 和监控"},
    {"id": "eng_002", "input": "怎么把现有 Django 项目迁移到 Kubernetes"},

    # ── 学习类（期望：需要规划） ──
    {"id": "learn_001", "input": "我想用 3 个月从零学会 Rust，给我一个学习计划"},

    # ── 简单问答（期望：无需规划） ──
    {"id": "simple_001", "input": "Python 里 list 和 tuple 的区别是什么？"},

    # ── 生活类 ──
    {"id": "life_001", "input": "我要搬家，从北京到上海，帮我规划一下"},
]

# 人工标注的期望意图（用于评估准确率）
EXPECTATIONS = {
    "cook_001":    {"needs_planning": True,  "category": "cooking"},
    "cook_002":    {"needs_planning": True,  "category": "cooking"},
    "cook_003":    {"needs_planning": True,  "category": "cooking"},
    "eng_001":     {"needs_planning": True,  "category": "engineering"},
    "eng_002":     {"needs_planning": True,  "category": "engineering"},
    "learn_001":   {"needs_planning": True,  "category": "learning"},
    "simple_001":  {"needs_planning": False, "category": "other"},
    "life_001":    {"needs_planning": True,  "category": "life_admin"},
}


def main():
    print("🚀 Task Planner Agent — 评估开始")
    print(f"   用例数: {len(TEST_CASES)}")
    print(f"   LLM 模式: {'MOCK' if os.getenv('USE_MOCK_LLM') == 'true' else 'REAL'}")
    print(f"   模型: {os.getenv('LLM_INTENT_MODEL', '?')}")
    print()

    # 1) 跑 Harness
    harness = AgentHarness(enable_refine=True)
    results = harness.run_batch(TEST_CASES)

    # 2) 保存原始数据
    raw_path = PROJECT_ROOT / "task_planner" / "tests" / "output" / "raw_results.json"
    harness.save_raw(str(raw_path))

    # 3) 评估
    report = eval_batch(harness, EXPECTATIONS)

    # 4) 生成报告
    out_dir = PROJECT_ROOT / "task_planner" / "tests" / "output"
    paths = save_reports(report, str(out_dir))

    # 5) 控制台摘要
    print("=" * 60)
    print("📊 评估结果摘要")
    print("=" * 60)
    print(f"  总用例:   {report.get('total_cases', 0)}")
    print(f"  全部通过: {report.get('fully_passed', 0)}")
    print(f"  平均通过: {report.get('avg_pass_rate', 0)}%")
    print()
    print("  维度得分:")
    for dim, st in report.get("dimension_summary", {}).items():
        print(f"    {dim:12s}: {st['avg_pct']}% ({st['avg_score']})")
    print()
    print(f"  ✅ Markdown: {paths['markdown']}")
    print(f"  ✅ JSON:     {paths['json']}")
    print()

    # 6) 退出码（CI 用）
    success_rate = report.get("avg_pass_rate", 0)
    if success_rate < 70:
        print("⚠️ 通过率低于 70%，建议检查")
        sys.exit(1)
    print("🎉 评估通过")
    sys.exit(0)


if __name__ == "__main__":
    main()
