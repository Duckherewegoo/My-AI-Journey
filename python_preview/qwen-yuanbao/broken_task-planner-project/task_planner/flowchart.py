"""
flowchart.py — 流程图渲染引擎（纯 Python + Graphviz）
- 拓扑分层 → 有序有向图
- 起点/终点自动识别，颜色区分
- 箭头方向明确（Graphviz dot 布局原生支持）
- 输出 SVG / PDF / PNG / DOT 四种格式
- 零前端 JS 依赖
"""
import os
import logging
from typing import List, Dict, Any, Optional

from .config import STATUS_COLOR, STATUS_BORDER, STATUS_TEXT, RENDER_DPI, RENDER_DIR

logger = logging.getLogger("task_planner.flowchart")

# ═══════════════════════════════════════════════════
#  拓扑分析：分层 + 起点/终点识别
# ═══════════════════════════════════════════════════
def analyze_graph(nodes: List[Dict], edges: List[Dict]) -> Dict[str, Any]:
    """
    分析节点和边的拓扑结构
    返回：每个节点的 in_degree / out_degree / layer / is_start / is_end
    """
    node_map = {n["id"]: dict(n) for n in nodes}
    in_deg: Dict = {nid: 0 for nid in node_map}
    out_deg: Dict = {nid: 0 for nid in node_map}
    adj: Dict = {nid: [] for nid in node_map}

    for e in edges:
        f = e["from"]
        t = e["to"]
        if f in adj and t in node_map:
            adj[f].append(t)
            out_deg[f] += 1
            in_deg[t] += 1

    # 分层（BFS 按最长路径分层）
    layer: Dict = {}
    queue = [nid for nid in node_map if in_deg[nid] == 0]
    for nid in queue:
        layer[nid] = 0
    visited = set(queue)
    while queue:
        nid = queue.pop(0)
        for nb in adj[nid]:
            if nb not in visited:
                layer[nb] = layer[nid] + 1
                visited.add(nb)
                queue.append(nb)

    max_layer = max(layer.values()) if layer else 0
    for nid in node_map:
        if nid not in layer:
            layer[nid] = max_layer + 1

    for nid, info in node_map.items():
        info["in_degree"] = in_deg[nid]
        info["out_degree"] = out_deg[nid]
        info["layer"] = layer[nid]
        info["is_start"] = in_deg[nid] == 0
        info["is_end"] = out_deg[nid] == 0
        info.setdefault("status", 0)

    return {
        "nodes": list(node_map.values()),
        "edges": edges,
        "adj": adj,
        "layer": layer,
    }


# ═══════════════════════════════════════════════════
#  Graphviz 渲染
# ═══════════════════════════════════════════════════
def build_dot(analysis: Dict, graph_title: str = ""):
    """
    根据拓扑分析结果构建 Graphviz Digraph 对象
    - 自动识别起点（菱形）/ 终点（椭圆）
    - 箭头方向明确
    - 状态颜色映射
    - 分层排列（rank=same via invisible edges）
    """
    import graphviz  # type: ignore

    dot = graphviz.Digraph(
        comment=graph_title or "Task Flow",
        format="svg",
        engine="dot",
    )
    dot.attr(
        rankdir="TB",
        bgcolor="white",
        fontname="Noto Sans CJK SC",
        fontsize="14",
        compound="true",
        nodesep="0.5",
        ranksep="0.8",
    )
    dot.attr("node", fontname="Noto Sans CJK SC", fontsize="13")
    dot.attr("edge", fontname="Noto Sans CJK SC", fontsize="11", arrowsize="0.8")

    nodes = analysis["nodes"]
    edges = analysis["edges"]

    # 按 layer 分组
    layers: Dict[int, List] = {}
    for n in nodes:
        layers.setdefault(n["layer"], []).append(n)

    # 用不可见节点 + 同 rank 边来做层级对齐
    for layer_idx in sorted(layers.keys()):
        layer_nodes = sorted(layers[layer_idx], key=lambda x: x["id"])
        # 添加不可见占位节点
        inv_name = f"_rank_{layer_idx}_anchor"
        dot.node(inv_name, label="", style="invis", width="0", height="0")

        for n in layer_nodes:
            nid = str(n["id"])
            label = n.get("name", f"节点{n['id']}")
            status = n.get("status", 0)
            color = STATUS_COLOR.get(status, "#eeeeee")
            border = STATUS_BORDER.get(status, "#999999")
            status_text = STATUS_TEXT.get(status, "?")

            if n.get("is_start"):
                shape = "diamond"
            elif n.get("is_end"):
                shape = "ellipse"
            else:
                shape = "box"

            full_label = f"{label}\\n──\\n{status_text}"

            dot.node(
                nid,
                label=full_label,
                shape=shape,
                style="filled,rounded",
                fillcolor=color,
                color=border,
                penwidth="2",
                width="2.2",
                height="0.8",
            )

            # 不可见边 → 强制同 rank
            dot.edge(inv_name, nid, style="invis", arrowhead="none")

    # 添加真实边（带箭头，有向图核心）
    for e in edges:
        f = str(e["from"])
        t = str(e["to"])
        label = e.get("label", "")
        dot.edge(
            f, t,
            label=label,
            arrowhead="vee",
            arrowtail="none",
            dir="forward",
            color="#546e7a",
            penwidth="1.5",
        )

    if graph_title:
        dot.attr(label=graph_title, labelloc="t", labeljust="c")

    return dot


