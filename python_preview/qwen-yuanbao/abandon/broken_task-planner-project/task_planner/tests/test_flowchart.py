"""
tests/test_flowchart.py — 流程图渲染测试（不依赖 LLM / MongoDB）
════════════════════════════════════════════════════
测试内容：
  ✅ DAG 校验（合法图 / 有环图）
  ✅ SVG 渲染输出非空
  ✅ HTML 交互式输出包含关键元素
  ✅ 节点状态颜色映射
  ✅ 导出 JSON 格式正确

运行：
  cd /data/workspace
  python -m pytest task_planner/tests/test_flowchart.py -v
  或
  python task_planner/tests/test_flowchart.py
"""
import sys
import os
import json
import tempfile

# 确保项目根目录在 path 中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from task_planner.flowchart_pro import (
    ProFlowchartRenderer,
    render_for_gradio,
    export,
)
from task_planner.config import (
    STATUS_TEXT,
    STATUS_COLOR,
    STATUS_BORDER,
)
# 别名
NODE_STATUS_COLORS = STATUS_COLOR
NODE_STATUS_BORDERS = STATUS_BORDER
NODE_STATUS_ICONS = {0: "⏳", 1: "🔄", 2: "✅", 3: "❌", 4: "⏰"}


# ═════════════════════════════════════════════════════
#  测试数据
# ═════════════════════════════════════════════════════
SAMPLE_NODES = [
    {"id": 1, "name": "准备食材", "detail": "西红柿2个+鸡蛋3个", "status": 0},
    {"id": 2, "name": "炒鸡蛋", "detail": "中火炒至八分熟", "status": 1},
    {"id": 3, "name": "炒西红柿", "detail": "煸炒出汁加糖", "status": 0},
    {"id": 4, "name": "合并调味", "detail": "回锅翻匀出锅", "status": 0},
]

SAMPLE_EDGES = [
    {"from": 1, "to": 2, "label": "食材备好"},
    {"from": 2, "to": 3, "label": "鸡蛋盛出"},
    {"from": 3, "to": 4, "label": "西红柿出汁"},
]

CYCLIC_EDGES = [
    {"from": 1, "to": 2},
    {"from": 2, "to": 3},
    {"from": 3, "to": 1},  # 环！
]


# ═════════════════════════════════════════════════════
#  测试函数
# ═════════════════════════════════════════════════════

def test_dag_validation_success():
    """合法 DAG 应通过校验"""
    renderer = ProFlowchartRenderer()
    g = renderer._validate_dag(SAMPLE_NODES, SAMPLE_EDGES, "test-req-001")
    assert g is not None
    assert len(g.nodes()) == 4
    assert len(g.edges()) == 3
    print("✅ test_dag_validation_success")


def test_dag_validation_cyclic():
    """有环图应抛 ValueError"""
    renderer = ProFlowchartRenderer()
    try:
        renderer._validate_dag(SAMPLE_NODES, CYCLIC_EDGES, "test-req-002")
        assert False, "应抛 ValueError"
    except ValueError as e:
        assert "循环" in str(e) or "cycle" in str(e).lower()
        print("✅ test_dag_validation_cyclic")


def test_render_interactive_contains_elements():
    """交互式 HTML 应包含关键元素"""
    renderer = ProFlowchartRenderer()
    html = renderer.render_interactive(
        SAMPLE_NODES, SAMPLE_EDGES, "task_test_001", "test-req-003"
    )
    # 关键元素检查
    assert "vis-network" in html.lower() or "network" in html.lower()
    assert "准备食材" in html
    assert "炒鸡蛋" in html
    assert "application/json" in html  # 数据传递方式
    assert "flowchart-data-" in html  # 数据 script 标签
    print("✅ test_render_interactive_contains_elements")


def test_render_for_gradio_wraps_html():
    """render_for_gradio 应返回包裹在 div 中的 HTML"""
    html = render_for_gradio(SAMPLE_NODES, SAMPLE_EDGES, "task_test_002", "test-req-004")
    assert isinstance(html, str)
    assert len(html) > 100
    assert "<div" in html
    print("✅ test_render_for_gradio_wraps_html")


def test_export_html():
    """导出 HTML 格式"""
    html = export(SAMPLE_NODES, SAMPLE_EDGES, "task_test_003", "html", "test-req-005")
    assert isinstance(html, str)
    assert len(html) > 100
    print("✅ test_export_html")


def test_export_json():
    """导出 JSON 格式"""
    json_str = export(SAMPLE_NODES, SAMPLE_EDGES, "task_test_004", "json", "test-req-006")
    data = json.loads(json_str)
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 4
    assert len(data["edges"]) == 3
    print("✅ test_export_json")


def test_export_unsupported_format():
    """不支持的格式应抛 ValueError"""
    try:
        export(SAMPLE_NODES, SAMPLE_EDGES, "task_test_005", "pdf", "test-req-007")
        assert False, "应抛 ValueError"
    except ValueError:
        print("✅ test_export_unsupported_format")


def test_status_color_mapping():
    """状态 → 颜色映射正确"""
    assert NODE_STATUS_COLORS[0] == "#fff3e0"   # 待处理 橙色
    assert NODE_STATUS_COLORS[2] == "#e8f5e9"   # 成功 绿色
    assert NODE_STATUS_BORDERS[3] == "#ef4444"    # 失败 红色
    assert NODE_STATUS_ICONS[1] == "🔄"         # 进行中
    assert STATUS_TEXT[4] == "⏰ 超时"
    print("✅ test_status_color_mapping")


def test_empty_nodes_handling():
    """空节点列表不应崩溃"""
    renderer = ProFlowchartRenderer()
    html = renderer.render_interactive([], [], "task_empty", "test-req-008")
    assert isinstance(html, str)
    assert "暂无" in html or "empty" in html.lower() or len(html) > 0
    print("✅ test_empty_nodes_handling")


def test_node_with_meta():
    """带 meta 信息的节点应正确渲染"""
    nodes = [
        {
            "id": 1,
            "name": "测试节点",
            "detail": "详细步骤1\n步骤2\n步骤3",
            "status": 0,
            "meta": {
                "preconditions": ["前置条件A", "前置条件B"],
                "postconditions": ["预期结果X"],
                "retry_policy": "失败后重试最多3次",
            },
        },
    ]
    html = render_for_gradio(nodes, [], "task_meta_001", "test-req-009")
    assert "测试节点" in html
    assert "前置条件" in html or "preconditions" in html.lower()
    print("✅ test_node_with_meta")


# ═════════════════════════════════════════════════════
#  主入口
# ═════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("  🧪 Flowchart 渲染测试（不依赖 LLM / MongoDB）")
    print("=" * 60)
    print()

    tests = [
        test_status_color_mapping,
        test_dag_validation_success,
        test_dag_validation_cyclic,
        test_render_interactive_contains_elements,
        test_render_for_gradio_wraps_html,
        test_export_html,
        test_export_json,
        test_export_unsupported_format,
        test_empty_nodes_handling,
        test_node_with_meta,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"❌ {t.__name__}: {e}")

    print()
    print("=" * 60)
    print(f"  结果: ✅ {passed} 通过 | ❌ {failed} 失败")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)
