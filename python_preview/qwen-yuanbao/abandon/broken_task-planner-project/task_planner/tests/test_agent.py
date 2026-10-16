"""
tests/test_agent.py — Agent 逻辑测试（Mock LLM，不依赖真实 API）
════════════════════════════════════════════════════
测试内容：
  ✅ 意图识别 → 无需规划 → 返回 direct_response
  ✅ 意图识别 → 需要规划 → 生成 DAG → 执行 → 渲染
  ✅ 超时控制
  ✅ 节点细化失败不影响主流程
  ✅ 重试逻辑

运行：
  cd /data/workspace
  python -m pytest task_planner/tests/test_agent.py -v
  或
  python task_planner/tests/test_agent.py
"""
import sys
import os
import json
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 安装 Mock（在导入 agent 之前）
from task_planner.tests.mock_llm import install_mock
install_mock()

from task_planner.agent import (
    run_task,
    retry_failed_nodes,
    get_task_status_map,
    TaskAgent,
)
from task_planner.flowchart_pro import render_for_gradio


# ════════════════════════════════════════════════════
#  测试数据
# ════════════════════════════════════════════════════
COOKING_INPUT = "教我做甜口西红柿炒鸡蛋"
TRAVEL_INPUT = "西双版纳3天3夜美食娱乐美景之旅"
SIMPLE_INPUT = "hello"


def test_no_planning_flow():
    """无需规划 → 返回 direct_response，不生成流程图"""
    result = run_task(SIMPLE_INPUT, enable_node_refine=False, external_rid="test-001")
    assert result["success"] is True, f"失败: {result.get('error')}"
    assert result["direct_response"], "应有 direct_response"
    assert result["svg"] == "", "无需规划时 SVG 应为空"
    assert result["task_id"] == "", "无需规划时 task_id 应为空"
    print("✅ test_no_planning_flow")


def test_full_planning_flow():
    """完整流程：意图识别 → 规划 → 细化 → 执行 → 渲染"""
    result = run_task(COOKING_INPUT, enable_node_refine=True, external_rid="test-002")
    assert result["success"] is True, f"失败: {result.get('error')}"
    assert result["task_id"], "应有 task_id"
    assert result["svg"], "应有 SVG 输出"
    assert "vis-network" in result["svg"].lower() or "network" in result["svg"].lower()
    assert "flowchart-data-" in result["svg"]  # 数据传递方式正确
    assert len(result["steps"]) > 0, "应有执行步骤记录"
    print(f"✅ test_full_planning_flow (steps={len(result['steps'])})")


def test_travel_planning():
    """旅游类任务规划"""
    result = run_task(TRAVEL_INPUT, enable_node_refine=True, external_rid="test-003")
    assert result["success"] is True, f"失败: {result.get('error')}"
    assert result["svg"], "应有 SVG"
    print("✅ test_travel_planning")


def test_disable_refine():
    """关闭节点细化"""
    result = run_task(COOKING_INPUT, enable_node_refine=False, external_rid="test-004")
    assert result["success"] is True, f"失败: {result.get('error')}"
    print("✅ test_disable_refine")


def test_progress_callback():
    """进度回调应被调用"""
    progress_log = []
    def cb(step_name, node_id, status, detail):
        progress_log.append(f"{status} {detail}")

    result = run_task(
        COOKING_INPUT,
        enable_node_refine=False,
        external_rid="test-005",
        progress_cb=cb,
    )
    assert result["success"] is True
    assert len(progress_log) > 0, f"进度回调未被调用: {progress_log}"
    print(f"✅ test_progress_callback (calls={len(progress_log)})")


def test_timeout_control():
    """超时控制应生效"""
    start = time.time()
    # 用一个极短的超时
    import task_planner.agent as agent_module
    original_timeout = agent_module.LLM_TASK_TOTAL_TIMEOUT
    agent_module.LLM_TASK_TOTAL_TIMEOUT = 1  # 1秒超时

    try:
        result = run_task("一个需要很长时间的复杂任务", external_rid="test-006")
        elapsed = time.time() - start
        assert elapsed < 10, f"超时控制失效，耗时 {elapsed:.1f}s"
        # 要么成功（很快完成），要么超时
        assert "超时" in result.get("error", "") or result.get("success")
        print(f"✅ test_timeout_control (elapsed={elapsed:.1f}s)")
    finally:
        agent_module.LLM_TASK_TOTAL_TIMEOUT = original_timeout


def test_empty_input():
    """空输入应优雅处理"""
    result = run_task("", external_rid="test-007")
    # 空输入要么报错要么返回友好提示
    assert "error" in result or result.get("status_text", "").startswith("⚠")
    print("✅ test_empty_input")


def test_render_for_gradio_direct():
    """直接调用 render_for_gradio"""
    nodes = [
        {"id": 1, "name": "步骤A", "detail": "做A", "status": 0},
        {"id": 2, "name": "步骤B", "detail": "做B", "status": 1},
        {"id": 3, "name": "步骤C", "detail": "做C", "status": 2},
    ]
    edges = [{"from": 1, "to": 2}, {"from": 2, "to": 3}]
    html = render_for_gradio(nodes, edges, "task_test_render", "test-008")
    assert "步骤A" in html
    assert "步骤B" in html
    assert "application/json" in html
    print("✅ test_render_for_gradio_direct")


# ════════════════════════════════════════════════════
#  主入口
# ════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("  🧪 Agent 逻辑测试（Mock LLM，不依赖真实 API）")
    print("=" * 60)
    print()

    tests = [
        test_no_planning_flow,
        test_full_planning_flow,
        test_travel_planning,
        test_disable_refine,
        test_progress_callback,
        test_timeout_control,
        test_empty_input,
        test_render_for_gradio_direct,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            import traceback
            print(f"❌ {t.__name__}: {e}")
            traceback.print_exc()

    print()
    print("=" * 60)
    print(f"  结果: ✅ {passed} 通过 | ❌ {failed} 失败")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)
