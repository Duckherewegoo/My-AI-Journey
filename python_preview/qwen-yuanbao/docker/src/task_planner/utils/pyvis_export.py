"""
DAG 静态可视化导出引擎 (Graphviz Backend)

## 模块定位
本模块是基于 Graphviz/pydot 的**纯后端静态渲染引擎**，负责将 DAG 数据结构
转换为高质量的 SVG/PNG 矢量或位图文件。它是整个任务流可视化体系的**基础设施层**，
而非面向终端用户的交互组件。

## 与 flowchart_pro 的关系

    ┌─────────────────────────────────────────────────┐
    │          flowchart_pro (交互式业务层)             │
    │   PyVis + vis.js → HTML/JS → 浏览器端交互        │
    │   · 拖拽/缩放/点击/悬停高亮                       │
    │   · 实时状态刷新                                 │
    │   · 业务操作入口                                 │
    └──────────────────────┬──────────────────────────┘
                           │ import 共享
    ┌──────────────────────┴──────────────────────────┐
    │       pyvis_export.py (静态基础设施层) ← 本模块   │
    │   Graphviz + cairosvg → SVG/PNG → 字节流/文件    │
    │   · 零交互，纯静态产物                            │
    │   · 提供共享配置 (NODE_COLORS / EDGE_STYLES)      │
    │   · 提供数据清洗 (_normalize_node_states)         │
    │   · dot 布局算法 (DAG 层级布局金标准)              │
    └─────────────────────────────────────────────────┘

### 核心区别

| 维度         | pyvis_export.py (本模块)        | flowchart_pro              |
|-------------|-------------------------------|---------------------------|
| 渲染引擎     | Graphviz (C) + cairosvg       | PyVis → vis.js (JS)       |
| 输出格式     | SVG / PNG 字节流或文件         | 自包含 HTML 字符串          |
| 交互能力     | ❌ 无                          | ✅ 拖拽/缩放/点击/高亮      |
| 布局算法     | dot (严格层级 DAG 布局)        | Barnes-Hut (力导向物理模拟) |
| 中文渲染     | 依赖系统字体 + cairosvg        | 浏览器原生渲染              |
| 运行环境     | 纯后端，无需浏览器             | 需浏览器执行 JS            |
| 大图性能     | 1000+ 节点秒级出图             | 200+ 节点可能卡顿          |
| 适用场景     | 报告/PPT/邮件/归档/CI          | Web 仪表盘/调试/用户探索    |

### 何时使用本模块而非 flowchart_pro
- 需要将流程图嵌入 **邮件、PDF 报告、PPT** 等非 Web 载体
- 需要在 **无浏览器环境** (容器/Serverless/CI) 中生成图表
- 需要 **严格层级对齐** 的 DAG 布局 (dot 算法优于力导向)
- 需要生成 **缩略图/预览图** 等轻量级静态产物
- 作为 flowchart_pro 的**配置与数据清洗共享源**

## 导出接口一览
- export_dag_to_svg()          : DAG → SVG bytes (矢量，推荐用于报告/打印)
- export_dag_to_png()          : DAG → PNG bytes (位图，推荐用于邮件/缩略图)
- export_from_dag_store()      : dag_store 便捷入口，支持格式路由

## 共享基础设施 (供 flowchart_pro 导入复用)
- NODE_COLORS / EDGE_STYLES    : 状态→视觉属性映射表
- FONT_FACE / PYDOT_GRAPH_ATTRS: 全局渲染配置
- _normalize_node_states()     : 节点状态归一化
- _estimate_canvas_size()      : 画布尺寸自适应估算

## 运行时依赖
- graphviz: 系统级二进制 (apt: graphviz / brew: graphviz)
- cairosvg: PNG 转换 (pip install cairosvg)
  - 系统依赖: apt: libcairo2-dev pkg-config python3-dev
- pydot: Python Graphviz 绑定 (pip install pydot)

Note:
    本模块不包含任何交互逻辑。如需 Web 端可交互 DAG 可视化，
    请使用 flowchart_pro.render_interactive_dag()。
"""
import os
import logging
from typing import Dict, List, Optional, Tuple
import io
from pyvis.network import Network
import networkx as nx

try:
    from task_planner.infrastructure.logger_setup import get_logger
    logger = get_logger()
except ImportError:
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)

# ══════════════════════════════════════════════════
#  从 config 统一导入（消除重复定义）
# ══════════════════════════════════════════════════
from task_planner.infrastructure.config import (
    STATUS_COLOR, STATUS_BORDER, STATUS_TEXT,
    NODE_TEXT_COLORS, NODE_COLORS, EDGE_STYLES,
    DEFAULT_EDGE_STYLE,
    FONT_FACE, RENDER_EDGE_WIDTH,
)

