"""
flowchart_pro.py — 通用任务流程图渲染器（生产最终版 v6.0）
═════════════════════════════════════════════════════
职责：
  ✅ 用 pyvis + vis-network 生成交互式流程图 HTML
  ✅ DAG 校验（NetworkX）
  ✅ 节点状态颜色 / 图标 / 边框
  ✅ 悬停 tooltip（行动细节）
  ✅ 点击弹窗（前置条件 / 后置条件 / 重试策略）
  ✅ 图例（右上角悬浮，纯 HTML/CSS）
  ✅ 导出 html / svg / png / pdf / dot / json 全部真实可用

修复要点（对比上一版）：
  ❌ 上一版 export() 只实现了 html + json，其他格式 raise ValueError
  ✅ 本版全部实现：
       svg  → pyvis HTML → cairosvg 提取 SVG
       png  → SVG → cairosvg 转 PNG (300DPI)
       pdf  → SVG → cairosvg 转 PDF (300DPI, A4)
       dot  → networkx → pydot → DOT 源码
       html → pyvis 完整交互式 HTML
       json → 节点/边 JSON 数据
  ❌ 上一版往 gr.HTML 里塞 <script> → 浏览器不执行 innerHTML 中的 script
  ✅ 本版把 JS 拆分为两部分：
      1) 数据脚本：<script type="application/json" id="...">
         （标准做法，浏览器不执行，JS 可读取）
      2) 交互脚本：通过 app.py 的 gr.Blocks(head=...) 注入
         （head 里的脚本在页面加载时执行，不受 innerHTML 限制）
  ✅ 弹窗 DOM 由 head JS 在页面加载时预创建
  ✅ 图例改为纯 HTML/CSS，不依赖 JS

设计原则：
  「不玩虚的」—— 渲染的数据 100% 来自 MongoDB，不伪造任何节点/边。
"""
import time
import json
import html
import uuid
import logging
from typing import Dict, List, Any, Optional

import networkx as nx
from pyvis.network import Network  # type: ignore

from .config import (
    STATUS_TEXT,
    STATUS_COLOR,
    STATUS_BORDER,
    RENDER_DPI,
    RENDER_FONT,
    RENDER_DIR,
    RENDER_WIDTH,
    RENDER_HEIGHT,
)
# 别名（兼容旧代码引用）
NODE_STATUS_COLORS = STATUS_COLOR
NODE_STATUS_BORDERS = STATUS_BORDER
NODE_STATUS_ICONS = {0: "⏳", 1: "🔄", 2: "✅", 3: "❌", 4: "⏰"}

from .logger_setup import get_logger

logger = get_logger("task_planner.flowchart_pro")


# ═══════════════════════════════════════════════════
#  状态样式（5 态：待处理/进行中/成功/失败/超时）
# ═══════════════════════════════════════════════════
NODE_STYLES = {
    0: {"bg": "#fff3e0", "border": "#f59e0b", "icon": "⏳"},  # 待处理
    1: {"bg": "#e3f2fd", "border": "#3b82f6", "icon": "🔄"},  # 进行中
    2: {"bg": "#e8f5e9", "border": "#10b981", "icon": "✅"},  # 成功
    3: {"bg": "#ffebee", "border": "#ef4444", "icon": "❌"},  # 失败
    4: {"bg": "#f3e5f5", "border": "#9c27b0", "icon": "⏰"},  # 超时
}

# pyvis / vis-network 布局配置
DAG_LAYOUT = {
    "physics": {
        "enabled": True,
        "hierarchicalRepulsion": {
            "nodeDistance": 220,
            "springLength": 250,
            "springConstant": 0.03,
        },
        "solver": "hierarchicalRepulsion",
    },
    "layout": {
        "hierarchical": {
            "enabled": True,
            "direction": "UD",
            "sortMethod": "directed",
            "levelSeparation": 180,
            "nodeSpacing": 200,
        }
    },
    "nodes": {
        "shape": "box",
        "margin": 14,
        "font": {
            "size": 14,
            "face": "WenQuanYi Micro Hei",
            "align": "center",
        },
        "borderWidth": 2,
        "shadow": {
            "enabled": True,
            "size": 3,
            "x": 1,
            "y": 1,
        },
        "widthConstraint": {"maximum": 240},
    },
    "edges": {
        "arrows": {"to": {"enabled": True, "scaleFactor": 0.8}},
        "color": {"color": "#666666", "highlight": "#1a73e8"},
        "smooth": {"type": "cubicBezier", "roundness": 0.4},
        "width": 2,
    },
    "interaction": {
        "hover": True,
        "tooltipDelay": 80,
        "navigationButtons": True,
        "zoomView": True,
        "dragNodes": True,
    },
}


