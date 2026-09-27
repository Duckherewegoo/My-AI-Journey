"""
dash_app.py — 完整 Dash UI + 交互式任务执行
包含：新建任务流式执行 + 历史记录 + 节点交互确认 + 导出 + 图操作优化 + 循环边支持
图片导出方案：PyVis 后端渲染 -> pydot (生成 DOT/SVG) → cairosvg (SVG 转 PNG) → io.BytesIO (内存缓冲) -> dcc.sendbytes 直接传输字节流 -> PNG 下载
"""
from __future__ import annotations

import json
import sys
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Tuple
from dataclasses import dataclass, fields
import hashlib
import dash
from dash import dcc, html, Input, Output, State, callback, clientside_callback, no_update, ctx
import dash_cytoscape as cyto
from task_planner.utils.cytoscape_adapter import _get_edge_type
from task_planner.utils.pyvis_export import export_dag_to_svg
from task_planner.utils.pyvis_export import export_dag_to_png
from task_planner.services.agent import run_task_stream
from task_planner.utils.good_addons import boost
from task_planner.utils.cytoscape_adapter import dag_to_cytoscape, build_detail_markdown, build_history_detail_markdown
from task_planner.core.graph.nodes import sanitize_node_for_user
from task_planner.services.stream_manager import (
    start_stream,
    get_stream_state,
    cancel_stream
)
from task_planner.core.database import (
    init_db,
    list_tasks,
    load_task_with_plan,
    batch_delete_tasks,
    reset_node_status
)
from task_planner.utils.presention_utils import build_history_dropdown_options
from task_planner.infrastructure.config import (
    BASE_BTN_STYLE,
    DASH_DISABLE_VERSION_CHECK,
    STATE_COLORS,
    STATE_LABELS,
    CYTO_STYLESHEET,
    NODE_STATUS_CODE_MAP,
    DASH_HOST,
    DASH_PORT,
    DEBUG,
    EDGE_TYPE_HARD,
    NODE_OPERABLE_STATES,
    PULSE_CSS,
    PROGRESS_CSS,
    MAX_CACHE_INPUT_BYTES,
    BAR_DONE,
    NODE_ACTION_CONFIG,
    GRAPH_CONFIGS,
    BAR_ERROR,
    FIT_JS_TEMPLATE,
    ZOOM_SLIDER_JS_TEMPLATE,
    BAR_LOADING,
    ZOOM_BTN_JS_TEMPLATE,
    EMPTY_BAR_STYLE,
    EMPTY_BAR_MINI_STYLE,
    MARKDOWN_PRE_STYLE,
    VALID_PORT_RANGE
)
from task_planner.infrastructure.logger_setup import get_logger

logger = get_logger("task_planner.dash_app")

cyto.load_extra_layouts()

try:
    init_db()
except Exception as e:
    logger.warning("[Dash] 数据库初始化失败: %s", e)

app = dash.Dash(
    __name__,
    title="🧠 通用任务规划助手",
    assets_folder="assets",
    suppress_callback_exceptions=True,
)
os.environ["DASH_DISABLE_VERSION_CHECK"] = DASH_DISABLE_VERSION_CHECK

@app.server.errorhandler(Exception)
def handle_exception(e):
    logger.exception("❌ Unhandled exception in request")
    raise  # 重新抛出，让 Dash 正常返回 500

# TOOLS

# ══════════════════════════════════════════════════
#  公共基础设施：双源数据解析引擎
# ══════════════════════════════════════════════════

def _resolve_dag_data(history_task_ids, dag_store, node_states_store=None):
    """
    统一的数据源解析引擎（双源适配器）。
    优先级契约：历史持久化数据 > 当前内存 Store。
    
    Returns:
        tuple: (nodes, edges, node_states, task_id_str)
        若数据为空则返回 (None, None, None, None)
    """
    # 统一 task_id 解析
    task_id = None
    if history_task_ids:
        task_id = history_task_ids[0] if isinstance(history_task_ids, list) else history_task_ids

    if task_id:
        try:
            data = load_task_with_plan(task_id)
        except Exception as e:
            logger.error("[Export] 加载历史任务失败 task=%s: %s", task_id, e, exc_info=True)
            data = None

        if data:
            plan = data.get("plan") or {}
            nodes = plan.get("nodes") or []
            edges = plan.get("edges") or []
            # 状态继承：优先使用历史任务保存的状态快照
            node_states = data.get("node_states", node_states_store)
            task_id_str = str(task_id)[-8:]
            return nodes, edges, node_states, task_id_str
        else:
            logger.warning("[Export] 未找到历史任务数据: %s", task_id)
            return None, None, None, None

    # 降级：使用当前内存 Store
    nodes = (dag_store or {}).get("nodes") or []
    edges = (dag_store or {}).get("edges") or []
    return nodes, edges, node_states_store, "current"


def _make_filename(content_type: str, task_id_str: str, ext: str) -> str:
    """统一文件命名规范：{content_type}_{source_id}_{timestamp}.{ext}"""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return f"{content_type}_{task_id_str}_{timestamp}.{ext}"



def _safe_elapsed(task_start_time, now):
    """安全计算耗时，无效起始时间返回 0.0"""
    try:
        start = float(task_start_time)
        if start <= 0:
            return 0.0
        return round(now - start, 1)
    except (TypeError, ValueError):
        return 0.0

def update_node_and_render(dag: dict, node_states: dict, nid: str, target_status: str) -> tuple:
    """
    统一节点状态更新引擎。
    根据 NODE_ACTION_CONFIG 自动处理下游解锁、渲染和统计。
    """
    config = NODE_ACTION_CONFIG.get(target_status)
    if not config:
        raise ValueError(f"未知的节点操作类型: {target_status}")

    new_states = dict(node_states)
    new_states[nid] = target_status

    # 根据配置决定是否解锁下游
    if config["unlock_downstream"]:
        new_states = _auto_unlock_downstream(dag, new_states, nid, target_status)

    # 重新渲染
    nodes = dag.get("nodes", [])
    edges = dag.get("edges", [])
    elements = dag_to_cytoscape(nodes, edges, new_states)

    # 多维统计
    total = len(nodes)
    counts = {s: sum(1 for v in new_states.values() if v == s) for s in ("done", "skipped", "failed")}
    processed = counts["done"] + counts["skipped"]

    status_msg = (
        f"{config['icon']} 节点 {nid} 已标记{config['label']} | "
        f"进度: {processed}/{total} "
        f"(完成:{counts['done']} 跳过:{counts['skipped']} 失败:{counts['failed']})"
    )

    return new_states, elements, status_msg

def _load_and_fill_query(task_ids, action_label: str) -> tuple:
    """
    统一的历史任务回填引擎。
    供 replan / resume 复用，仅通过 action_label 区分提示文案。
    """
    # 统一 task_ids 解析（假设 extract_first_task_id 已在 utils 中定义）
    from task_planner.utils.presentation_utils import extract_first_task_id
    task_id = extract_first_task_id(task_ids)

    if not task_id:
        return "⚠️ 请先选择历史任务", no_update, no_update

    try:
        data = load_task_with_plan(task_id)
    except Exception as e:
        logger.error("[HistoryAction] %s 加载失败 task=%s: %s", action_label, task_id, e, exc_info=True)
        return "❌ 任务数据加载失败，请稍后重试", no_update, no_update

    if not data:
        return "❌ 任务不存在或已被删除", no_update, no_update

    raw_query = (data.get("task") or {}).get("raw_query", "").strip()
    if not raw_query:
        return "⚠️ 该任务无原始需求文本，无法操作", no_update, no_update

    # 差异化文案：resume 强调"可修改后继续"，replan 强调"重新生成"
    if action_label == "继续执行":
        msg = f"▶️ 已回填上次需求（{len(raw_query)}字），可直接继续或修改后重新规划"
    else:
        msg = f"🔄 [{action_label}] 已回填原始需求（{len(raw_query)}字），请确认后点击「开始规划」"

    logger.info("[HistoryAction] %s 回填成功 task=%s query_len=%d", action_label, task_id, len(raw_query))
    return msg, "tab-new", raw_query

# ══════════════════════════════════════════════════
#  返回结构定义（字段顺序与 @callback Output 严格一一对应）
# ══════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class HistorySelectResult:
    """
    on_history_select 返回值自描述容器。

    - frozen=True  : 不可变，语义等价于 NamedTuple
    - slots=True   : 内存紧凑，访问性能优于普通 dataclass
    - 字段声明顺序必须与 @callback Output(...) 列表严格一致
    """
    elements:            Any   = no_update
    detail:              Any   = no_update
    zoom:                float = 0.6
    pan:                 dict  = None
    global_status:       str   = "👋 就绪，等待操作"
    dag_store:           dict  = None
    replan_disabled:     bool  = True
    edit_disabled:       bool  = True
    resume_disabled:     bool  = True
    retry_disabled:      bool  = True
    action_status:       str   = "👆 请先从左侧列表选择一个历史任务"
    history_dag_store:   dict  = None
    history_node_states: dict  = None

    def to_tuple(self) -> tuple:
        """转为有序元组，供 Dash callback 直接 return。"""
        return tuple(getattr(self, f.name) for f in fields(self))

@dataclass(frozen=True, slots=True)
class HistoryTapNodeResult:
    """on_history_tap_node 返回值自描述容器"""
    detail:         Any  = no_update
    selected_node:  str  = no_update
    done_disabled:  bool = True
    skip_disabled:  bool = True
    fail_disabled:  bool = True

    def to_tuple(self) -> tuple:
        """转为有序元组，供 Dash callback 直接 return。"""
        return tuple(getattr(self, f.name) for f in fields(self))

# ══════════════════════════════════════════════════
#  布局
# ══════════════════════════════════════════════════
from task_planner.infrastructure.config import (
    BUTTON_STYLE_PRIMARY,
    BUTTON_STYLE_DANGER,
    BUTTON_STYLE_SECONDARY,
    SECTION_HEADER_STYLE,
    ZOOM_TOOLBAR_STYLE
)