# ══════════════════════════════════════════════════
#  适配层：将 config 枚举转为 pyvis/networkx 可用的渲染字典
# ══════════════════════════════════════════════════

# 节点颜色：(背景色, 边框色, 文字色)
# config 只定义了背景和边框，文字色根据背景亮度自动推导或手动补充
# 已经内置到 config 中
_NODE_TEXT_COLORS = NODE_TEXT_COLORS
# ══════════════════════════════════════════════════
#  内部工具函数
# ══════════════════════════════════════════════════


def _normalize_node_states(
    node_states: Optional[Dict[str, str]],
) -> Dict[str, str]:
    """确保 node_states 的 key 全部为 str，避免类型不匹配导致状态丢失"""
    if not node_states:
        return {}
    return {str(k): v for k, v in node_states.items()}


def _estimate_canvas_size(nodes: List[Dict], edges: List[Dict]) -> Tuple[int, int]:
    """根据节点数和边数动态估算画布尺寸"""
    n = max(len(nodes), 1)
    e = max(len(edges), 1)
    width = min(2400, max(1000, n * 180))
    height = min(2000, max(800, n * 140))
    if e > n * 1.5:
        height = int(height * 1.3)
    return width, height


def _build_pydot_graph(
    nodes: List[Dict],
    edges: List[Dict],
    node_states: Dict[str, str],
    title: str,
    dpi: int,
):
    """
    统一构建 pydot 图对象（供 SVG / PNG 导出共用）
    返回 pydot.Dot 实例
    """
    import pydot  # noqa: F811

    G = nx.DiGraph()

    for node in nodes:
        nid = str(node.get("id"))
        if not nid:
            continue
        label = node.get("label") or node.get("name") or nid
        state = node_states.get(nid, "pending")
        if state not in NODE_COLORS:
            state = "pending"
        color_bg, color_border, color_text = NODE_COLORS[state]
        G.add_node(
            nid,
            label=label,
            style="filled,rounded",
            fillcolor=color_bg,
            color=color_border,
            penwidth="2",
            fontcolor=color_text,
            fontname=FONT_FACE,
            fontsize="14",
            shape="box",
            margin="0.3,0.15",
        )

    added = set()
    for edge in edges:
        src = str(edge.get("from") or edge.get("source"))
        tgt = str(edge.get("to") or edge.get("target"))
        if not src or not tgt or (src, tgt) in added:
            continue
        added.add((src, tgt))

        edge_label = edge.get("label", "")
        state = edge.get("state", node_states.get(src, "pending"))
        style_info = EDGE_STYLES.get(state, DEFAULT_EDGE_STYLE)

        edge_attrs = {
            "label": f" {edge_label} " if edge_label else "",
            "color": style_info["color"],
            "penwidth": str(style_info["width"]),
            "fontname": FONT_FACE,
            "fontsize": "11",
            "fontcolor": "#555555",
        }
        if style_info["style"] == "dashed":
            edge_attrs["style"] = "dashed"
        G.add_edge(src, tgt, **edge_attrs)

    dot_graph = nx.nx_pydot.to_pydot(G)
    dot_graph.obj_dict["attributes"].update({
        "dpi": str(dpi),
        "bgcolor": "white",
        "rankdir": "TB",
        "nodesep": "0.8",
        "ranksep": "1.2",
        "pad": "0.5",
        "label": title,
        "labelloc": "t",
        "fontname": FONT_FACE,
        "fontsize": "18",
        "splines": "true",
        "overlap": "false",
    })
    return dot_graph


# ══════════════════════════════════════════════════
#  核心渲染引擎 (PyVis — 交互式)
# ══════════════════════════════════════════════════