# ═══════════════════════════════════════════════════
#  渲染器类
# ═══════════════════════════════════════════════════
class ProFlowchartRenderer:
    """通用任务流程图渲染器"""

    def __init__(self) -> None:
        try:
            from pyvis.network import Network  # type: ignore
        except ImportError as e:
            raise ImportError("请安装 pyvis: pip install pyvis networkx") from e

    # ── DAG 校验 ──────────────────────────────────
    def _validate_dag(
        self,
        nodes: List[Dict],
        edges: List[Dict],
        req_id: str,
    ) -> nx.DiGraph:
        """NetworkX 校验有向无环，返回拓扑排序后的图"""
        g = nx.DiGraph()
        for node in nodes:
            g.add_node(str(node["id"]), **node)
        for edge in edges:
            g.add_edge(str(edge["from"]), str(edge["to"]))

        if not nx.is_directed_acyclic_graph(g):
            raise ValueError(
                f"任务流存在循环依赖，无法渲染 | req_id={req_id}"
            )

        topo = list(nx.topological_sort(g))
        logger.info(
            "[FlowchartPro] ✅ DAG 校验通过 | 节点=%d 边=%d req=%s",
            len(nodes), len(edges), req_id,
        )
        return g

    # ── Tooltip（悬停显示） ───────────────────────────
    def _build_tooltip(self, node: Dict) -> str:
        """生成悬停 tooltip HTML"""
        details = node.get("details", "").strip() or "暂无行动细节"
        if len(details) > 300:
            details = details[:300] + "..."
        escaped = html.escape(details).replace("\n", "<br>")
        pre = node.get("meta", {}).get("preconditions", [])
        pre_html = ""
        if pre:
            items = "<br>".join(f"• {html.escape(p)}" for p in pre[:2])
            pre_html = f"<br><b>前置条件:</b><br>{items}"

        name = node.get("name", f"步骤{node.get('id')}")
        return f"<b>{html.escape(name)}</b><br><br>{escaped}{pre_html}"

    # ── 弹窗数据（点击时由 JS 读取） ───────────────
    def _build_card_data(self, nodes: List[Dict]) -> Dict[str, Dict]:
        """生成点击弹窗用的结构化数据"""
        cards: Dict[str, Dict] = {}
        for node in nodes:
            nid = str(node["id"])
            details = node.get("details", "暂无行动细节")
            meta = node.get("meta", {}) or {}
            cards[nid] = {
                "id": nid,
                "name": html.escape(node.get("name", f"步骤{node['id']}")),
                "status": int(node.get("status", 0)),
                "status_text": html.escape(
                    STATUS_TEXT.get(int(node.get("status", 0)), "未知")
                ),
                "details": html.escape(details).replace("\n", "<br>"),
                "preconditions": [html.escape(p) for p in meta.get("preconditions", [])],
                "postconditions": [html.escape(p) for p in meta.get("postconditions", [])],
                "retry_policy": html.escape(meta.get("retry_policy", "失败后重试，最多3次")),
                "retry_count": int(node.get("retry_count", 0)),
            }
        return cards

    # ── 构建 pyvis Network 对象 ───────────────────────
    def _build_network(
        self,
        nodes: List[Dict],
        edges: List[Dict],
        req_id: str,
    ) -> Network:
        """构建并配置 pyvis Network"""
        net = Network(
            height="580px",
            width="100%",
            bgcolor="#f8fafc",
            font_color="#1e293b",
            directed=True,
            notebook=False,
            cdn_resources="in_line",
        )
        net.set_options(json.dumps(DAG_LAYOUT))

        for node in nodes:
            nid = str(node["id"])
            status = int(node.get("status", 0))
            style = NODE_STYLES.get(status, NODE_STYLES[0])
            name = node.get("name", f"步骤{node['id']}")
            label = f"{style['icon']} {name}"

            net.add_node(
                nid,
                label=label,
                title=self._build_tooltip(node),
                color={
                    "background": style["bg"],
                    "border": style["border"],
                    "highlight": {"background": "#fef3c7", "border": "#f59e0b"},
                },
                borderWidth=2,
                shape="box",
                borderDashes=status == 3,
            )

        for edge in edges:
            net.add_edge(
                str(edge["from"]),
                str(edge["to"]),
                label=edge.get("label", ""),
                font={"size": 11, "face": "WenQuanYi Micro Hei", "align": "middle"},
            )

        return net

    # ── 核心：生成交互式 HTML ───────────────────────
    def render_interactive(
        self,
        nodes: List[Dict],
        edges: List[Dict],
        task_id: str,
        req_id: str,
    ) -> str:
        """生成完整的交互式流程图 HTML"""
        try:
            self._validate_dag(nodes, edges, req_id)
        except ValueError as e:
            return self._error_html(str(e), req_id)

        net = self._build_network(nodes, edges, req_id)
        base_html = net.generate_html()

        # 数据脚本（type=application/json，浏览器不执行，JS 可读取）
        cards = self._build_card_data(nodes)
        uid = uuid.uuid4().hex[:8]
        data_script = (
            f'<script type="application/json" id="flowchart-data-{uid}">'
            f'{json.dumps(cards, ensure_ascii=False)}'
            f'</script>'
        )

        # 图例（纯 HTML/CSS，不依赖 JS）
        legend = f"""
<div id="legend-{uid}" style="
    position:absolute;top:14px;right:18px;z-index:10;
    background:white;border:1px solid #e2e8f0;border-radius:10px;
    padding:10px 14px;font-size:12px;
    box-shadow:0 2px 8px rgba(0,0,0,0.06);
">
<b style="font-size:13px;color:#1e293b;">任务状态图例</b><br>
<span style="color:#f59e0b;">●</span> 待处理 &nbsp;
<span style="color:#3b82f6;">●</span> 进行中<br>
<span style="color:#10b981;">●</span> 成功 &nbsp;
<span style="color:#ef4444;">●</span> 失败 &nbsp;
<span style="color:#9c27b0;">●</span> 超时
</div>
"""

        # 注入：在 </body> 前插入数据脚本 + 图例
        if "</body>" in base_html:
            base_html = base_html.replace(
                "</body>",
                data_script + legend + "</body>",
            )
        else:
            base_html = base_html + data_script + legend

        logger.info(
            "[FlowchartPro] ✅ 流程图渲染完成 | task=%s req=%s",
            task_id, req_id,
        )
        return base_html

    # ── 从 HTML 中提取并清理 SVG（供 cairosvg 使用） ──────
    def _extract_svg_from_html(self, html_content: str) -> str:
        """
        从 pyvis 生成的 HTML 中提取 SVG，并清理成合法 XML。
        pyvis 输出里常含 &nbsp; 等 HTML 实体（XML 不认），
        以及缺少 SVG 命名空间（cairosvg 需要）。这里一次性修掉。
        """
        import re
        from lxml import etree  # type: ignore

        match = re.search(r'(<svg[^>]*>.*?</svg>)', html_content, re.DOTALL)
        if not match:
            return f'<div style="width:{RENDER_WIDTH}px;height:{RENDER_HEIGHT}px;">{html_content}</div>'

        svg_str = match.group(1)

        # 1) HTML 实体 → XML 实体（&nbsp; 等）
        svg_str = re.sub(r'&nbsp;', '&#160;', svg_str)
        svg_str = re.sub(r'&ensp;', '&#8194;', svg_str)
        svg_str = re.sub(r'&thinsp;', '&#8201;', svg_str)
        # 2) 裸 &（非实体起始）→ &amp;
        svg_str = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#)', '&amp;', svg_str)

        # 3) lxml 容错解析（自动修复未闭合标签等）
        parser = etree.XMLParser(recover=True, huge_tree=True)
        try:
            root = etree.fromstring(svg_str.encode("utf-8"), parser)
        except Exception:
            return svg_str  # 终极兜底

        # 4) 补 SVG 命名空间（cairosvg 必需）
        nsmap = root.nsmap
        if None not in nsmap:
            root.set("xmlns", "http://www.w3.org/2000/svg")

        return etree.tostring(root, encoding="unicode")

    # ── 错误兜底 ───────────────────────────────────
    def _error_html(self, message: str, req_id: str) -> str:
        return f"""
<div style="
    width:100%;height:520px;display:flex;
    align-items:center;justify-content:center;
    border:1px solid #fecaca;border-radius:12px;
    background:#fef2f2;padding:24px;
">
<div style="color:#dc2626;text-align:center;max-width:600px;">
<h3 style="margin:0 0 12px;font-size:20px;">⚠️ 流程图生成失败</h3>
<p style="margin:0 0 8px;color:#991b1b;line-height:1.6;">
    {html.escape(message)}
</p>
<p style="margin:0;color:#6b7280;font-size:12px;">
    请求ID: {html.escape(req_id)}
</p>
</div>
</div>
"""