def build_layout() -> html.Div:
    """构建应用主布局"""
    return html.Div([
        # ✅ 优化 1: 使用 html.Style 替代 dcc.Markdown 注入全局样式
        html.Style(PULSE_CSS + PROGRESS_CSS, type="text/css"),
        
        # ═══ 全局状态存储 ═══
        dcc.Interval(id="stream-interval", interval=500, disabled=True, n_intervals=0),
        dcc.Store(id="thread-id-store", data=""),
        dcc.Store(id="stream-active", data=False),
        dcc.Store(id="node-states-store", data={}),
        dcc.Store(id="dag-store", data={"nodes": [], "edges": []}),
        dcc.Store(id="selected-node-store", data=""),
        dcc.Store(id="task-start-time", data=None),
        dcc.Store(id="history-replan-trigger", data=0),  # 用于历史操作回填
        
        # ═══ 导出下载组件 ═══
        dcc.Download(id="export-download"),

        # ═══ 全局导出工具栏 ═══
        html.Div([
            # 图片导出区
            html.Div([
                html.Span("📤 导出图像：", style={
                    "fontSize": "12px", "fontWeight": "bold",
                    "marginRight": "6px", "whiteSpace": "nowrap",
                }),
                dcc.RadioItems(
                    id="image-format",
                    options=[
                        {"label": "PNG", "value": "png"},
                        {"label": "SVG", "value": "svg"},
                    ],
                    value="svg",
                    inline=True,
                    style={"fontSize": "12px", "display": "inline-block", "marginRight": "10px"},
                ),
                html.Button("⬇️ 导出图片", id="export-image-btn", n_clicks=0, style={
                    "padding": "4px 12px", "backgroundColor": "#1a73e8", "color": "white",
                    "border": "none", "borderRadius": "4px", "cursor": "pointer",
                    "fontSize": "12px", "marginRight": "20px",
                }),
            ], style={"display": "inline-block", "marginRight": "15px", "marginBottom": "5px"}),
            
            # 数据导出区
            html.Div([
                html.Span("📤 导出数据：", style={
                    "fontSize": "12px", "fontWeight": "bold",
                    "marginRight": "6px", "whiteSpace": "nowrap",
                }),
                dcc.RadioItems(
                    id="data-format",
                    options=[
                        {"label": "JSON", "value": "json"},
                        {"label": "DOT", "value": "dot"},
                        {"label": "HTML", "value": "html"},
                    ],
                    value="json",
                    inline=True,
                    style={"fontSize": "12px", "display": "inline-block", "marginRight": "10px"},
                ),
                html.Button("⬇️ 导出数据", id="export-data-btn", n_clicks=0, style={
                    "padding": "4px 12px", "backgroundColor": "#10b981", "color": "white",
                    "border": "none", "borderRadius": "4px", "cursor": "pointer",
                    "fontSize": "12px",
                }),
            ], style={"display": "inline-block", "marginBottom": "5px"}),
        ], style={
            "textAlign": "right", "backgroundColor": "white",
            "padding": "8px 15px", "borderRadius": "8px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.1)",
            "marginBottom": "15px", "flexWrap": "wrap",
        }),

        # ═══ 页面标题 ═══
        html.H1("🧠 通用任务规划助手", style={
            "textAlign": "center", "marginBottom": "5px", "color": "#1e293b",
        }),
        html.P("输入任务需求，AI 自动分解为 DAG 流程图，逐步确认执行", style={
            "textAlign": "center", "color": "#64748b", "marginBottom": "10px",
        }),

        # ═══ 全局状态栏 ═══
        html.Div(id="global-status", children="👋 就绪，等待操作", style={
            "marginBottom": "8px", "fontWeight": "bold", "fontSize": "14px",
            "color": "#1e293b", "textAlign": "center",
        }),
        
        # 进度条
        html.Div([
            html.Div(id="progress-bar-fill", style={
                "width": "0%", "height": "100%",
                "background": "linear-gradient(90deg, #10b981, #34d399)",
                "borderRadius": "6px", "transition": "width 0.5s ease",
            }),
        ], style={
            "width": "60%", "height": "8px", "backgroundColor": "#e2e8f0",
            "borderRadius": "6px", "margin": "0 auto 15px auto", "overflow": "hidden",
        }),

        # ═══ 主标签页 ═══
        dcc.Tabs(id="main-tabs", value="tab-new", children=[
            # ──────────────────────────────────────
            #  Tab 1: 新建任务
            # ──────────────────────────────────────
            dcc.Tab(label="🚀 新建任务", value="tab-new", children=[
                html.Div([
                    # 输入区
                    html.Div([
                        dcc.Textarea(
                            id="user-input",
                            placeholder="输入任务需求，例如：教我做甜口西红柿炒鸡蛋（最多 2000 字符）",
                            style={
                                "width": "100%", "height": "90px", "fontSize": "14px",
                                "padding": "10px", "borderRadius": "8px",
                                "border": "1px solid #d1d5db",
                            },
                        ),
                        dcc.Checklist(
                            id="enable-refine",
                            options=[{"label": "🔧 节点细化", "value": "refine"}],
                            value=["refine"],
                            style={"marginTop": "10px"},
                        ),
                    ], style={"marginBottom": "15px"}),

                    # 任务控制区
                    html.Div([
                        html.Div("📋 任务控制", style=SECTION_HEADER_STYLE),
                        html.Div([
                            html.Button("🚀 开始规划", id="submit-btn", n_clicks=0,
                                       style=BUTTON_STYLE_PRIMARY),
                            html.Button("⏹️ 停止", id="stop-btn", n_clicks=0, disabled=True,
                                       style=BUTTON_STYLE_DANGER),
                            html.Button("▶️ 继续", id="resume-btn", n_clicks=0, disabled=True,
                                       style=BUTTON_STYLE_SECONDARY),
                        ]),
                    ], style={
                        "padding": "14px 18px", "backgroundColor": "#eff6ff",
                        "border": "1px solid #bfdbfe", "borderRadius": "10px",
                        "marginBottom": "12px",
                    }),

                    # 节点操作区
                    html.Div([
                        html.Div("🎯 节点操作（先点击流程图中的节点，再选择操作）",
                                style=SECTION_HEADER_STYLE),
                        html.Div([
                            html.Button("▶️ 开始执行选中节点", id="start-exec-btn",
                                       n_clicks=0, disabled=True, style={
                                "backgroundColor": "#10b981", "color": "white",
                                "border": "none", "padding": "12px 20px",
                                "borderRadius": "8px", "cursor": "pointer",
                                "fontSize": "14px", "fontWeight": "bold",
                                "marginRight": "10px",
                            }),
                            html.Button("⏭️ 跳过选中节点", id="skip-btn",
                                       n_clicks=0, disabled=True, style={
                                "backgroundColor": "#6366f1", "color": "white",
                                "border": "none", "padding": "12px 20px",
                                "borderRadius": "8px", "cursor": "pointer",
                                "fontSize": "14px", "fontWeight": "bold",
                                "marginRight": "10px",
                            }),
                            html.Button("❌ 做不到", id="fail-btn",
                                       n_clicks=0, disabled=True, style={
                                "backgroundColor": "#ef4444", "color": "white",
                                "border": "none", "padding": "12px 20px",
                                "borderRadius": "8px", "cursor": "pointer",
                                "fontSize": "14px", "fontWeight": "bold",
                            }),
                        ]),
                        html.Div(id="node-action-hint",
                                children="👆 请先在流程图中点击一个高亮（蓝色）节点",
                                style={
                                    "fontSize": "13px", "color": "#94a3b8",
                                    "marginTop": "8px", "fontStyle": "italic",
                                }),
                    ], style={
                        "padding": "14px 18px", "backgroundColor": "#f0fdf4",
                        "border": "1px solid #bbf7d0", "borderRadius": "10px",
                        "marginBottom": "15px",
                    }),

                    # 图操作工具栏
                    html.Div([
                        html.Button("⊡ 适应窗口", id="fit-btn", n_clicks=0,
                                   style={**ZOOM_TOOLBAR_STYLE, "marginRight": "8px"}),
                        html.Button("＋ 放大", id="zoom-in-btn", n_clicks=0,
                                   style={**ZOOM_TOOLBAR_STYLE, "marginRight": "4px"}),
                        html.Button("－ 缩小", id="zoom-out-btn", n_clicks=0,
                                   style={**ZOOM_TOOLBAR_STYLE, "marginRight": "8px"}),
                        html.Div(
                            dcc.Slider(
                                id="zoom-slider", min=0.2, max=4.0, step=0.1, value=0.6,
                                marks={0.2: "20%", 0.6: "60%", 1: "100%", 2: "200%", 4: "400%"},
                                tooltip={"placement": "bottom", "always_visible": True},
                            ),
                            style={"width": "200px", "display": "inline-block",
                                   "verticalAlign": "middle"},
                        ),
                    ], style={"marginBottom": "10px"}),

                    # 流程图
                    cyto.Cytoscape(
                        id="flowchart",
                        elements=[],
                        layout={
                            "name": "dagre", "rankDir": "TB",
                            "nodeSep": 300, "rankSep": 450, "edgeSep": 80,
                            "fit": True, "padding": 80,
                        },
                        style={
                            "width": "100%", "height": "700px",
                            "border": "1px solid #e2e8f0", "borderRadius": "12px",
                        },
                        stylesheet=CYTO_STYLESHEET,
                        userZoomingEnabled=True,
                        userPanningEnabled=True,
                        boxSelectionEnabled=False,
                        autoungrabify=False,
                        minZoom=0.2, maxZoom=4.0, zoom=0.6,
                    ),

                    # 节点详情面板
                    html.Div(id="node-detail-panel", children=[
                        dcc.Markdown("👆 **点击流程图中的节点查看详情并操作**",
                                    style={"fontSize": "14px", "color": "#94a3b8"})
                    ], style={
                        "marginTop": "15px", "padding": "18px",
                        "border": "1px solid #e2e8f0", "borderRadius": "12px",
                        "backgroundColor": "#f8fafc", "minHeight": "160px",
                        "fontSize": "14px", "lineHeight": "1.8",
                    }),
                ], style={"padding": "25px", "maxWidth": "1400px", "margin": "0 auto"}),
            ]),

            # ──────────────────────────────────────
            #  Tab 2: 历史记录
            # ──────────────────────────────────────
            dcc.Tab(label="📜 历史记录", value="tab-history", children=[
                html.Div([
                    # 左侧：任务列表
                    html.Div([
                        html.H3("📋 任务列表", style={"marginTop": "0"}),
                        html.Button("🔄 刷新列表", id="refresh-btn", n_clicks=0, style={
                            "width": "100%", "padding": "10px", "backgroundColor": "#f1f5f9",
                            "border": "1px solid #d1d5db", "borderRadius": "6px",
                            "cursor": "pointer", "marginBottom": "12px",
                        }),
                        dcc.Dropdown(
                            id="history-dropdown",
                            options=[],
                            placeholder="选择历史任务（可多选删除）",
                            multi=True,
                            style={"marginBottom": "12px"},
                        ),
                        html.Button("🗑️ 删除选中", id="delete-btn", n_clicks=0, style={
                            "width": "100%", "padding": "10px", "backgroundColor": "#ef4444",
                            "color": "white", "border": "none", "borderRadius": "6px",
                            "cursor": "pointer", "marginBottom": "10px",
                        }),
                        html.Div(id="delete-status", style={"fontSize": "13px", "color": "#059669"}),
                    ], style={
                        "width": "28%", "display": "inline-block", "verticalAlign": "top",
                        "padding": "20px", "borderRight": "1px solid #e2e8f0",
                    }),

                    # 右侧：详情与操作
                    html.Div([
                        # 历史任务操作区
                        html.Div([
                            html.Div("🎮 任务控制（基于历史任务）", style=SECTION_HEADER_STYLE),
                            html.Div([
                                html.Button("🔄 重新规划", id="history-replan-btn",
                                           n_clicks=0, disabled=True, style={
                                    "backgroundColor": "#1a73e8", "color": "white",
                                    "border": "none", "padding": "10px 18px",
                                    "borderRadius": "6px", "cursor": "pointer",
                                    "fontSize": "13px", "fontWeight": "bold",
                                    "marginRight": "8px",
                                }),
                                html.Button("✏️ 修改规划", id="history-edit-plan-btn",
                                           n_clicks=0, disabled=True, style={
                                    "backgroundColor": "#8b5cf6", "color": "white",
                                    "border": "none", "padding": "10px 18px",
                                    "borderRadius": "6px", "cursor": "pointer",
                                    "fontSize": "13px", "fontWeight": "bold",
                                    "marginRight": "8px",
                                }),
                                html.Button("▶️ 继续执行", id="history-resume-btn",
                                           n_clicks=0, disabled=True, style={
                                    "backgroundColor": "#10b981", "color": "white",
                                    "border": "none", "padding": "10px 18px",
                                    "borderRadius": "6px", "cursor": "pointer",
                                    "fontSize": "13px", "fontWeight": "bold",
                                    "marginRight": "8px",
                                }),
                                html.Button("🔁 重试失败节点", id="history-retry-btn",
                                           n_clicks=0, disabled=True, style={
                                    "backgroundColor": "#f59e0b", "color": "white",
                                    "border": "none", "padding": "10px 18px",
                                    "borderRadius": "6px", "cursor": "pointer",
                                    "fontSize": "13px", "fontWeight": "bold",
                                }),
                            ]),
                            html.Div(id="history-action-status",
                                    children="👆 请先从左侧列表选择一个历史任务",
                                    style={
                                        "fontSize": "12px", "color": "#94a3b8",
                                        "marginTop": "8px", "fontStyle": "italic",
                                    }),
                        ], style={
                            "padding": "14px 18px", "backgroundColor": "#eff6ff",
                            "border": "1px solid #bfdbfe", "borderRadius": "10px",
                            "marginBottom": "15px",
                        }),

                        # 历史节点操作区
                        html.Div([
                            html.Div("🎯 节点操作（先点击历史流程图中的节点）",
                                    style=SECTION_HEADER_STYLE),
                            html.Div([
                                html.Button("✅ 标记完成", id="history-node-done-btn",
                                           n_clicks=0, disabled=True, style={
                                    "backgroundColor": "#10b981", "color": "white",
                                    "border": "none", "padding": "10px 18px",
                                    "borderRadius": "6px", "cursor": "pointer",
                                    "fontSize": "13px", "fontWeight": "bold",
                                    "marginRight": "8px",
                                }),
                                html.Button("⏭️ 跳过", id="history-node-skip-btn",
                                           n_clicks=0, disabled=True, style={
                                    "backgroundColor": "#6366f1", "color": "white",
                                    "border": "none", "padding": "10px 18px",
                                    "borderRadius": "6px", "cursor": "pointer",
                                    "fontSize": "13px", "fontWeight": "bold",
                                    "marginRight": "8px",
                                }),
                                html.Button("❌ 标记失败", id="history-node-fail-btn",
                                           n_clicks=0, disabled=True, style={
                                    "backgroundColor": "#ef4444", "color": "white",
                                    "border": "none", "padding": "10px 18px",
                                    "borderRadius": "6px", "cursor": "pointer",
                                    "fontSize": "13px", "fontWeight": "bold",
                                }),
                            ]),
                            dcc.Store(id="history-selected-node-store", data=""),
                            dcc.Store(id="history-dag-store", data={"nodes": [], "edges": []}),
                            dcc.Store(id="history-node-states-store"),
                        ]),

                        # 流程图与详情
                        html.Div([
                            html.H3("🗺️ 流程图", style={"marginTop": "0"}),
                            
                            # 图操作工具栏
                            html.Div([
                                html.Button("⊡ 适应窗口", id="history-fit-btn",
                                           n_clicks=0, style={
                                    **ZOOM_TOOLBAR_STYLE, "marginRight": "8px"
                                }),
                                html.Button("＋ 放大", id="history-zoom-in-btn",
                                           n_clicks=0, style={
                                    **ZOOM_TOOLBAR_STYLE, "marginRight": "4px"
                                }),
                                html.Button("－ 缩小", id="history-zoom-out-btn",
                                           n_clicks=0, style={
                                    **ZOOM_TOOLBAR_STYLE, "marginRight": "8px"
                                }),
                                html.Div(
                                    dcc.Slider(
                                        id="history-zoom-slider",
                                        min=0.2, max=4.0, step=0.1, value=0.6,
                                        marks={0.2: "20%", 0.6: "60%", 1: "100%",
                                               2: "200%", 4: "400%"},
                                        tooltip={"placement": "bottom", "always_visible": True},
                                    ),
                                    style={
                                        "width": "200px", "display": "inline-block",
                                        "verticalAlign": "middle",
                                    },
                                ),
                            ], style={"marginBottom": "10px"}),

                            # 历史流程图
                            cyto.Cytoscape(
                                id="history-flowchart",
                                elements=[],
                                layout={
                                    "name": "dagre", "rankDir": "TB",
                                    "nodeSep": 250, "rankSep": 380, "edgeSep": 60,
                                    "fit": True, "padding": 60,
                                },
                                style={
                                    "width": "100%", "height": "450px",
                                    "border": "1px solid #e2e8f0", "borderRadius": "12px",
                                    "marginBottom": "15px",
                                },
                                stylesheet=CYTO_STYLESHEET,
                                minZoom=0.2, maxZoom=4.0, zoom=0.6,
                                userZoomingEnabled=True,
                                userPanningEnabled=True,
                            ),

                            # 节点详情
                            html.Div([
                                html.H4("🎯 节点详情", style={"margin": "0 0 8px", "fontSize": "14px"}),
                                html.Div(id="history-node-detail", children=[
                                    dcc.Markdown("**点击流程图中的节点查看详情**")
                                ], style={
                                    "padding": "10px", "border": "1px solid #e2e8f0",
                                    "borderRadius": "8px", "backgroundColor": "#f8fafc",
                                    "minHeight": "80px", "fontSize": "13px",
                                    "marginBottom": "10px",
                                }),
                            ], style={"marginBottom": "15px"}),

                            # 任务详情
                            html.H3("📝 任务详情"),
                            html.Div(id="history-detail", style={
                                "whiteSpace": "pre-wrap", "padding": "15px",
                                "border": "1px solid #e2e8f0", "borderRadius": "8px",
                                "backgroundColor": "#f8fafc", "fontSize": "14px",
                                "lineHeight": "1.8",
                            }),
                        ], style={
                            "width": "68%", "display": "inline-block",
                            "padding": "20px", "verticalAlign": "top",
                        }),
                    ]),
                ]),
            ]),
        ]),
    ])