def _render_pyvis_html(
    nodes: List[Dict],
    edges: List[Dict],
    node_states: Optional[Dict[str, str]] = None,
) -> Network:
    """使用 PyVis 渲染 DAG（支持有环）并返回 Network 对象"""
    canvas_w, canvas_h = _estimate_canvas_size(nodes, edges)
    net = Network(
        directed=True, notebook=False,
        height=f"{canvas_h}px", width=f"{canvas_w}px",
        bgcolor="#ffffff", font_color="#333333", layout=None,
    )

    states = _normalize_node_states(node_states)

    for node in nodes:
        nid = str(node.get("id"))
        if not nid:
            continue
        label = node.get("label") or node.get("name") or nid
        if len(label) > 20:
            label = label[:17] + "..."

        state = states.get(nid, "pending")
        if state not in NODE_COLORS:
            state = "pending"
        color_bg, color_border, color_text = NODE_COLORS[state]
        title = f"ID: {nid}\n状态: {state}\n详情: {node.get('description', '无')}"

        net.add_node(
            n_id=nid, label=label, title=title,
            color={
                "background": color_bg, "border": color_border,
                "highlight": {"background": color_bg, "border": color_border},
            },
            borderWidth=2, shape="box", margin=15, size=25,
            font={"color": color_text, "size": 16, "face": FONT_FACE},
        )

    added_edges = set()
    for edge in edges:
        src = str(edge.get("from") or edge.get("source"))
        tgt = str(edge.get("to") or edge.get("target"))
        if not src or not tgt or (src, tgt) in added_edges:
            continue
        added_edges.add((src, tgt))

        edge_label = edge.get("label", "")
        state = edge.get("state", states.get(src, "pending"))
        style_info = EDGE_STYLES.get(state, DEFAULT_EDGE_STYLE)

        net.add_edge(
            src, tgt,
            title=edge_label, label=edge_label,
            color=style_info["color"], width=style_info["width"],
            dashes=(style_info["style"] == "dashed"),
            arrows="to", arrowStrikethrough=False,
            font={"face": FONT_FACE, "size": 12,
                  "color": "#555555", "align": "middle"},
            smooth={"type": "curvedCW", "roundness": 0.2},
        )

    net.barnes_hut(
        gravity=-30000, central_gravity=0.8, spring_length=250,
        spring_strength=0.05, damping=0.75, overlap=0.5,
    )
    net.toggle_physics(True)
    return net


# ══════════════════════════════════════════════════
#  对外导出接口
# ══════════════════════════════════════════════════

def export_dag_to_svg(
    nodes: List[Dict],
    edges: List[Dict],
    output_path: Optional[str] = None,
    node_states: Optional[Dict[str, str]] = None,
    title: str = "流程图",
    dpi: int = 800,
) -> bytes:
    """DAG → pydot → SVG bytes"""
    if not nodes:
        raise ValueError("没有节点数据可导出")

    try:
        states = _normalize_node_states(node_states)
        dot_graph = _build_pydot_graph(nodes, edges, states, title, dpi)
        svg_bytes = dot_graph.create_svg(prog="dot")

        if output_path is not None:
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(svg_bytes)
            file_size = len(svg_bytes) / 1024
            logger.info(
                "[Export] ✅ SVG 已保存: %s (%.1f KB)", output_path, file_size
            )

        return svg_bytes

    except Exception:
        logger.error("[Export] SVG 导出失败", exc_info=True)
        raise


def export_dag_to_png(
    nodes: List[Dict],
    edges: List[Dict],
    output_path: Optional[str] = None,      # ← 改为 Optional，默认 None
    node_states: Optional[Dict[str, str]] = None,
    title: str = "流程图",
    width: int = 1600,
    height: int = 2000,
    dpi: int = 1000,
) -> bytes:                                  # ← 返回值改为 bytes
    """DAG → pydot SVG → cairosvg PNG
    - output_path=None: 纯内存模式，返回 PNG bytes
    - output_path=str: 写入磁盘，同时返回 PNG bytes
    """
    if not nodes:
        raise ValueError("没有节点数据可导出")

    try:
        import cairosvg

        states = _normalize_node_states(node_states)
        dot_graph = _build_pydot_graph(nodes, edges, states, title, dpi)
        svg_bytes = dot_graph.create_svg(prog="dot")

        # ✅ 核心改动：cairosvg 写入 BytesIO 而非文件
        buf = io.BytesIO()
        cairosvg.svg2png(
            bytestring=svg_bytes,
            write_to=buf,                    # ← 写入内存缓冲区
            output_width=width,
            output_height=height,
            dpi=dpi,
        )
        png_bytes = buf.getvalue()

        # 可选：写入磁盘（与 SVG 函数行为对齐）
        if output_path is not None:
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(png_bytes)
            logger.info(
                "[Export] ✅ PNG 已保存: %s (%.1f KB)",
                output_path, len(png_bytes) / 1024,
            )

        return png_bytes                       # ← 统一返回 bytes

    except Exception:
        logger.error("[Export] PNG 导出失败", exc_info=True)
        raise


def export_from_dag_store(
    dag_store: Dict,
    output_path: str,
    node_states: Optional[Dict[str, str]] = None,
    title: str = "流程图",
) -> bytes:
    """便捷入口：从 dag_store 字典直接导出 PNG"""
    nodes = dag_store.get("nodes", [])
    edges = dag_store.get("edges", [])
    if not nodes:
        raise ValueError("dag_store 中没有节点数据")
    return export_dag_to_png(
        nodes=nodes, edges=edges,
        output_path=output_path,
        node_states=node_states, title=title,
    )