# ═══════════════════════════════════════════════════
#  对外接口：渲染 + 导出
# ═══════════════════════════════════════════════════
def render_flowchart(
    nodes: List[Dict],
    edges: List[Dict],
    graph_title: str = "",
    output_dir: str = RENDER_DIR,
    base_name: str = "flowchart",
    formats: Optional[List[str]] = None,
) -> Dict[str, str]:
    """
    主入口：渲染流程图并导出多种格式
    返回：{ "svg": path, "pdf": path, "png": path, "dot": path }
    """
    os.makedirs(output_dir, exist_ok=True)
    formats = formats or ["svg", "pdf", "png"]

    analysis = analyze_graph(nodes, edges)
    dot = build_dot(analysis, graph_title)

    results: Dict[str, str] = {}

    for fmt in formats:
        out_path = os.path.join(output_dir, f"{base_name}.{fmt}")
        try:
            if fmt == "dot":
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(dot.source)
            elif fmt == "svg":
                data = dot.pipe(format="svg")
                with open(out_path, "wb") as f:
                    f.write(data)
            elif fmt == "pdf":
                data = dot.pipe(format="pdf")
                with open(out_path, "wb") as f:
                    f.write(data)
            elif fmt == "png":
                dot_png = dot.copy()
                dot_png.attr(dpi=str(RENDER_DPI))
                data = dot_png.pipe(format="png")
                with open(out_path, "wb") as f:
                    f.write(data)
            else:
                logger.warning("[Flowchart] 不支持的格式: %s", fmt)
                continue
            results[fmt] = out_path
            logger.info("[Flowchart] ✅ 导出 %s: %s", fmt.upper(), out_path)
        except Exception as e:
            logger.error("[Flowchart] ❌ 导出 %s 失败: %s", fmt, e)

    return results


def render_svg_for_gradio(nodes: List[Dict], edges: List[Dict], graph_title: str = "") -> str:
    """
    直接返回 SVG 字符串，供 Gradio gr.HTML 嵌入显示
    带友好错误提示（中文）
    """
    try:
        analysis = analyze_graph(nodes, edges)
        dot = build_dot(analysis, graph_title)
        svg_bytes = dot.pipe(format="svg")
        svg_str = svg_bytes.decode("utf-8")

        svg_str = svg_str.replace(
            "<svg ", '<svg width="100%" height="500" preserveAspectRatio="xMidYMid meet" ', 1
        )
        logger.info("[Flowchart] ✅ SVG 渲染成功 (nodes=%d, edges=%d)", len(nodes), len(edges))
        return svg_str
    except FileNotFoundError:
        msg = "⚠️ 系统未安装 Graphviz，无法渲染流程图。请安装：apt-get install graphviz"
        logger.error("[Flowchart] %s", msg)
        return (
            '<div style="padding:20px;border:2px solid #ef4444;'
            'border-radius:8px;color:#b91c1c;background:#fef2f2;">'
            f'<b>{msg}</b></div>'
        )
    except Exception as e:
        msg = f"⚠️ 流程图渲染失败：{type(e).__name__}: {e}"
        logger.error("[Flowchart] %s", msg)
        return (
            '<div style="padding:20px;border:2px solid #f59e0b;'
            'border-radius:8px;color:#92400e;background:#fffbeb;">'
            f'<b>{msg}</b></div>'
        )