app.layout = build_layout()

# ══════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════

def _auto_unlock_downstream(dag, node_states, changed_nid, new_state, allowed_edge_types=None):
    """
    通用下游建议性解锁引擎。根据触发状态(new_state)差异化处理边类型：

    - done:    仅检查 hard 边，全部 done → 下游解锁为 running
    - skipped/failed: 若未指定 allowed_edge_types，默认行为与 done 一致（仅 hard 边）
                      调用方可通过 allowed_edge_types 自定义检查范围

    ⚠️ 绝不自动将下游设为 skipped/failed，仅做建议性 unlock
    ⚠️ 仅依赖 EDGE_TYPE_HARD，不引入任何未经项目定义的边类型常量
    """
    edges = dag.get("edges", [])
    new_states = dict(node_states or {})

    # ── 1. 确定需要检查的边类型集合 ──
    if allowed_edge_types is not None:
        check_edge_types = set(allowed_edge_types)
    elif new_state == "done":
        check_edge_types = {EDGE_TYPE_HARD}
    else:
        # skipped / failed / 其他状态：未显式指定时，保守地仅检查 hard 边
        # 调用方（如 on_fail_node）应主动传入 allowed_edge_types 以覆盖此默认行为
        check_edge_types = {EDGE_TYPE_HARD}

    # ── 2. 单次遍历收集直接下游及其相关入边 ──
    downstream_edges_map = {}
    for e in edges:
        src, tgt = str(e.get("from", "")), str(e.get("to", ""))
        if src == changed_nid and _get_edge_type(e) in check_edge_types:
            downstream_edges_map.setdefault(tgt, []).append(e)

    # ── 3. 逐下游判断是否可解锁 ──
    for tgt, relevant_in_edges in downstream_edges_map.items():
        current_state = new_states.get(tgt, "pending")
        if current_state not in ("pending", "blocked"):
            continue

        all_satisfied = all(
            new_states.get(str(e["from"])) == "done"
            for e in relevant_in_edges
        )
        if all_satisfied:
            new_states[tgt] = "running"

    return new_states