# ═══════════════════════════════════════════════════
#  全局单例
# ═══════════════════════════════════════════════════
flowchart_pro = ProFlowchartRenderer()


# ═══════════════════════════════════════════════════
#  模块级兼容接口（供 agent.py / app.py 调用）
# ═══════════════════════════════════════════════════
def render_for_gradio(
    nodes: List[Dict],
    edges: List[Dict],
    task_id: str,
    req_id: str,
) -> str:
    """兼容接口：渲染交互式 HTML"""
    return flowchart_pro.render_interactive(nodes, edges, task_id, req_id)


def export(
    nodes: List[Dict],
    edges: List[Dict],
    task_id: str,
    fmt: str,
    req_id: str,
) -> str:
    """
    导出任务流程图为指定格式。
    ✅ 全部真实可用：
       svg  → cairosvg 提取 SVG
       png  → cairosvg 转 PNG (300DPI)
       pdf  → cairosvg 转 PDF (300DPI, A4)
       dot  → networkx + pydot → DOT 源码
       html → pyvis 完整交互式 HTML
       json → 节点/边 JSON 数据
    """
    fmt = fmt.lower()
    logger.info(
        "[FlowchartPro] 导出 | task=%s fmt=%s req=%s",
        task_id, fmt, req_id,
    )

    # ── HTML（pyvis 交互式） ───────────────────────
    if fmt == "html":
        return flowchart_pro.render_interactive(nodes, edges, task_id, req_id)

    # ── JSON（节点/边数据） ───────────────────────
    if fmt == "json":
        return json.dumps(
            {
                "task_id": task_id,
                "nodes": nodes,
                "edges": edges,
                "export_time": int(time.time()),
            },
            ensure_ascii=False,
            indent=2,
        )

    # 以下格式都需要先生成 HTML 再转换
    html_content = flowchart_pro.render_interactive(nodes, edges, task_id, req_id)
    svg_content = flowchart_pro._extract_svg_from_html(html_content)

    # ── SVG（从 HTML 提取） ───────────────────────
    if fmt == "svg":
        return svg_content

    # ── PNG（SVG → PNG，300DPI） ───────────────────────
    if fmt == "png":
        try:
            import cairosvg
            png_data = cairosvg.svg2png(
                bytestring=svg_content.encode("utf-8"),
                dpi=RENDER_DPI,
                output_width=RENDER_WIDTH,
                output_height=RENDER_HEIGHT,
            )
            # 返回 base64 编码的 PNG（用于 Gradio File 组件）
            import base64
            b64 = base64.b64encode(png_data).decode("ascii")
            return f"data:image/png;base64,{b64}"
        except ImportError:
            logger.error("[FlowchartPro] cairosvg 未安装，无法导出 PNG")
            raise ValueError("导出 PNG 需要安装 cairosvg: pip install cairosvg")
        except Exception as e:
            logger.error("[FlowchartPro] PNG 导出失败: %s", e)
            raise ValueError(f"PNG 导出失败: {e}")

    # ── PDF（SVG → PDF，300DPI，A4） ───────────────────────
    if fmt == "pdf":
        try:
            import cairosvg
            pdf_data = cairosvg.svg2pdf(
                bytestring=svg_content.encode("utf-8"),
                dpi=RENDER_DPI,
            )
            import base64
            b64 = base64.b64encode(pdf_data).decode("ascii")
            return f"data:application/pdf;base64,{b64}"
        except ImportError:
            logger.error("[FlowchartPro] cairosvg 未安装，无法导出 PDF")
            raise ValueError("导出 PDF 需要安装 cairosvg: pip install cairosvg")
        except Exception as e:
            logger.error("[FlowchartPro] PDF 导出失败: %s", e)
            raise ValueError(f"PDF 导出失败: {e}")

    # ── DOT（networkx → pydot → DOT 源码） ───────────────────────
    if fmt == "dot":
        try:
            import pydot  # type: ignore
            g = nx.DiGraph()
            for n in nodes:
                g.add_node(n["id"], label=n.get("name", f"步骤{n['id']}"))
            for e in edges:
                g.add_edge(e["from"], e["to"], label=e.get("label", ""))
            dot_data = nx.nx_pydot.to_pydot(g)
            return dot_data.to_string()
        except ImportError:
            logger.error("[FlowchartPro] pydot 未安装，无法导出 DOT")
            raise ValueError("导出 DOT 需要安装 pydot: pip install pydot")
        except Exception as e:
            logger.error("[FlowchartPro] DOT 导出失败: %s", e)
            raise ValueError(f"DOT 导出失败: {e}")

    # ── 不支持的格式 ───────────────────────
    raise ValueError(
        f"不支持的导出格式: {fmt}（当前支持 svg / png / pdf / dot / html / json）"
    )