def _generate_html_export(nodes, edges, task_id):
    import textwrap
    # 1. 构建元素列表（保持原有的防御性字段访问）
    elements_list = []
    for i, n in enumerate(nodes):
        nid = str(n.get("id", i))
        label = n.get("name", n.get("node_name", f"Node {i}"))
        detail = n.get("detail", n.get("details", ""))
        elements_list.append({"data": {"id": nid, "label": label, "detail": detail}})

    for i, e in enumerate(edges):
        elements_list.append({
            "data": {
                "id": f"e{i}",
                "source": str(e["from"]),
                "target": str(e["to"]),
                "label": e.get("label", ""),
            }
        })

    # 2. 安全序列化：防止 </script> 注入导致 XSS
    safe_json = json.dumps(elements_list, ensure_ascii=False).replace("</", r"<\/")

    # 3. 使用 dedent + f-string 生成 HTML
    return textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>流程图 {task_id}</title>
            <script src="https://unpkg.com/cytoscape@3.28.1/dist/cytoscape.min.js"></script>
            <script src="https://unpkg.com/cytoscape-dagre@2.5.0/cytoscape-dagre.js"></script>
            <style>
                body {{ margin: 0; font-family: Arial; }}
                #cy {{ width: 100%; height: 100vh; }}
            </style>
        </head>
        <body>
            <div id="cy"></div>
            <script>
                var cy = cytoscape({{
                    container: document.getElementById('cy'),
                    elements: {safe_json},
                    layout: {{ name: 'dagre', rankDir: 'TB', nodeSep: 300, rankSep: 450 }},
                    style: [
                        {{
                            selector: 'node',
                            style: {{
                                'label': 'data(label)',
                                'text-valign': 'center',
                                'text-halign': 'center',
                                'font-size': 13,
                                'shape': 'round-rectangle',
                                'padding': 12,
                                'background-color': '#dbeafe',
                                'border-color': '#3b82f6',
                                'border-width': 2
                            }}
                        }},
                        {{
                            selector: 'edge',
                            style: {{
                                'curve-style': 'bezier',
                                'target-arrow-shape': 'triangle',
                                'label': 'data(label)',
                                'font-size': 11
                            }}
                        }}
                    ]
                }});
            </script>
        </body>
        </html>
    """)

# ══════════════════════════════════════════════════
#  全局缓存（纯计算结果，无用户会话绑定，线程安全）
# ══════════════════════════════════════════════════
_cyto_cache: Dict[str, Any] = {"hash": None, "elements": None}
_cyto_lock = threading.Lock()

# 缓存上限：超过此大小的输入跳过缓存，防止内存膨胀
_MAX_CACHE_INPUT_BYTES = MAX_CACHE_INPUT_BYTES


def _stable_fingerprint(
    nodes: List[dict],
    edges: List[dict],
    node_states: Dict[str, str],
) -> Tuple[str, int]:
    """
    生成确定性指纹，替代全量 json.dumps + md5。
    
    优化策略：
    - nodes/edges 结构变更频率远低于 node_states，
      用 (len, id_tuple) 代替全量序列化即可检测拓扑变化。
    - node_states 是高频变更部分，单独排序序列化。
    - 返回 (hash_hex, raw_byte_length) 供大小守卫使用。
    
    安全性：
    - 不使用 default=str，遇到不可序列化类型立即报错，
      避免语义不同的对象被错误地映射到同一指纹。
    """
    try:
        # 拓扑指纹：节点数 + 边数 + 有序ID元组（轻量且确定性）
        node_ids = tuple(sorted(str(n.get("id", i)) for i, n in enumerate(nodes)))
        edge_keys = tuple(
            sorted((str(e["from"]), str(e["to"]), e.get("label", "")) for e in edges)
        )
        topo_part = f"{len(nodes)}|{len(edges)}|{node_ids}|{edge_keys}"

        # 状态指纹：排序后的键值对（node_states 值应为 str，无需 default）
        state_part = json.dumps(node_states, sort_keys=True, ensure_ascii=False)

        raw = f"{topo_part}||{state_part}"
        raw_bytes = raw.encode("utf-8")
        return hashlib.md5(raw_bytes).hexdigest(), len(raw_bytes)

    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"Cache fingerprint failed: node_states contains non-serializable value. "
            f"All values must be str. Got error: {exc}"
        ) from exc


def _cytoscape_cached(
    nodes: List[dict],
    edges: List[dict],
    node_states: Dict[str, str],
) -> list:
    """
    带内容寻址缓存的 Cytoscape 元素转换器。
    
    安全保证：
    1. 线程安全：Lock 保护读写，兼容多 Worker/多线程部署。
    2. 类型严格：拒绝不可序列化类型，杜绝 default=str 的语义碰撞。
    3. 内存守卫：超大输入自动跳过缓存，防止 OOM。
    4. 确定性哈希：sort_keys + 结构化指纹，保证语义等价 → 哈希等价。
    """
    # ── Step 1: 生成指纹（在锁外执行，减少持锁时间）──
    fingerprint, raw_size = _stable_fingerprint(nodes, edges, node_states)

    # ── Step 2: 大小守卫 ──
    if raw_size > _MAX_CACHE_INPUT_BYTES:
        # 超大图直接计算，不写入缓存
        from task_planner.utils.cytoscape_adapter import dag_to_cytoscape
        return dag_to_cytoscape(nodes, edges, node_states)

    # ── Step 3: 线程安全的缓存查找与更新 ──
    with _cyto_lock:
        if (
            fingerprint == _cyto_cache["hash"]
            and _cyto_cache["elements"] is not None
        ):
            return _cyto_cache["elements"]

        # Cache miss：执行昂贵转换
        from task_planner.utils.cytoscape_adapter import dag_to_cytoscape
        elements = dag_to_cytoscape(nodes, edges, node_states)

        # 写入缓存
        _cyto_cache["hash"] = fingerprint
        _cyto_cache["elements"] = elements
        return elements

# ══════════════════════════════════════════════════
#  Callbacks
# ══════════════════════════════════════════════════
@callback(
    Output("node-action-hint", "children"),
    Output("node-action-hint", "style"),
    Input("flowchart", "tapNodeData"),
    State("node-states-store", "data"),
    State("dag-store", "data"),
    # ⚠️ 移除 prevent_initial_call=True，让 not node_data 分支处理首屏状态
)
def on_node_hint(node_data, node_states, dag):
    from task_planner.infrastructure.config import HINT_TEMPLATES, HINT_STYLES
    from task_planner.core.graph.state import NodeStatus
    _STYLES = HINT_STYLES
    # ── 系统级状态提示（与具体节点无关）──
    if not dag or not dag.get("nodes"):
        return (
            HINT_TEMPLATES.get("loading", "⏳ 加载中..."),
            _STYLES.get("loading", {"color": "#94a3b8", "fontSize": "14px"}),
        )

    if not node_data:
        return HINT_TEMPLATES["ready"], _STYLES["ready"]
    
    # ── 节点级状态提示 ──
    nid = str(node_data.get("id", ""))
    raw_st = node_states.get(nid, NodeStatus.PENDING)

    # 安全地将原始值映射为枚举成员，非法值自动降级为 PENDING
    try:
        status = NodeStatus(raw_st)
    except (ValueError, KeyError):
        status = NodeStatus.PENDING

    template_key = status.value  # e.g. "running", "done", "pending"
    text = HINT_TEMPLATES.get(template_key, HINT_TEMPLATES["pending"]).format(nid=nid)
    style = _STYLES.get(template_key, _STYLES["pending"])

    return text, style

# 节点 hover
@app.callback(
    Output("flowchart", "className"),  # 或使用 setProps
    Input("flowchart", "mouseoverNodeData"),
    Input("flowchart", "mouseoutNodeData"),
    prevent_initial_call=True,
)
def on_node_hover(over_data, out_data):
    ctx = dash.callback_context.triggered_id
    if ctx == "flowchart" and over_data:
        # 通过 patch 或直接操作 elements 添加 .node-hover 类
        return dash.Patch({"addClasses": f"#node-{over_data['id']}.node-hover"})
    return dash.no_update


@callback(
    Output("thread-id-store", "data"), Output("stream-interval", "disabled"),
    Output("stream-active", "data"), Output("global-status", "children"),
    Output("flowchart", "elements"), Output("submit-btn", "disabled"),
    Output("stop-btn", "disabled"), Output("start-exec-btn", "disabled"),
    Output("dag-store", "data"), Output("node-states-store", "data"),
    Output("progress-bar-fill", "style"), Output("task-start-time", "data"),
    Input("submit-btn", "n_clicks"),
    State("user-input", "value"), State("enable-refine", "value"),
    prevent_initial_call=True,
)
def on_submit(n_clicks, user_input, refine_value):
    from task_planner.infrastructure.config import EMPTY_BAR_STYLE, EMPTY_DAG, EMPTY_STATES, MAX_INPUT_LENGTH
    # ── 输入校验 ──
    if not user_input or not user_input.strip():
        return ("", True, False, "⚠️ 请输入任务需求", [], False, True, True,
                EMPTY_DAG, EMPTY_STATES, EMPTY_BAR_STYLE, 0.0)

    cleaned = user_input.strip()
    if len(cleaned) > MAX_INPUT_LENGTH:
        return ("", True, False, f"⚠️ 输入过长（{len(cleaned)}字），请精简至 {MAX_INPUT_LENGTH} 字以内",
                [], False, True, True, EMPTY_DAG, EMPTY_STATES, EMPTY_BAR_STYLE, 0.0)

    # ── 状态解析 ──
    thread_id = str(uuid.uuid4())
    enable_refine = isinstance(refine_value, list) and "refine" in refine_value

    # ── 启动异步流式任务（带异常守卫）──
    try:
        start_stream(
            thread_id=thread_id,
            user_input=cleaned,
            enable_refine=enable_refine,
            run_task_stream_fn=run_task_stream,
        )
    except Exception as e:
        return ("", True, False, f"❌ 任务启动失败: {e}", [], False, True, True,
                EMPTY_DAG, EMPTY_STATES, EMPTY_BAR_STYLE, 0.0)

    # ── 返回"运行态" UI 状态 ──
    return (
        thread_id,          # thread-id-store
        False,              # stream-interval (启用轮询)
        True,               # stream-active (标记流式进行中)
        "🚀 任务已提交，正在生成流程图...",
        [],                 # flowchart elements (清空旧图)
        True,               # submit-btn disabled
        False,              # stop-btn enabled
        True,               # start-exec-btn disabled
        EMPTY_DAG,          # dag-store (清空)
        EMPTY_STATES,       # node-states-store (清空)
        EMPTY_BAR_STYLE,    # progress-bar (归零)
        time.time(),        # task-start-time
    )

@callback(
    Output("flowchart", "elements", allow_duplicate=True),
    Output("global-status", "children", allow_duplicate=True),
    Output("stream-interval", "disabled", allow_duplicate=True),
    Output("submit-btn", "disabled", allow_duplicate=True),
    Output("stop-btn", "disabled", allow_duplicate=True),
    Output("start-exec-btn", "disabled", allow_duplicate=True),
    Output("dag-store", "data", allow_duplicate=True),
    Output("progress-bar-fill", "style", allow_duplicate=True),
    Input("stream-interval", "n_intervals"),
    State("thread-id-store", "data"),
    State("stream-active", "data"),
    State("task-start-time", "data"),
    prevent_initial_call=True,
)
def poll_stream_progress(n_intervals, thread_id, stream_active, task_start_time):
    now = time.time()
    elapsed = _safe_elapsed(task_start_time, now)

    # ── 1. 前置守卫：无效状态立即禁用 interval ──
    if not stream_active or not thread_id:
        return (no_update, no_update, True, False, True, True,
                no_update, EMPTY_BAR_MINI_STYLE)

    state = get_stream_state(thread_id)
    if not state:
        return (no_update, f"⚠️ 任务状态丢失 (⏱️ {elapsed}s)", True, False, True, True,
                no_update, EMPTY_BAR_MINI_STYLE)


    latest = state.get_latest()

    # ── 2. direct_response 快捷路径 ──
    direct_response = latest.get("direct_response", "")
    if direct_response:
        msg = f"💬 {direct_response}\n\n⏱️ 总耗时 {elapsed}s"
        return ([], dcc.Markdown(msg, style=MARKDOWN_PRE_STYLE),
                True, False, True, True, no_update,
                EMPTY_BAR_STYLE)

    # ── 3. ⭐ 带缓存的转换（核心修复）──
    nodes = latest.get("nodes") or []
    edges = latest.get("edges") or []
    node_states = latest.get("node_states") or {}
    dag = {"nodes": nodes, "edges": edges}
    elements = _cytoscape_cached(nodes, edges, node_states)   # ← 数据没变就跳过

    # ── 4. 状态文本 ──
    status_text = str(latest.get("status_text", ""))
    if not status_text:
        steps = latest.get("steps", [])
        status_text = steps[-1] if steps else "处理中..."
    status_text = f"{status_text} (⏱️ {elapsed}s)"

    # ── 5. 完成/失败 → 禁用 interval ──
    if state.finished:
        if state.error:
            return (
                elements,
                f"❌ 任务失败: {state.error} (⏱️ {elapsed}s)",
                True, False, True, True, dag,
                BAR_ERROR,
            )
        return (
            elements,
            "✅ 流程图渲染完成！请先在图中点击一个高亮（黄色）节点，再选择操作",
            True, False, True, False, dag,
            BAR_DONE,
        )

    # ── 6. 进行中 ──
    return (elements, status_text, False, True, False, True, dag,
            BAR_LOADING)

# dash_app.py - on_stop 回调优化
@callback(
    Output("stream-interval", "disabled", allow_duplicate=True),
    Output("global-status", "children", allow_duplicate=True),
    Output("submit-btn", "disabled", allow_duplicate=True),
    Output("stop-btn", "disabled", allow_duplicate=True),
    Output("resume-btn", "disabled"),
    Input("stop-btn", "n_clicks"),
    State("thread-id-store", "data"),
    prevent_initial_call=True,
)
def on_stop(n_clicks, thread_id):
    # ── 防御性校验 ──
    if not thread_id:
        return (True, "⚠️ 没有正在运行的任务", False, True, True)

    # ── 安全执行取消操作 ──
    try:
        cancel_stream(thread_id)
        status_msg = "⏹️ 任务已取消（后端 LLM 调用将在下次响应前终止）"
        resume_disabled = True  # ⭐ 取消后默认禁用恢复，除非确认支持断点续传
    except Exception as e:
        logger.exception(f"Failed to cancel stream {thread_id}")
        status_msg = f"❌ 取消失败: {e}（任务可能仍在后台运行）"
        resume_disabled = True

    return (
        True,               # stream-interval disabled
        status_msg,         # global-status
        False,              # submit-btn enabled (允许重新提交)
        True,               # stop-btn disabled
        resume_disabled,    # resume-btn
    )

@callback(
    Output("node-states-store", "data", allow_duplicate=True),
    Output("flowchart", "elements", allow_duplicate=True),
    Output("global-status", "children", allow_duplicate=True),
    Output("start-exec-btn", "disabled", allow_duplicate=True),
    Input("start-exec-btn", "n_clicks"),
    State("dag-store", "data"),
    State("node-states-store", "data"),
    prevent_initial_call=True,
)
def on_start_execution(n_clicks, dag, node_states):
    # ── 1. 前置校验 ──
    if not dag or not dag.get("nodes"):
        return no_update, no_update, "⚠️ 没有可执行的任务", True

    nodes = dag["nodes"]
    edges = dag.get("edges", [])
    valid_ids = {str(n["id"]) for n in nodes}

    # ── 2. 安全计算入度（过滤悬空边）──
    in_deg = {}
    for e in edges:
        target = str(e.get("to", ""))
        if target in valid_ids:  # ⭐ 只统计指向合法节点的边
            in_deg[target] = in_deg.get(target, 0) + 1

    # ── 3. 初始化根节点状态 ──
    new_states = dict(node_states or {})  # ⭐ 防御 None
    for node in nodes:
        nid = str(node["id"])
        if nid not in new_states and in_deg.get(nid, 0) == 0:
            new_states[nid] = "running"

    # ── 4. 带缓存的渲染 ──
    elements = _cytoscape_cached(nodes, edges, new_states)  # ⭐ 统一使用缓存版本

    # ── 5. 智能状态文案 ──
    running_count = sum(1 for v in new_states.values() if v == "running")
    if running_count > 0:
        status_msg = f"▶️ 正在执行 {running_count} 个根节点，完成后点击节点标记状态"
    else:
        status_msg = "⚠️ 未找到可执行的根节点（可能存在循环依赖），请检查流程图"

    return new_states, elements, status_msg, True

@callback(
    Output("node-detail-panel", "children"),
    Output("selected-node-store", "data"),
    # ⭐ 移除了错误的 skip-btn 和 fail-btn Output
    Input("flowchart", "tapNodeData"),
    State("dag-store", "data"),
    State("node-states-store", "data"),
)
def on_tap_node(node_data, dag, node_states):
    # ── 1. 空值与粘滞防御 ──
    if not node_data or not node_data.get("id"):
        return dcc.Markdown("👆 **点击流程图中的节点查看详情并操作**",
                            style={"fontSize": "14px", "color": "#94a3b8"}), no_update

    nid = str(node_data["id"])
    node_states = node_states or {}
    st = str(node_states.get(nid, "pending"))

    # ── 2. 构建详情文本 ──
    md_text = build_detail_markdown(dict(node_data))  # 假设此函数已存在
    current_label = STATE_LABELS.get(st, st)

    # ── 3. 动态生成按钮（复用基础样式）──
    def make_btn(label, btn_id, state_key):
        bg, color = STATE_COLORS.get(state_key, ("#e2e8f0", "#475569"))
        is_active = (st == state_key)
        style = {
            **BASE_BTN_STYLE,
            "backgroundColor": bg if is_active else "#e2e8f0",
            "color": color if is_active else "#475569",
            "opacity": "1" if is_active else "0.8",
        }
        return html.Button(label, id=btn_id, n_clicks=0, style=style)

    buttons = [
        make_btn("✅ 完成", "complete-btn", "done"),
        make_btn("⏭️ 跳过", "skip-btn-panel", "skipped"),
        make_btn("❌ 失败", "fail-btn-panel", "failed"),
        html.Button("🔄 重置", id="reset-btn-panel", n_clicks=0,
                    style={**BASE_BTN_STYLE, "backgroundColor": "#e2e8f0", "color": "#475569"}),
    ]

    # ── 4. 组装面板 ──
    panel_children = [
        html.Div(f"当前状态: {current_label}", style={
            "fontSize": "13px", "color": "#64748b", "marginBottom": "8px", "fontWeight": "bold",
        }),
        dcc.Markdown(md_text, style={"fontSize": "14px", "lineHeight": "1.8"}),
        html.Div(buttons, style={"marginTop": "12px"}),
    ]

    return html.Div(panel_children), nid

@callback(
    Output("node-states-store", "data", allow_duplicate=True),
    Output("flowchart", "elements", allow_duplicate=True),
    Output("global-status", "children", allow_duplicate=True),
    Output("progress-bar-fill", "style", allow_duplicate=True),
    Output("start-exec-btn", "disabled", allow_duplicate=True),
    Input("complete-btn", "n_clicks"),
    State("selected-node-store", "data"),
    State("dag-store", "data"),
    State("node-states-store", "data"),
    prevent_initial_call=True,
)
def on_complete_node(n_clicks, selected_nid, dag, node_states):
    # ── 1. 前置守卫 ──
    if not selected_nid or not dag:
        return (no_update,) * 5

    nodes = dag.get("nodes", [])
    edges = dag.get("edges", [])

    # ── 2. 安全更新状态 ──
    new_states = dict(node_states or {})  # ⭐ 防御 None
    new_states[selected_nid] = "done"

    # ── 3. 拓扑传播（仅解锁直接下游，不级联）──
    new_states = _auto_unlock_downstream(dag, new_states, selected_nid, "done")

    # ── 4. 带缓存的渲染 ──
    elements = _cytoscape_cached(nodes, edges, new_states)  # ⭐ 统一缓存

    # ── 5. 进度计算与反馈 ──
    done_count = sum(1 for v in new_states.values() if v == "done")
    total = len(nodes)
    pct = int(done_count / total * 100) if total > 0 else 0

    status_msg = f"✅ 完成 {done_count}/{total} ({pct}%)"
    if pct >= 100:
        status_msg = "🎉 所有节点已完成！"

    bar_style = {
        "width": f"{pct}%",
        "height": "100%",
        "background": "linear-gradient(90deg, #10b981, #34d399)",
        "borderRadius": "6px",
        "transition": "width 0.3s ease",  # ⭐ 平滑动画
    }

    return new_states, elements, status_msg, bar_style, False

@callback(
    Output("node-states-store", "data", allow_duplicate=True),
    Output("flowchart", "elements", allow_duplicate=True),
    Output("global-status", "children", allow_duplicate=True),
    Output("progress-bar-fill", "style", allow_duplicate=True),      # ⭐ 新增：同步进度条
    Output("start-exec-btn", "disabled", allow_duplicate=True),     # ⭐ 新增：保持按钮状态一致
    Input("skip-btn", "n_clicks"),
    Input("skip-btn-panel", "n_clicks"),
    State("selected-node-store", "data"),
    State("dag-store", "data"),
    State("node-states-store", "data"),
    prevent_initial_call=True,
)
def on_skip_node(n1, n2, selected_nid, dag, node_states):
    # ── 1. 触发源校验与前置守卫 ──
    triggered_id = ctx.triggered_id
    if triggered_id not in ("skip-btn", "skip-btn-panel"):
        return (no_update,) * 5
    
    if not selected_nid or not dag:
        return no_update, no_update, "⚠️ 请先选择要跳过的节点", no_update, no_update

    nodes = dag.get("nodes", [])
    edges = dag.get("edges", [])

    # ── 2. 安全更新状态 ──
    new_states = dict(node_states or {})  # ⭐ 防御 None
    new_states[selected_nid] = "skipped"

    # ── 3. 建议性解锁下游（非级联）──
    new_states = _auto_unlock_downstream(dag, new_states, selected_nid, "skipped")

    # ── 4. 带缓存的渲染 ──
    elements = _cytoscape_cached(nodes, edges, new_states)  # ⭐ 统一缓存

    # ── 5. 进度计算（skipped 视为已处理，计入总进度）──
    done_count = sum(1 for v in new_states.values() if v == "done")
    skipped_count = sum(1 for v in new_states.values() if v == "skipped")
    total = len(nodes)
    processed = done_count + skipped_count
    pct = int(processed / total * 100) if total > 0 else 0

    # ⭐ 修正文案：准确描述下游行为，避免语义矛盾
    status_msg = f"⏭️ 已跳过 {selected_nid}（下游已按规则解锁）| ✅{done_count} ⏭️{skipped_count} / {total}"

    bar_style = {
        "width": f"{pct}%",
        "height": "100%",
        "background": "linear-gradient(90deg, #6366f1, #818cf8)",  # 紫色渐变区分于完成的绿色
        "borderRadius": "6px",
        "transition": "width 0.3s ease",
    }

    return new_states, elements, status_msg, bar_style, False

@callback(
    Output("node-states-store", "data", allow_duplicate=True),
    Output("flowchart", "elements", allow_duplicate=True),
    Output("global-status", "children", allow_duplicate=True),
    Output("progress-bar-fill", "style", allow_duplicate=True),
    Output("start-exec-btn", "disabled", allow_duplicate=True),
    Input("fail-btn", "n_clicks"),
    Input("fail-btn-panel", "n_clicks"),
    State("selected-node-store", "data"),
    State("dag-store", "data"),
    State("node-states-store", "data"),
    prevent_initial_call=True,
)
def on_fail_node(n1, n2, selected_nid, dag, node_states):
    # ── 1. 触发源校验与前置守卫 ──
    triggered_id = ctx.triggered_id
    if triggered_id not in ("fail-btn", "fail-btn-panel"):
        return (no_update,) * 5

    if not selected_nid or not dag:
        return no_update, no_update, "⚠️ 请先选择要标记失败的节点", no_update, no_update

    nodes = dag.get("nodes", [])
    edges = dag.get("edges", [])

    # ── 2. 安全更新状态 ──
    new_states = dict(node_states or {})
    new_states[selected_nid] = "failed"

    # ── 3. 失败专用下游处理：仅解锁 soft/optional 边，hard 边保持 blocked ──
    # 注：需确保 _auto_unlock_downstream 支持按边类型过滤，或此处改用专用函数
    new_states = _auto_unlock_downstream(
        dag, new_states, selected_nid, "failed", 
        allowed_edge_types=("soft", "optional")  # ⭐ 关键：限制解锁范围
    )

    # ── 4. 带缓存的渲染 ──
    elements = _cytoscape_cached(nodes, edges, new_states)

    # ── 5. 进度计算（failed 视为已处理，计入总进度）──
    done_count = sum(1 for v in new_states.values() if v == "done")
    skipped_count = sum(1 for v in new_states.values() if v == "skipped")
    failed_count = sum(1 for v in new_states.values() if v == "failed")
    total = len(nodes)
    processed = done_count + skipped_count + failed_count
    pct = int(processed / total * 100) if total > 0 else 0

    # ⭐ 文案准确描述失败后果，区分边类型影响
    hard_blocked_hint = "（强依赖下游已锁定）"
    status_msg = f"❌ {selected_nid} 标记为「做不到」{hard_blocked_hint} | ✅{done_count} ⏭️{skipped_count} ❌{failed_count}/{total}"

    bar_style = {
        "width": f"{pct}%",
        "height": "100%",
        "background": "linear-gradient(90deg, #ef4444, #f87171)",  # 红色渐变标识失败
        "borderRadius": "6px",
        "transition": "width 0.3s ease",
    }

    return new_states, elements, status_msg, bar_style, False

@callback(
    Output("node-states-store", "data", allow_duplicate=True),
    Output("flowchart", "elements", allow_duplicate=True),
    Output("global-status", "children", allow_duplicate=True),
    Output("progress-bar-fill", "style", allow_duplicate=True),
    Output("start-exec-btn", "disabled", allow_duplicate=True),
    Input("reset-btn-panel", "n_clicks"),
    State("selected-node-store", "data"),
    State("dag-store", "data"),
    State("node-states-store", "data"),
    State("current-task-id-store", "data"),
    prevent_initial_call=True,
)
def on_reset_node(n_clicks, selected_nid, dag, node_states, task_id):
    """重置节点：前后端双写，DB 失败时保留前端状态防止数据撕裂"""
    # ── 1. 触发源校验与前置守卫 ──
    if ctx.triggered_id != "reset-btn-panel":
        return (no_update,) * 5

    if not selected_nid or not dag:
        return no_update, no_update, "⚠️ 请先选择要重置的节点", no_update, no_update

    # 安全转换 nid，防止非数字字符串导致 int() 崩溃
    try:
        nid_int = int(selected_nid)
    except (ValueError, TypeError):
        return no_update, no_update, f"⚠️ 无效节点ID: {selected_nid}", no_update, no_update

    nodes = dag.get("nodes", [])
    edges = dag.get("edges", [])
    old_states = dict(node_states or {})

    # ── 2. 后端 DB 重置 ──
    db_ok = False
    has_task = bool(task_id)
    if has_task:
        try:
            db_ok = reset_node_status(task_id, nid_int)
        except Exception as e:
            logger.error("[Reset] DB 重置失败 task=%s node=%s: %s", task_id, nid_int, e, exc_info=True)

    # ── 3. 前端状态更新：DB 失败且有 task_id 时拒绝删除，防止前后端撕裂 ──
    new_states = dict(old_states)
    frontend_reset = False

    if has_task and not db_ok:
        # ⭐ 关键：后端未确认时，前端不做任何变更
        pass
    else:
        # DB 成功 / 无关联任务 → 安全删除前端状态
        if selected_nid in new_states:
            del new_states[selected_nid]
            frontend_reset = True

    # ── 4. 带缓存的渲染 ──
    elements = _cytoscape_cached(nodes, edges, new_states)

    # ── 5. 进度重新计算 ──
    done_count = sum(1 for v in new_states.values() if v == "done")
    skipped_count = sum(1 for v in new_states.values() if v == "skipped")
    failed_count = sum(1 for v in new_states.values() if v == "failed")
    total = len(nodes)
    processed = done_count + skipped_count + failed_count
    pct = int(processed / total * 100) if total > 0 else 0

    bar_style = {
        "width": f"{pct}%",
        "height": "100%",
        "background": "linear-gradient(90deg, #6366f1, #818cf8)",
        "borderRadius": "6px",
        "transition": "width 0.3s ease",
    }

    # ── 6. 精准反馈消息 ──
    if has_task and not db_ok:
        msg = f"❌ 节点 {selected_nid} 后端重置失败，前端状态未变更（请重试或检查日志）"
    elif frontend_reset:
        sync_label = "前端+后端同步" if has_task else "仅前端，无关联任务"
        msg = f"🔄 节点 {selected_nid} 已重置（{sync_label}）| ✅{done_count} ⏭️{skipped_count} ❌{failed_count}/{total}"
    else:
        msg = f"ℹ️ 节点 {selected_nid} 原本就是初始状态，无需重置"

    return new_states, elements, msg, bar_style, False

# 
#  历史记录 Callbacks
# ══════════════════════════════════════════════════

@callback(
    Output("history-dropdown", "options"),
    Output("history-dropdown", "placeholder"),
    Input("refresh-btn", "n_clicks"),
    Input("main-tabs", "value"),
    prevent_initial_call=True,
)
def load_history_list(n_clicks, tab_value):
    """加载历史记录下拉选项，带异常日志、排序、安全截断"""
    # ── 1. 非历史 tab 保持现有 options 不变，防止已选值失效 ──
    if tab_value != "tab-history":
        return no_update, no_update

    # ── 2. 安全加载 + 异常日志 ──
    try:
        tasks = list_tasks(limit=50)
    except Exception as e:
        logger.error("[History] 加载任务列表失败: %s", e, exc_info=True)
        return [], "❌ 加载失败，请检查后端服务"

    if not tasks:
        return [], "暂无历史记录"

    # ── 3. 按创建时间倒序排列（最新在前），label 安全截断 ──
    sorted_tasks = sorted(tasks, key=lambda t: t.get("created_at", ""), reverse=True)

    options = []
    for t in sorted_tasks:
        raw_title = t.get("title") or ""
        safe_title = str(raw_title)[:30] if raw_title else "(无标题)"
        tid_suffix = str(t.get("task_id", ""))[-8:]
        options.append({
            "label": f"{safe_title} | {tid_suffix}",
            "value": t["task_id"],
        })

    return options, "请选择历史任务"


@callback(
    Output("history-flowchart", "elements"),
    Output("history-detail", "children"),
    Output("history-flowchart", "pan"),
    Output("global-status", "children", allow_duplicate=True),
    Output("dag-store", "data", allow_duplicate=True),
    Output("history-replan-btn", "disabled"),
    Output("history-edit-plan-btn", "disabled"),
    Output("history-resume-btn", "disabled"),
    Output("history-retry-btn", "disabled"),
    Output("history-action-status", "children"),
    Output("history-dag-store", "data"),
    Output("history-node-states-store", "data"),
    Input("history-dropdown", "value"),
    prevent_initial_call=True,
)
def on_history_select(task_ids):
    """加载历史任务：渲染流程图 + 重建节点状态 + 按钮联动"""

    # ── 1. 空选择守卫 ──
    if not task_ids:
        return HistorySelectResult().to_tuple()

    task_id = task_ids[0] if isinstance(task_ids, list) else task_ids

    # ── 2. 安全加载 + 异常日志 ──
    try:
        data = load_task_with_plan(task_id)
    except Exception as e:
        logger.error("[History] 加载任务失败 task=%s: %s", task_id, e, exc_info=True)
        return HistorySelectResult(
            global_status="❌ 加载失败，请检查后端服务",
            action_status="❌ 加载失败",
        ).to_tuple()

    if not data:
        return HistorySelectResult(
            global_status="⚠️ 任务不存在",
            action_status="⚠️ 任务不存在",
        ).to_tuple()

    task_info = data["task"]
    plan_data = data.get("plan")

    # ── 3. 直接回答类会话（无 Plan）──
    if not plan_data:
        direct_resp = task_info.get("direct_response") or "（无回答内容）"
        raw_query = task_info.get("raw_query") or ""
        md_text = (
            f"## 💬 直接回答\n\n"
            f"**用户提问：**\n\n{raw_query}\n\n---\n\n"
            f"**AI 回答：**\n\n{direct_resp}\n\n---\n\n"
            f"*任务 ID: {task_id} | 类型: 直接回答（无规划流程）*"
        )
        return HistorySelectResult(
            detail=dcc.Markdown(md_text, style={"fontSize": "14px", "lineHeight": "1.8"}),
            global_status="💬 直接回答任务已加载",
            action_status="💡 这是一个直接回答类会话，无需规划流程。可在新建任务中重新提问。",
        ).to_tuple()

    # ── 4. 规划类任务：重建 node_states ──
    nodes = plan_data.get("nodes", [])
    edges = plan_data.get("edges", [])

    node_states = {
        str(n.get("id", "")): NODE_STATUS_CODE_MAP.get(n.get("status", 0), "pending")
        for n in nodes
    }

    # ── 5. 带缓存的渲染 ──
    elements = _cytoscape_cached(nodes, edges, node_states)
    md_text = build_history_detail_markdown(task_id, nodes)
    dag_store_data = {"nodes": nodes, "edges": edges, "task_id": task_id}

    # ── 6. 按钮启用逻辑 ──
    has_failed = any(v == "failed" for v in node_states.values())
    has_pending = any(v in ("pending", "blocked") for v in node_states.values())
    all_done = all(v in ("done", "skipped") for v in node_states.values())

    pending_count = sum(1 for v in node_states.values() if v in ("pending", "blocked"))
    hint_parts = []
    if all_done:
        hint_parts.append("✅ 所有节点已完成")
    if has_failed:
        hint_parts.append("❌ 存在失败节点，可重试")
    if has_pending:
        hint_parts.append(f"⏳ 还有 {pending_count} 个节点待执行")
    action_hint = " | ".join(hint_parts) if hint_parts else "✅ 任务状态正常"

    # ── 7. 关键字构造返回，顺序无关、IDE 补全、零错位风险 ──
    return HistorySelectResult(
        elements=elements,
        detail=dcc.Markdown(md_text, style={"fontSize": "14px", "lineHeight": "1.8"}),
        global_status=f"✅ 已加载历史流程图（{len(nodes)} 个节点）",
        dag_store=dag_store_data,
        replan_disabled=False,
        edit_disabled=False,
        resume_disabled=not has_pending,
        retry_disabled=not has_failed,
        action_status=action_hint,
        history_dag_store=dag_store_data,
        history_node_states=node_states,
    ).to_tuple()


@callback(
    Output("history-node-detail", "children"),
    Output("history-selected-node-store", "data"),
    Output("history-node-done-btn", "disabled"),
    Output("history-node-skip-btn", "disabled"),
    Output("history-node-fail-btn", "disabled"),
    Input("history-flowchart", "tapNodeData"),
    State("history-node-states-store", "data"),
    prevent_initial_call=True,
)
def on_history_tap_node(node_data, node_states):
    """节点点击：展示详情 + 基于实际状态的按钮联动"""

    # ── 1. 空点击守卫：保持现有状态不变 ──
    if not node_data:
        return HistoryTapNodeResult().to_tuple()

    nid = str(node_data.get("id", ""))
    if not nid:
        logger.warning("[History] tapNodeData 缺少 id 字段: %s", node_data)
        return HistoryTapNodeResult().to_tuple()

    # ── 2. 安全获取节点状态 ──
    node_states = node_states or {}
    current_state = str(node_states.get(nid, "pending"))
    can_operate = current_state in NODE_OPERABLE_STATES

    # ── 3. 安全构建详情 Markdown ──
    try:
        clean_data = sanitize_node_for_user(dict(node_data))
        md_text = build_detail_markdown(clean_data)
    except Exception as e:
        logger.error("[History] 构建节点详情失败 node=%s: %s", nid, e, exc_info=True)
        md_text = f"**⚠️ 节点详情加载失败**\n\n`{nid}`"

    # ── 4. 关键字构造返回 ──
    return HistoryTapNodeResult(
        detail=dcc.Markdown(md_text, style={"fontSize": "13px", "lineHeight": "1.8"}),
        selected_node=nid,
        done_disabled=not can_operate,
        skip_disabled=not can_operate,
        fail_disabled=not can_operate,
    ).to_tuple()


@callback(
    Output("history-dropdown", "options", allow_duplicate=True),
    Output("history-dropdown", "value", allow_duplicate=True),   # ← 新增：删除后清空选中
    Output("delete-status", "children"),
    Input("delete-btn", "n_clicks"),
    State("history-dropdown", "value"),
    prevent_initial_call=True,
)
def on_delete(n_clicks, task_ids):
    """删除历史任务：安全执行 + 刷新列表 + 清空选中 + 审计日志"""

    # ── 1. 空选择守卫 ──
    if not task_ids:
        return no_update, no_update, "⚠️ 请先选择要删除的任务"

    ids = task_ids if isinstance(task_ids, list) else [task_ids]

    # ── 2. 安全删除 + 审计日志 ──
    try:
        count = batch_delete_tasks(ids)
        logger.info("[History] 删除成功 tasks=%s count=%d", ids, count)
    except Exception as e:
        logger.error("[History] 删除失败 tasks=%s: %s", ids, e, exc_info=True)
        return no_update, no_update, "❌ 删除失败，请稍后重试或联系管理员"

    # ── 3. 刷新下拉列表 ──
    try:
        tasks = list_tasks(limit=50)
        options = build_history_dropdown_options(tasks)
    except Exception as e:
        logger.error("[History] 删除后刷新列表失败: %s", e, exc_info=True)
        # 删除已成功但刷新失败：仍清空选中，提示部分成功
        return no_update, None, f"✅ 已删除 {count} 个任务，但列表刷新失败，请手动刷新页面"

    # ── 4. 返回：新列表 + 清空选中 + 成功提示 ──
    return options, None, f"✅ 已删除 {count} 个任务"

@callback(
    Output("global-status", "children", allow_duplicate=True),
    Output("main-tabs", "value"),
    Output("user-input", "value"),
    Input("history-replan-btn", "n_clicks"),
    State("history-dropdown", "value"),
    prevent_initial_call=True,
)
def on_history_replan(n_clicks, task_ids):
    """重新规划：回填原始需求到新建任务页"""
    return _load_and_fill_query(task_ids, action_label="重新规划")

@callback(
    Output("history-node-states-store", "data", allow_duplicate=True),
    Output("history-flowchart", "elements", allow_duplicate=True),
    Output("history-action-status", "children", allow_duplicate=True),
    Input("history-node-done-btn", "n_clicks"),
    State("history-selected-node-store", "data"),
    State("history-dag-store", "data"),
    State("history-node-states-store", "data"),
    prevent_initial_call=True,
)
def on_history_node_done(n_clicks, selected_nid, dag, node_states):
    """手动标记节点完成：安全守卫 + 核心引擎调用 + 审计日志"""

    # ── 1. 全面空值守卫（包含 dag） ──
    if not selected_nid or not node_states or not dag:
        return no_update, no_update, no_update

    # ── 2. 调用核心引擎 + 异常兜底 ──
    try:
        new_states, elements, status_msg = update_node_and_render(
            dag, node_states, selected_nid, target_status="done"
        )
    except Exception as e:
        logger.error("[NodeAction] 标记完成失败 node=%s: %s", selected_nid, e, exc_info=True)
        return no_update, no_update, f"❌ 状态更新失败: {selected_nid}"

    # ── 3. 审计日志 ──
    logger.info("[NodeAction] 手动标记完成 node=%s", selected_nid)

    return new_states, elements, status_msg

@callback(
    Output("history-node-states-store", "data", allow_duplicate=True),
    Output("history-flowchart", "elements", allow_duplicate=True),
    Output("history-action-status", "children", allow_duplicate=True),
    Input("history-node-skip-btn", "n_clicks"),
    State("history-selected-node-store", "data"),
    State("history-dag-store", "data"),
    State("history-node-states-store", "data"),
    prevent_initial_call=True,
)
def on_history_node_skip(n_clicks, selected_nid, dag, node_states):
    """手动跳过节点：调用统一引擎，跳过不解锁下游"""
    if not selected_nid or not node_states or not dag:
        return no_update, no_update, no_update

    try:
        result = update_node_and_render(dag, node_states, selected_nid, "skipped")
    except Exception as e:
        logger.error("[NodeAction] 跳过失败 node=%s: %s", selected_nid, e, exc_info=True)
        return no_update, no_update, f"❌ 跳过操作失败: {selected_nid}"

    logger.info("[NodeAction] 手动跳过 node=%s", selected_nid)
    return result

@callback(
    Output("history-node-states-store", "data", allow_duplicate=True),
    Output("history-flowchart", "elements", allow_duplicate=True),
    Output("history-action-status", "children", allow_duplicate=True),
    Input("history-node-fail-btn", "n_clicks"),
    State("history-selected-node-store", "data"),
    State("history-dag-store", "data"),
    State("history-node-states-store", "data"),
    prevent_initial_call=True,
)
def on_history_node_fail(n_clicks, selected_nid, dag, node_states):
    """手动标记节点失败：调用统一引擎，失败不解锁下游"""
    if not selected_nid or not node_states or not dag:
        return no_update, no_update, no_update

    try:
        result = update_node_and_render(dag, node_states, selected_nid, "failed")
    except Exception as e:
        logger.error("[NodeAction] 标记失败异常 node=%s: %s", selected_nid, e, exc_info=True)
        return no_update, no_update, f"❌ 标记失败操作异常: {selected_nid}"

    logger.warning("[NodeAction] 手动标记失败 node=%s", selected_nid)  # ← warning 级别，便于告警
    return result

@callback(
    Output("global-status", "children", allow_duplicate=True),
    Output("main-tabs", "value", allow_duplicate=True),
    Output("user-input", "value", allow_duplicate=True),
    Input("history-resume-btn", "n_clicks"),
    State("history-dropdown", "value"),
    prevent_initial_call=True,
)
def on_history_resume(n_clicks, task_ids):
    """继续执行：回填需求到新建页，用户可修改或直接继续"""
    return _load_and_fill_query(task_ids, action_label="继续执行")


# ══════════════════════════════════════════════════
#  数据导出：JSON / DOT / HTML（策略模式）
# ══════════════════════════════════════════════════

def _escape_dot_label(text: str) -> str:
    """修复 DOT 注入漏洞：转义双引号和反斜杠"""
    if not text:
        return ""
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


def _export_json(nodes, edges, task_id_str):
    """JSON 格式导出"""
    content = json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False, indent=2)
    return dcc.send_string(
        content, 
        filename=_make_filename("dag", task_id_str, "json"),
        type="application/json"
    )


def _export_dot(nodes, edges, task_id_str):
    """DOT (Graphviz) 格式导出 —— 已修复注入漏洞"""
    lines = ["digraph G {", '  rankdir=TB;', '  node [shape=box, style="rounded,filled", fillcolor="#E8F4FD"];']
    
    for n in nodes:
        node_id = _escape_dot_label(n.get("id", ""))
        label = _escape_dot_label(n.get("name") or n.get("node_name", ""))
        lines.append(f'  "{node_id}" [label="{label}"];')
    
    for e in edges:
        from_id = _escape_dot_label(e.get("from", ""))
        to_id = _escape_dot_label(e.get("to", ""))
        label = _escape_dot_label(e.get("label", ""))
        label_attr = f' [label="{label}"]' if label else ""
        lines.append(f'  "{from_id}" -> "{to_id}"{label_attr};')
    
    lines.append("}")
    return dcc.send_string(
        "\n".join(lines), 
        filename=_make_filename("dag", task_id_str, "dot"),
        type="text/vnd.graphviz"
    )


def _export_html(nodes, edges, task_id_str):
    """HTML 自包含报告导出"""
    html_content = _generate_html_export(nodes, edges, task_id_str)
    return dcc.send_string(
        html_content, 
        filename=_make_filename("dag", task_id_str, "html"),
        type="text/html"
    )

# 策略字典：新增格式只需添加映射条目，无需修改主回调（开闭原则）
_DATA_EXPORT_STRATEGIES = {
    "json": _export_json,
    "dot":  _export_dot,
    "html": _export_html,
}


@callback(
    Output("export-download", "data"),
    Input("export-data-btn", "n_clicks"),
    State("history-dropdown", "value"),
    State("dag-store", "data"),
    State("data-format", "value"),
    prevent_initial_call=True,
)
def on_export_data(n_clicks, history_task_ids, dag_store, fmt):
    """数据导出统一网关：JSON / DOT / HTML"""
    nodes, edges, _, task_id_str = _resolve_dag_data(history_task_ids, dag_store)

    if not nodes:
        logger.warning("[Export] 没有节点数据可导出 (format=%s)", fmt)
        return None

    export_fn = _DATA_EXPORT_STRATEGIES.get(fmt)
    if not export_fn:
        logger.error("[Export] 不支持的导出格式: %s", fmt)
        return None

    try:
        result = export_fn(nodes, edges, task_id_str)
        logger.info("[Export] ✅ %s 导出成功 (task=%s)", fmt.upper(), task_id_str)
        return result
    except Exception as e:
        logger.error("[Export] %s 导出失败: %s", fmt.upper(), e, exc_info=True)
        return None


# ══════════════════════════════════════════════════
#  图片导出：PyVis 后端渲染 → PNG / SVG 下载
# ══════════════════════════════════════════════════

@callback(
    Output("export-download", "data", allow_duplicate=True),
    Input("export-image-btn", "n_clicks"),
    State("history-dropdown", "value"),
    State("dag-store", "data"),
    State("node-states-store", "data"),
    State("image-format", "value"),
    prevent_initial_call=True,
)
def on_export_image(n_clicks, history_task_ids, dag_store, node_states, image_format):
    """图片导出统一网关：PNG / SVG（纯内存流式传输，零磁盘 IO）"""
    nodes, edges, node_states, task_id_str = _resolve_dag_data(
        history_task_ids, dag_store, node_states
    )

    if not nodes:
        logger.warning("[Export] 没有节点数据可导出 (format=%s)", image_format)
        return None

    title = f"流程图 {task_id_str}"

    try:
        if image_format == "svg":
            svg_bytes = export_dag_to_svg(
                nodes=nodes, edges=edges,
                output_path=None,  # None = 纯内存模式，零磁盘 IO
                node_states=node_states,
                title=title, dpi=200,
            )
            logger.info("[Export] ✅ SVG 导出成功 (%.1f KB, task=%s)", 
                       len(svg_bytes) / 1024, task_id_str)
            return dcc.send_bytes(
                svg_bytes, 
                filename=_make_filename("flowchart", task_id_str, "svg"),
                type="image/svg+xml"
            )

        else:  # 默认 PNG
            png_bytes = export_dag_to_png(
                nodes=nodes, edges=edges,
                output_path=None,  # None = 纯内存模式，零磁盘 IO
                node_states=node_states,
                title=title, width=1600, height=1200, dpi=200,
            )
            logger.info("[Export] ✅ PNG 导出成功 (%.1f KB, task=%s)", 
                       len(png_bytes) / 1024, task_id_str)
            return dcc.send_bytes(
                png_bytes, 
                filename=_make_filename("flowchart", task_id_str, "png"),
                type="image/png"
            )

    except Exception as e:
        logger.error("[Export] %s 图片渲染失败: %s", 
                    image_format.upper(), e, exc_info=True)
        return None

# ══════════════════════════════════════════════════
#  图操作 Clientside Callbacks（DRY 重构版）
# ═════════════════════════════════════════════════
# ── 动态注册所有图的客户端回调 ──
_GRAPH_CONFIGS = GRAPH_CONFIGS
_FIT_JS_TEMPLATE = FIT_JS_TEMPLATE
_ZOOM_BTN_JS_TEMPLATE = ZOOM_BTN_JS_TEMPLATE 
_ZOOM_SLIDER_JS_TEMPLATE= ZOOM_SLIDER_JS_TEMPLATE
for _key, _cfg in _GRAPH_CONFIGS.items():
    # 1. Fit/Layout 回调
    clientside_callback(
        _FIT_JS_TEMPLATE.format(
            element_id=_cfg["element_id"],
            layout_json=json.dumps(_cfg["layout_options"]),
        ),
        Output(_cfg["fit_btn_id"], "n_clicks"),
        Input(_cfg["fit_btn_id"], "n_clicks"),
    )

    # 2. Zoom Button → Slider 回调
    clientside_callback(
        _ZOOM_BTN_JS_TEMPLATE.format(
            element_id=_cfg["element_id"],
            zoom_in_btn_id=_cfg["zoom_in_btn_id"],
            zoom_out_btn_id=_cfg["zoom_out_btn_id"],
        ),
        Output(_cfg["zoom_slider_id"], "value"),
        Input(_cfg["zoom_in_btn_id"], "n_clicks"),
        Input(_cfg["zoom_out_btn_id"], "n_clicks"),
    )

    # 3. Slider → Graph Zoom 回调
    clientside_callback(
        _ZOOM_SLIDER_JS_TEMPLATE.format(element_id=_cfg["element_id"]),
        Output(_cfg["element_id"], "zoom"),
        Input(_cfg["zoom_slider_id"], "value"),
    )

# ══════════════════════════════════════════════════
#  启动
# ══════════════════════════════════════════════════
# 端口合法范围常量
_VALID_PORT_RANGE = VALID_PORT_RANGE

def _validate_port(port_value) -> int:
    """
    严格校验端口号。
    Raises:
        ValueError: 端口无效时抛出，附带明确的错误描述
    """
    try:
        port = int(port_value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"DASH_PORT 无法转换为整数: {port_value!r}") from e

    if port not in _VALID_PORT_RANGE:
        raise ValueError(
            f"DASH_PORT={port} 超出合法范围 [1-65535]"
        )
    return port


def main() -> None:
    """Dash 应用启动入口：配置校验 → 运行时增强 → 进程感知启动"""
    from task_planner.infrastructure.config import CSP_POLICY as csp
    # ── 1. 配置解析与严格校验（Fail-Fast） ──
    host = DASH_HOST
    debug = DEBUG

    try:
        port = _validate_port(DASH_PORT)
    except ValueError as e:
        logger.error("[Startup] 配置校验失败: %s", e)
        sys.exit(1)

    # ── 2. 运行时增强 ──
    # boost() 内部已处理幂等 + Werkzeug reloader 兼容
    # memory_watchdog 仅在非 debug 模式启用，避免干扰热重载
    boost(
        app=app,
        graceful_shutdown=True,
        memory_watchdog=not debug,
        #csp_policy=csp
    )

    # ── 3. 进程感知启动日志 ──
    mode = "debug" if debug else "production"
    is_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    process_tag = " [reloader]" if is_reloader else ""

    logger.info(
        "[Startup] Dash starting (%s%s) | %s:%d",
        mode, process_tag, host, port,
    )

    # ── 4. 启动服务 ──
    app.run(debug=debug, host=host, port=port)


if __name__ == "__main__":
    main()
