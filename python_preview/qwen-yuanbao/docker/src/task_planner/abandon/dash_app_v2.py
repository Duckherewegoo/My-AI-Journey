"""
dash_app.py — 完整 Dash UI + 交互式任务执行
包含：新建任务流式执行 + 历史记录 + 节点交互确认 + 导出 + 图操作优化 + 循环边支持
图片导出方案：纯 Python 后端渲染（NetworkX + Matplotlib），不依赖前端 Cytoscape
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

import dash
from dash import dcc, html, Input, Output, State, callback, clientside_callback
import dash_cytoscape as cyto

from .model.cytoscape_adapter import dag_to_cytoscape, build_detail_markdown, build_history_detail_markdown
from .model.stream_manager import (
    start_stream,
    get_stream_state,
    cancel_stream,
)
from .model.database import (
    init_db,
    list_tasks,
    load_task_with_plan,
    batch_delete_tasks,
)
from .model.logger_setup import get_logger

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

# ══════════════════════════════════════════════════
#  Cytoscape 样式
# ══════════════════════════════════════════════════
CYTO_STYLESHEET: List[Dict[str, Any]] = [
    {
        "selector": "node",
        "style": {
            "label": "data(label)",
            "text-valign": "center",
            "text-halign": "center",
            "font-size": "13px",
            "font-family": "Arial, sans-serif",
            "width": "data(width)",
            "height": "label",
            "padding": "12px",
            "shape": "round-rectangle",
            "border-width": 2,
            "text-wrap": "wrap",
            "text-max-width": "180px",
            "transition-property": "background-color, border-color, opacity",
            "transition-duration": "0.3s",
        },
    },
    {"selector": ".state-ready", "style": {
        "background-color": "#fef3c7", "border-color": "#f59e0b", "border-width": 3,
    }},
    {"selector": ".state-running", "style": {
        "background-color": "#dbeafe", "border-color": "#3b82f6", "border-width": 3,
    }},
    {"selector": ".state-done", "style": {
        "background-color": "#d1fae5", "border-color": "#10b981", "opacity": 0.9,
    }},
    {"selector": ".state-failed", "style": {
        "background-color": "#fee2e2", "border-color": "#ef4444", "border-style": "dashed",
    }},
    {"selector": ".state-skipped", "style": {
        "background-color": "#f3f4f6", "border-color": "#9ca3af", "opacity": 0.5,
    }},
    {"selector": ".state-blocked", "style": {
        "background-color": "#f9fafb", "border-color": "#d1d5db", "opacity": 0.6,
    }},
    {
        "selector": "edge",
        "style": {
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            "target-arrow-color": "#64748b",
            "width": 1.5,
            "label": "data(label)",
            "font-size": "11px",
            "color": "#1e293b",
            "text-background-color": "#ffffff",
            "text-background-opacity": 0.95,
            "text-background-padding": "4px",
            "text-background-shape": "round-rectangle",
            "text-border-color": "#cbd5e1",
            "text-border-width": 1,
            "text-border-opacity": 0.5,
            "text-offset": 12,
            "text-rotation": "autorotate",
            "control-point-step-size": 80,
            "transition-property": "line-color, target-arrow-color, line-style",
            "transition-duration": "0.3s",
        },
    },
    {"selector": ".edge-done", "style": {
        "line-color": "#10b981", "target-arrow-color": "#10b981", "width": 2.5,
    }},
    {"selector": ".edge-pending", "style": {
        "line-color": "#cbd5e1", "target-arrow-color": "#cbd5e1",
    }},
    {"selector": ".edge-skipped", "style": {
        "line-color": "#d1d5db", "target-arrow-color": "#d1d5db",
        "line-style": "dashed", "opacity": 0.4,
    }},
    {"selector": ".edge-failed", "style": {
        "line-color": "#ef4444", "target-arrow-color": "#ef4444", "line-style": "dashed",
    }},
    {"selector": ".edge-cycle", "style": {
        "line-color": "#f59e0b", "target-arrow-color": "#f59e0b",
        "line-style": "dotted", "width": 2,
        "label": "data(full_label)", "font-size": "10px",
        "color": "#92400e",
        "text-background-color": "#fef3c7",
        "text-background-opacity": 0.95,
        "text-background-padding": "4px",
        "text-background-shape": "round-rectangle",
        "text-border-color": "#f59e0b",
        "text-border-width": 1,
    }},
    {"selector": "edge:hover", "style": {
        "line-color": "#1a73e8", "target-arrow-color": "#1a73e8", "width": 3,
        "label": "data(full_label)", "font-size": "11px", "color": "#1a73e8",
    }},
    {"selector": ":hover", "style": {"border-width": 3, "border-color": "#1a73e8"}},
    {"selector": ":selected", "style": {
        "border-width": 4, "border-color": "#f59e0b"}},
]

PULSE_CSS = (
    "@keyframes pulse {"
    "0% { box-shadow: 0 0 0 0 rgba(59,130,246,0.5); }"
    "70% { box-shadow: 0 0 0 10px rgba(59,130,246,0); }"
    "100% { box-shadow: 0 0 0 0 rgba(59,130,246,0); }"
    "}"
)

PROGRESS_CSS = (
    "@keyframes stripe-slide {"
    "0% { background-position: 0 0; }"
    "100% { background-position: 30px 0; }"
    "}"
    ".indeterminate-bar {"
    "width: 100% !important;"
    "background: repeating-linear-gradient("
    "45deg, #3b82f6, #3b82f6 10px, #60a5fa 10px, #60a5fa 20px"
    ") !important;"
    "background-size: 30px 100% !important;"
    "animation: stripe-slide 0.8s linear infinite !important;"
    "border-radius: 6px !important;"
    "height: 100% !important;"
    "transition: none !important;"
    "}"
)

# ══════════════════════════════════════════════════
#  布局
# ══════════════════════════════════════════════════


def build_layout() -> html.Div:
    return html.Div([
        dcc.Markdown(
            '<style>'
            + PULSE_CSS + PROGRESS_CSS
            + '</style>',
            dangerously_allow_html=True,
        ),
        dcc.Interval(id="stream-interval", interval=500,
                     disabled=True, n_intervals=0),
        dcc.Store(id="thread-id-store", data=""),
        dcc.Store(id="stream-active", data=False),
        dcc.Store(id="node-states-store", data={}),
        dcc.Store(id="dag-store", data={"nodes": [], "edges": []}),
        dcc.Store(id="selected-node-store", data=""),
        dcc.Store(id="task-start-time", data=None),

        # ═══ 导出下载组件（纯后端方案，不需要 screenshot-store） ═══
        dcc.Download(id="export-download"),

        # ═══ 全局导出工具栏 ═══
        html.Div([
            html.Div([
                html.Span("📤 导出图像：", style={
                    "fontSize": "12px", "fontWeight": "bold", "marginRight": "6px", "whiteSpace": "nowrap"}),
                html.Button("⬇️ 导出图片", id="export-image-btn", n_clicks=0, style={
                    "padding": "4px 12px", "backgroundColor": "#1a73e8", "color": "white",
                    "border": "none", "borderRadius": "4px", "cursor": "pointer", "fontSize": "12px",
                    "marginRight": "20px",
                }),
            ], style={"display": "inline-block", "marginRight": "15px", "marginBottom": "5px"}),

            html.Div([
                html.Span("📤 导出数据：", style={
                    "fontSize": "12px", "fontWeight": "bold", "marginRight": "6px", "whiteSpace": "nowrap"}),
                dcc.RadioItems(
                    id="data-format",
                    options=[
                        {"label": "JSON", "value": "json"},
                        {"label": "DOT", "value": "dot"},
                        {"label": "HTML", "value": "html"},
                    ],
                    value="json", inline=True,
                    style={"fontSize": "12px",
                           "display": "inline-block", "marginRight": "10px"},
                ),
                html.Button("⬇️ 导出数据", id="export-data-btn", n_clicks=0, style={
                    "padding": "4px 12px", "backgroundColor": "#10b981", "color": "white",
                    "border": "none", "borderRadius": "4px", "cursor": "pointer", "fontSize": "12px",
                }),
            ], style={"display": "inline-block", "marginBottom": "5px"}),
        ], style={
            "textAlign": "right",
            "backgroundColor": "white",
            "padding": "8px 15px",
            "borderRadius": "8px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.1)",
            "marginBottom": "15px",
            "flexWrap": "wrap",
        }),

        html.H1("🧠 通用任务规划助手", style={
            "textAlign": "center", "marginBottom": "5px", "color": "#1e293b",
        }),
        html.P("输入任务需求，AI 自动分解为 DAG 流程图，逐步确认执行", style={
            "textAlign": "center", "color": "#64748b", "marginBottom": "10px",
        }),

        # ═══ 全局状态栏 ═══
        html.Div(id="global-status", children="👋 就绪，等待操作", style={
            "marginBottom": "8px", "fontWeight": "bold", "fontSize": "14px", "color": "#1e293b",
            "textAlign": "center",
        }),
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

        dcc.Tabs(id="main-tabs", value="tab-new", children=[
            dcc.Tab(label="🚀 新建任务", value="tab-new", children=[
                html.Div([
                    html.Div([
                        dcc.Textarea(
                            id="user-input",
                            placeholder="输入任务需求，例如：教我做甜口西红柿炒鸡蛋（最多 2000 字符）",
                            style={
                                "width": "100%", "height": "90px", "fontSize": "14px",
                                "padding": "10px", "borderRadius": "8px", "border": "1px solid #d1d5db",
                            },
                        ),
                        dcc.Checklist(
                            id="enable-refine",
                            options=[{"label": "🔧 节点细化", "value": "refine"}],
                            value=["refine"],
                            style={"marginTop": "10px"},
                        ),
                    ], style={"marginBottom": "15px"}),

                    # ── 任务控制 ──
                    html.Div([
                        html.Div("📋 任务控制", style={
                            "fontSize": "12px", "fontWeight": "bold", "color": "#64748b",
                            "marginBottom": "8px", "textTransform": "uppercase", "letterSpacing": "1px",
                        }),
                        html.Div([
                            html.Button("🚀 开始规划", id="submit-btn", n_clicks=0, style={
                                "backgroundColor": "#1a73e8", "color": "white", "border": "none",
                                "padding": "12px 24px", "borderRadius": "8px", "cursor": "pointer",
                                "fontSize": "15px", "fontWeight": "bold", "marginRight": "10px",
                            }),
                            html.Button("⏹️ 停止", id="stop-btn", n_clicks=0, disabled=True, style={
                                "backgroundColor": "#ef4444", "color": "white", "border": "none",
                                "padding": "12px 24px", "borderRadius": "8px", "cursor": "pointer",
                                "fontSize": "15px", "fontWeight": "bold",
                            }),
                            html.Button("▶️ 继续", id="resume-btn", n_clicks=0, disabled=True, style={
                                "backgroundColor": "#8b5cf6", "color": "white", "border": "none",
                                "padding": "12px 24px", "borderRadius": "8px", "cursor": "pointer",
                                "fontSize": "15px", "fontWeight": "bold",
                            }),
                        ]),
                    ], style={
                        "padding": "14px 18px", "backgroundColor": "#eff6ff",
                        "border": "1px solid #bfdbfe", "borderRadius": "10px", "marginBottom": "12px",
                    }),

                    # ── 节点操作 ──
                    html.Div([
                        html.Div("🎯 节点操作（先点击流程图中的节点，再选择操作）", style={
                            "fontSize": "12px", "fontWeight": "bold", "color": "#64748b",
                            "marginBottom": "8px", "textTransform": "uppercase", "letterSpacing": "1px",
                        }),
                        html.Div([
                            html.Button("▶️ 开始执行选中节点", id="start-exec-btn", n_clicks=0, disabled=True, style={
                                "backgroundColor": "#10b981", "color": "white", "border": "none",
                                "padding": "12px 20px", "borderRadius": "8px", "cursor": "pointer",
                                "fontSize": "14px", "fontWeight": "bold", "marginRight": "10px",
                            }),
                            html.Button("⏭️ 跳过选中节点", id="skip-btn", n_clicks=0, disabled=True, style={
                                "backgroundColor": "#6366f1", "color": "white", "border": "none",
                                "padding": "12px 20px", "borderRadius": "8px", "cursor": "pointer",
                                "fontSize": "14px", "fontWeight": "bold", "marginRight": "10px",
                            }),
                            html.Button("❌ 做不到", id="fail-btn", n_clicks=0, disabled=True, style={
                                "backgroundColor": "#ef4444", "color": "white", "border": "none",
                                "padding": "12px 20px", "borderRadius": "8px", "cursor": "pointer",
                                "fontSize": "14px", "fontWeight": "bold",
                            }),
                        ]),
                        html.Div(id="node-action-hint", children="👆 请先在流程图中点击一个高亮（蓝色）节点", style={
                            "fontSize": "13px", "color": "#94a3b8", "marginTop": "8px", "fontStyle": "italic",
                        }),
                    ], style={
                        "padding": "14px 18px", "backgroundColor": "#f0fdf4",
                        "border": "1px solid #bbf7d0", "borderRadius": "10px", "marginBottom": "15px",
                    }),

                    # ── 图操作工具栏 ──
                    html.Div([
                        html.Button("⊡ 适应窗口", id="fit-btn", n_clicks=0, style={
                            "padding": "4px 10px", "marginRight": "8px", "backgroundColor": "#f1f5f9",
                            "border": "1px solid #d1d5db", "borderRadius": "4px", "cursor": "pointer", "fontSize": "12px",
                        }),
                        html.Button("＋ 放大", id="zoom-in-btn", n_clicks=0, style={
                            "padding": "4px 10px", "marginRight": "4px", "backgroundColor": "#f1f5f9",
                            "border": "1px solid #d1d5db", "borderRadius": "4px", "cursor": "pointer", "fontSize": "12px",
                        }),
                        html.Button("－ 缩小", id="zoom-out-btn", n_clicks=0, style={
                            "padding": "4px 10px", "marginRight": "8px", "backgroundColor": "#f1f5f9",
                            "border": "1px solid #d1d5db", "borderRadius": "4px", "cursor": "pointer", "fontSize": "12px",
                        }),
                        html.Div(
                            dcc.Slider(
                                id="zoom-slider", min=0.2, max=4.0, step=0.1, value=0.6,
                                marks={0.2: "20%", 0.6: "60%",
                                       1: "100%", 2: "200%", 4: "400%"},
                                tooltip={"placement": "bottom",
                                         "always_visible": True},
                            ),
                            style={"width": "200px", "display": "inline-block",
                                   "verticalAlign": "middle"},
                        ),
                    ], style={"marginBottom": "10px"}),

                    cyto.Cytoscape(
                        id="flowchart",
                        elements=[],
                        layout={
                            "name": "dagre", "rankDir": "TB",
                            "nodeSep": 300, "rankSep": 450, "edgeSep": 80, "fit": True, "padding": 80,
                        },
                        style={"width": "100%", "height": "700px",
                               "border": "1px solid #e2e8f0", "borderRadius": "12px"},
                        stylesheet=CYTO_STYLESHEET,
                        userZoomingEnabled=True,
                        userPanningEnabled=True,
                        boxSelectionEnabled=False,
                        autoungrabify=False,
                        minZoom=0.2, maxZoom=4.0, zoom=0.6,
                    ),

                    html.Div(id="node-detail-panel", children=[
                        dcc.Markdown("👆 **点击流程图中的节点查看详情并操作**", style={
                            "fontSize": "14px", "color": "#94a3b8"
                        })
                    ], style={
                        "marginTop": "15px", "padding": "18px", "border": "1px solid #e2e8f0",
                        "borderRadius": "12px", "backgroundColor": "#f8fafc",
                        "minHeight": "160px", "fontSize": "14px", "lineHeight": "1.8",
                    }),
                ], style={"padding": "25px", "maxWidth": "1400px", "margin": "0 auto"}),
            ]),

            # ══════════════════════════════════════
            #  Tab 2: 历史记录
            # ══════════════════════════════════════
            dcc.Tab(label="📜 历史记录", value="tab-history", children=[
                html.Div([
                    html.Div([
                        html.H3("📋 任务列表", style={"marginTop": "0"}),
                        html.Button("🔄 刷新列表", id="refresh-btn", n_clicks=0, style={
                            "width": "100%", "padding": "10px", "backgroundColor": "#f1f5f9",
                            "border": "1px solid #d1d5db", "borderRadius": "6px",
                            "cursor": "pointer", "marginBottom": "12px",
                        }),
                        dcc.Dropdown(
                            id="history-dropdown", options=[], placeholder="选择历史任务（可多选删除）", multi=True,
                            style={"marginBottom": "12px"},
                        ),
                        html.Button("🗑️ 删除选中", id="delete-btn", n_clicks=0, style={
                            "width": "100%", "padding": "10px", "backgroundColor": "#ef4444",
                            "color": "white", "border": "none", "borderRadius": "6px",
                            "cursor": "pointer", "marginBottom": "10px",
                        }),
                        html.Div(id="delete-status",
                                 style={"fontSize": "13px", "color": "#059669"}),
                    ], style={
                        "width": "28%", "display": "inline-block", "verticalAlign": "top",
                        "padding": "20px", "borderRight": "1px solid #e2e8f0",
                    }),

                    html.Div([
                        html.H3("🗺️ 流程图", style={"marginTop": "0"}),

                        html.Div([
                            html.Button("⊡ 适应窗口", id="history-fit-btn", n_clicks=0, style={
                                "padding": "4px 10px", "marginRight": "8px",
                                "backgroundColor": "#f1f5f9", "border": "1px solid #d1d5db",
                                "borderRadius": "4px", "cursor": "pointer", "fontSize": "12px",
                            }),
                            html.Button("＋ 放大", id="history-zoom-in-btn", n_clicks=0, style={
                                "padding": "4px 10px", "marginRight": "4px",
                                "backgroundColor": "#f1f5f9", "border": "1px solid #d1d5db",
                                "borderRadius": "4px", "cursor": "pointer", "fontSize": "12px",
                            }),
                            html.Button("－ 缩小", id="history-zoom-out-btn", n_clicks=0, style={
                                "padding": "4px 10px", "marginRight": "8px",
                                "backgroundColor": "#f1f5f9", "border": "1px solid #d1d5db",
                                "borderRadius": "4px", "cursor": "pointer", "fontSize": "12px",
                            }),
                            html.Div(
                                dcc.Slider(
                                    id="history-zoom-slider", min=0.2, max=4.0, step=0.1, value=0.6,
                                    marks={0.2: "20%", 0.6: "60%",
                                           1: "100%", 2: "200%", 4: "400%"},
                                    tooltip={"placement": "bottom",
                                             "always_visible": True},
                                ),
                                style={
                                    "width": "200px", "display": "inline-block", "verticalAlign": "middle"},
                            ),
                        ], style={"marginBottom": "10px"}),

                        cyto.Cytoscape(
                            id="history-flowchart",
                            elements=[],
                            layout={
                                "name": "dagre", "rankDir": "TB",
                                "nodeSep": 250, "rankSep": 380, "edgeSep": 60, "fit": True, "padding": 60,
                            },
                            style={
                                "width": "100%", "height": "450px",
                                "border": "1px solid #e2e8f0", "borderRadius": "12px",
                                "marginBottom": "15px",
                            },
                            stylesheet=CYTO_STYLESHEET,
                            minZoom=0.2, maxZoom=4.0, zoom=0.6,
                            userZoomingEnabled=True, userPanningEnabled=True,
                        ),
                        html.Div([
                            html.H4("🎯 节点详情", style={
                                    "margin": "0 0 8px", "fontSize": "14px"}),
                            html.Div(id="history-node-detail", children=[
                                dcc.Markdown("**点击流程图中的节点查看详情**")
                            ], style={
                                "padding": "10px", "border": "1px solid #e2e8f0",
                                "borderRadius": "8px", "backgroundColor": "#f8fafc",
                                "minHeight": "80px", "fontSize": "13px", "marginBottom": "10px",
                            }),
                        ], style={"marginBottom": "15px"}),
                        html.H3("📝 任务详情"),
                        html.Div(id="history-detail", style={
                            "whiteSpace": "pre-wrap", "padding": "15px",
                            "border": "1px solid #e2e8f0", "borderRadius": "8px",
                            "backgroundColor": "#f8fafc", "fontSize": "14px", "lineHeight": "1.8",
                        }),
                    ], style={
                        "width": "68%", "display": "inline-block",
                        "padding": "20px", "verticalAlign": "top",
                    }),
                ]),
            ]),
        ]),
    ])


app.layout = build_layout()

# ══════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════


def _cascade_skip(dag, node_states, start_nid):
    edges = dag.get("edges", [])
    adj = {}
    for e in edges:
        src = str(e["from"])
        tgt = str(e["to"])
        if src not in adj:
            adj[src] = []
        adj[src].append(tgt)
    queue = [start_nid]
    visited = set()
    while queue:
        cur = queue.pop(0)
        for nxt in adj.get(cur, []):
            if nxt not in visited and node_states.get(nxt) not in ("done", "failed"):
                node_states[nxt] = "skipped"
                visited.add(nxt)
                queue.append(nxt)
    return node_states


def _generate_html_export(nodes, edges, task_id):
    elements_list = []
    for i, n in enumerate(nodes):
        nid = str(n.get("id", i))
        label = n.get("name", n.get("node_name", "Node " + str(i)))
        detail = n.get("detail", n.get("details", ""))
        elements_list.append(
            {"data": {"id": nid, "label": label, "detail": detail}})
    for i, e in enumerate(edges):
        elements_list.append({"data": {
            "id": "e" + str(i), "source": str(e["from"]), "target": str(e["to"]),
            "label": e.get("label", ""),
        }})
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<title>流程图 ' + str(task_id) + '</title>'
        '<script src="https://unpkg.com/cytoscape@3.28.1/dist/cytoscape.min.js"></script>'
        '<style>body{margin:0;font-family:Arial;}#cy{width:100%;height:100vh;}</style>'
        '</head><body><div id="cy"></div><script>'
        'var cy=cytoscape({container:document.getElementById("cy"),elements:'
        + json.dumps(elements_list, ensure_ascii=False)
        + ',layout:{name:"dagre",rankDir:"TB",nodeSep:300,rankSep:450},'
        'style:[{selector:"node",style:{"label":"data(label)","text-valign":"center",'
        '"text-halign":"center","font-size":13,"shape":"round-rectangle","padding":12,'
        '"background-color":"#dbeafe","border-color":"#3b82f6","border-width":2}},'
        '{selector:"edge",style:{"curve-style":"bezier","target-arrow-shape":"triangle",'
        '"label":"data(label)","font-size":11}}]'
        '});</script></body></html>'
    )

# ══════════════════════════════════════════════════
#  Callbacks
# ══════════════════════════════════════════════════


@callback(
    Output("node-action-hint", "children"),
    Output("node-action-hint", "style"),
    Input("flowchart", "tapNodeData"),
    State("node-states-store", "data"),
    State("dag-store", "data"),
    prevent_initial_call=True,
)
def on_node_hint(node_data, node_states, dag):
    base = {"fontSize": "13px", "marginTop": "8px", "fontStyle": "italic"}
    if not dag or not dag.get("nodes"):
        return (
            "⏳ 流程图正在渲染中，请稍候... 渲染完成后会通知你",
            dict(base, **{"color": "#f59e0b", "fontWeight": "bold"}),
        )
    if not node_data:
        return (
            "👆 流程图已就绪！请点击一个高亮（黄色/蓝色）节点再操作",
            dict(base, **{"color": "#10b981", "fontWeight": "bold"}),
        )
    nid = str(node_data.get("id", ""))
    st = str(node_states.get(nid, "pending"))
    if st == "running":
        return (
            "✅ 已选中节点 " + nid + "，现在可以「开始执行」或「跳过/做不到」",
            dict(base, **{"color": "#10b981", "fontWeight": "bold"}),
        )
    elif st == "done" or st == "completed":
        return "✅ 节点 " + nid + " 已完成", dict(base, **{"color": "#10b981"})
    elif st == "skipped":
        return "⏭️ 节点 " + nid + " 已跳过", dict(base, **{"color": "#9ca3af"})
    elif st == "failed":
        return "❌ 节点 " + nid + " 标记为做不到", dict(base, **{"color": "#ef4444"})
    else:
        return "⏳ 节点 " + nid + " 等待前置条件完成，暂时无法操作", dict(base, **{"color": "#f59e0b"})


@callback(
    Output("thread-id-store", "data"), Output("stream-interval", "disabled"),
    Output("stream-active", "data"), Output("global-status", "children"),
    Output("flowchart", "elements"), Output("submit-btn", "disabled"),
    Output("stop-btn", "disabled"), Output("start-exec-btn", "disabled"),
    Output("dag-store", "data"), Output("node-states-store", "data"),
    Output("progress-bar-fill", "style"), Output("task-start-time", "data"),
    Input("submit-btn", "n_clicks"), State("user-input",
                                           "value"), State("enable-refine", "value"),
    prevent_initial_call=True,
)
def on_submit(n_clicks, user_input, refine_value):
    empty_dag = {"nodes": [], "edges": []}
    empty_bar = {"width": "0%", "height": "100%",
                 "background": "linear-gradient(90deg, #10b981, #34d399)", "borderRadius": "6px"}
    if not user_input or not user_input.strip():
        return "", True, False, "⚠️ 请输入任务需求", [], False, True, True, empty_dag, {}, empty_bar, 0.0

    thread_id = str(uuid.uuid4())
    enable_refine = bool(refine_value and "refine" in refine_value)
    try:
        from .model.agent import run_task_stream
    except ImportError:
        return "", True, False, "❌ agent 模块未加载", [], False, True, True, empty_dag, {}, empty_bar, 0.0

    start_stream(thread_id=thread_id, user_input=user_input.strip(),
                 enable_refine=enable_refine, run_task_stream_fn=run_task_stream)
    return (thread_id, False, True,
            "🚀 任务已提交，正在生成流程图...",
            [], True, False, True, empty_dag, {}, empty_bar, time.time())


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
    State("thread-id-store", "data"), State("stream-active",
                                            "data"), State("task-start-time", "data"),
    prevent_initial_call=True,
)
def poll_stream_progress(n_intervals, thread_id, stream_active, task_start_time):
    now = time.time()
    elapsed = round(now - float(task_start_time),
                    1) if task_start_time else 0.0

    if not stream_active or not thread_id:
        return (dash.no_update, dash.no_update, True, False, True, True,
                dash.no_update, {"width": "0%", "height": "100%", "background": "transparent"})

    state = get_stream_state(thread_id)
    if not state:
        return (dash.no_update, "⚠️ 任务状态丢失 (⏱️ " + str(elapsed) + "s)", True, False, True, True,
                dash.no_update, {"width": "0%", "height": "100%", "background": "transparent"})

    latest = state.get_latest()
    direct_response = latest.get("direct_response", "")
    if direct_response:
        msg = "💬 " + direct_response + "\n\n⏱️ 总耗时 " + str(elapsed) + "s"
        return ([], dcc.Markdown(msg, style={"whiteSpace": "pre-wrap", "fontSize": "14px", "lineHeight": "1.8"}),
                True, False, True, True, dash.no_update,
                {"width": "100%", "height": "100%", "background": "linear-gradient(90deg, #10b981, #34d399)"})

    nodes = latest.get("nodes") or []
    edges = latest.get("edges") or []
    dag = {"nodes": nodes, "edges": edges}
    elements = dag_to_cytoscape(nodes, edges, {})

    status_text = str(latest.get("status_text", ""))
    if not status_text:
        steps = latest.get("steps", [])
        status_text = steps[-1] if steps else "处理中..."
    status_text = status_text + " (⏱️ " + str(elapsed) + "s)"

    if state.finished:
        if state.error:
            return (
                dash.no_update,  # elements — 保持已有图
                "❌ 任务失败: " + str(state.error) + " (⏱️ " + str(elapsed) + "s)",
                True, False, True, True,
                dash.no_update,  # dag-store — 保持
                {"width": "100%", "height": "100%",
                    "background": "#ef4444", "borderRadius": "6px"},
            )
    # ✅ 成功完成：更新 dag-store 确保数据在
    return (
        dash.no_update,  # elements — 保持已有图
        "✅ 流程图渲染完成！请先在图中点击一个高亮（黄色）节点，再选择操作",
        True, False, True, False,
        dag,  # ← 这里改成 dag，确保 dag-store 有数据
        {"width": "100%", "height": "100%",
            "background": "linear-gradient(90deg, #10b981, #34d399)", "borderRadius": "6px"},
    )
    return (elements, status_text, False, True, False, True, dag,
            {"className": "indeterminate-bar", "width": "100%", "height": "100%"})


@callback(
    Output("stream-interval", "disabled", allow_duplicate=True),
    Output("global-status", "children", allow_duplicate=True),
    Output("submit-btn", "disabled", allow_duplicate=True),
    Output("stop-btn", "disabled", allow_duplicate=True),
    Output("resume-btn", "disabled"),
    Input("stop-btn", "n_clicks"), State("thread-id-store", "data"),
    prevent_initial_call=True,
)
def on_stop(n_clicks, thread_id):
    if thread_id:
        cancel_stream(thread_id)
    return True, "⏹️ 已停止", False, True, False


@callback(
    Output("node-states-store", "data", allow_duplicate=True),
    Output("flowchart", "elements", allow_duplicate=True),
    Output("global-status", "children", allow_duplicate=True),
    Output("start-exec-btn", "disabled", allow_duplicate=True),
    Input("start-exec-btn", "n_clicks"), State("dag-store",
                                               "data"), State("node-states-store", "data"),
    prevent_initial_call=True,
)
def on_start_execution(n_clicks, dag, node_states):
    if not dag or not dag.get("nodes"):
        return dash.no_update, dash.no_update, "⚠️ 没有可执行的任务", True
    edges = dag.get("edges", [])
    in_deg = {}
    for e in edges:
        t = str(e["to"])
        in_deg[t] = in_deg.get(t, 0) + 1
    new_states = dict(node_states)
    for node in dag.get("nodes", []):
        nid = str(node["id"])
        if nid not in new_states and in_deg.get(nid, 0) == 0:
            new_states[nid] = "running"
    elements = dag_to_cytoscape(dag["nodes"], edges, new_states)
    running_count = sum(1 for v in new_states.values() if v == "running")
    return new_states, elements, "▶️ 正在执行 " + str(running_count) + " 个节点，完成后点击节点标记状态", True


@callback(
    Output("node-detail-panel", "children"),
    Output("selected-node-store", "data"),
    Output("skip-btn", "disabled"),
    Output("fail-btn", "disabled"),
    Input("flowchart", "tapNodeData"),
    State("dag-store", "data"),
    State("node-states-store", "data"),
)
def on_tap_node(node_data, dag, node_states):
    if not node_data:
        return dcc.Markdown("👆 **点击流程图中的节点查看详情并操作**", style={
            "fontSize": "14px", "color": "#94a3b8"
        }), "", True, True
    nid = str(node_data.get("id", ""))
    st = str(node_states.get(nid, "pending"))
    can_operate = (st == "running")

    md_text = build_detail_markdown(dict(node_data))
    buttons = []
    if can_operate:
        buttons.append(html.Button(
            "✅ 标记完成", id="complete-btn", n_clicks=0, style={
                "backgroundColor": "#10b981", "color": "white", "border": "none",
                "padding": "8px 20px", "borderRadius": "6px", "cursor": "pointer",
                "marginRight": "8px", "fontWeight": "bold",
            },
        ))
    panel_children = [dcc.Markdown(
        md_text, style={"fontSize": "14px", "lineHeight": "1.8"})]
    if buttons:
        panel_children.append(html.Div(buttons, style={"marginTop": "12px"}))
    return html.Div(panel_children), nid, not can_operate, not can_operate


@callback(
    Output("node-states-store", "data", allow_duplicate=True),
    Output("flowchart", "elements", allow_duplicate=True),
    Output("global-status", "children", allow_duplicate=True),
    Output("progress-bar-fill", "style", allow_duplicate=True),
    Output("start-exec-btn", "disabled", allow_duplicate=True),
    Input("complete-btn", "n_clicks"), State("selected-node-store", "data"),
    State("dag-store", "data"), State("node-states-store", "data"),
    prevent_initial_call=True,
)
def on_complete_node(n_clicks, selected_nid, dag, node_states):
    if not selected_nid or node_states.get(selected_nid) != "running":
        return (dash.no_update,) * 5
    new_states = dict(node_states)
    new_states[selected_nid] = "done"
    edges = dag.get("edges", [])
    for e in edges:
        if str(e["from"]) == selected_nid:
            tgt = str(e["to"])
            if new_states.get(tgt) in (None, "pending", "blocked"):
                all_done = True
                for pe in edges:
                    if str(pe["to"]) == tgt:
                        src = str(pe["from"])
                        if src not in new_states or new_states[src] != "done":
                            all_done = False
                            break
                if all_done:
                    new_states[tgt] = "running"
    nodes = dag.get("nodes", [])
    elements = dag_to_cytoscape(nodes, edges, new_states)
    done = sum(1 for v in new_states.values() if v in ("done", "completed"))
    total = len(nodes)
    pct = int(done / total * 100) if total > 0 else 0
    return (new_states, elements, f"✅ 完成 {done}/{total} ({pct}%)",
            {"width": f"{pct}%", "height": "100%",
             "background": "linear-gradient(90deg, #10b981, #34d399)", "borderRadius": "6px"},
            True)


@callback(
    Output("node-states-store", "data", allow_duplicate=True),
    Output("flowchart", "elements", allow_duplicate=True),
    Output("global-status", "children", allow_duplicate=True),
    Input("skip-btn", "n_clicks"), State("selected-node-store", "data"),
    State("dag-store", "data"), State("node-states-store", "data"),
    prevent_initial_call=True,
)
def on_skip_node(n_clicks, selected_nid, dag, node_states):
    if not selected_nid or node_states.get(selected_nid) != "running":
        return dash.no_update, dash.no_update, "⚠️ 请先选择要跳过的节点"
    new_states = dict(node_states)
    new_states[selected_nid] = "skipped"
    new_states = _cascade_skip(dag, new_states, selected_nid)
    edges = dag.get("edges", [])
    elements = dag_to_cytoscape(dag.get("nodes", []), edges, new_states)
    skipped = sum(1 for v in new_states.values() if v == "skipped")
    done = sum(1 for v in new_states.values() if v in ("done", "completed"))
    return new_states, elements, f"⏭️ 已跳过节点 {selected_nid} 及其下游 | 完成 {done} 跳过 {skipped}"


@callback(
    Output("node-states-store", "data", allow_duplicate=True),
    Output("flowchart", "elements", allow_duplicate=True),
    Output("global-status", "children", allow_duplicate=True),
    Input("fail-btn", "n_clicks"), State("selected-node-store", "data"),
    State("dag-store", "data"), State("node-states-store", "data"),
    prevent_initial_call=True,
)
def on_fail_node(n_clicks, selected_nid, dag, node_states):
    if not selected_nid or node_states.get(selected_nid) != "running":
        return dash.no_update, dash.no_update, "⚠️ 请先选择节点"
    new_states = dict(node_states)
    new_states[selected_nid] = "failed"
    new_states = _cascade_skip(dag, new_states, selected_nid)
    edges = dag.get("edges", [])
    elements = dag_to_cytoscape(dag.get("nodes", []), edges, new_states)
    return new_states, elements, f"❌ 节点 {selected_nid} 标记为「做不到」，下游已自动跳过"


# ══════════════════════════════════════════════════
#  历史记录 Callbacks
# ══════════════════════════════════════════════════

@callback(Output("history-dropdown", "options"), Input("refresh-btn", "n_clicks"), Input("main-tabs", "value"))
def load_history_list(n_clicks, tab_value):
    if tab_value != "tab-history":
        return []
    try:
        tasks = list_tasks(limit=50)
        return [{"label": str(t["title"])[:30] + " | " + str(t["task_id"])[-8:], "value": t["task_id"]} for t in tasks]
    except Exception:
        return []


@callback(
    Output("history-flowchart", "elements"),
    Output("history-detail", "children"),
    Output("history-flowchart", "zoom"),
    Output("history-flowchart", "pan"),
    Output("global-status", "children"),
    Output("dag-store", "data"),
    Input("history-dropdown", "value"),
)
def on_history_select(task_ids):
    empty_dag = {"nodes": [], "edges": []}
    if not task_ids:
        return [], dcc.Markdown("**请选择任务**"), 0.6, {"x": 0, "y": 0}, "👋 就绪，等待操作", empty_dag
    task_id = task_ids[0] if isinstance(task_ids, list) else task_ids
    try:
        data = load_task_with_plan(task_id)
    except Exception:
        return [], dcc.Markdown("**加载失败**"), 0.6, {"x": 0, "y": 0}, "❌ 加载失败", empty_dag
    if not data:
        return [], dcc.Markdown("**任务不存在**"), 0.6, {"x": 0, "y": 0}, "⚠️ 任务不存在", empty_dag

    nodes = data["plan"]["nodes"]
    edges = data["plan"]["edges"]
    elements = dag_to_cytoscape(nodes, edges, {})
    md_text = build_history_detail_markdown(task_id, nodes)
    dag_store_data = {"nodes": nodes, "edges": edges, "task_id": task_id}

    return (elements, dcc.Markdown(md_text, style={"fontSize": "14px", "lineHeight": "1.8"}),
            0.6, {"x": 0, "y": 0}, f"✅ 已加载历史流程图（{len(nodes)} 个节点）",
            dag_store_data)


@callback(
    Output("history-node-detail", "children"),
    Input("history-flowchart", "tapNodeData"),
)
def on_history_tap_node(node_data):
    if not node_data:
        return dcc.Markdown("**点击流程图中的节点查看详情**")
    md = build_detail_markdown(dict(node_data))
    return dcc.Markdown(md, style={"fontSize": "13px", "lineHeight": "1.8"})


@callback(
    Output("history-dropdown", "options", allow_duplicate=True),
    Output("delete-status", "children"),
    Input("delete-btn", "n_clicks"), State("history-dropdown", "value"), prevent_initial_call=True,
)
def on_delete(n_clicks, task_ids):
    if not task_ids:
        return dash.no_update, "⚠️ 请先选择要删除的任务"
    ids = task_ids if isinstance(task_ids, list) else [task_ids]
    try:
        count = batch_delete_tasks(ids)
        tasks = list_tasks(limit=50)
        options = [{"label": str(t["title"])[
            :30] + " | " + str(t["task_id"])[-8:], "value": t["task_id"]} for t in tasks]
        return options, f"✅ 已删除 {count} 个任务"
    except Exception as e:
        return dash.no_update, f"❌ 删除失败: {e}"


# ══════════════════════════════════════════════════
#  数据导出：JSON / DOT / HTML
# ══════════════════════════════════════════════════

@callback(
    Output("export-download", "data"),
    Input("export-data-btn", "n_clicks"),
    State("history-dropdown", "value"),
    State("dag-store", "data"),
    State("data-format", "value"),
    prevent_initial_call=True,
)
def on_export_data(n_clicks, history_task_ids, dag_store, fmt):
    if history_task_ids:
        task_id = history_task_ids[0] if isinstance(
            history_task_ids, list) else history_task_ids
        data = load_task_with_plan(task_id)
        if not data:
            return None
        nodes = data["plan"]["nodes"]
        edges = data["plan"]["edges"]
        task_id_str = str(task_id)[-8:]
    else:
        nodes = dag_store.get("nodes", [])
        edges = dag_store.get("edges", [])
        task_id_str = "current"

    if fmt == "json":
        return dcc.send_string(
            json.dumps({"nodes": nodes, "edges": edges},
                       ensure_ascii=False, indent=2),
            f"{task_id_str}.json"
        )
    elif fmt == "dot":
        lines = ["digraph G {"]
        for n in nodes:
            lines.append(f'  {n.get("id", "")} [label="{
                         n.get("name", n.get("node_name", ""))}"];')
        for e in edges:
            lines.append(
                f'  {e.get("from", "")} -> {e.get("to", "")} [label="{e.get("label", "")}"];')
        lines.append("}")
        return dcc.send_string("\n".join(lines), f"{task_id_str}.dot")
    elif fmt == "html":
        return dcc.send_string(
            _generate_html_export(nodes, edges, task_id_str),
            f"{task_id_str}.html"
        )
    return None


# ══════════════════════════════════════════════════
#  【核心】图片导出：纯 Python 后端渲染
#  不依赖前端 Cytoscape，不依赖浏览器
# ══════════════════════════════════════════════════


@callback(
    Output("export-download", "data", allow_duplicate=True),
    Input("export-image-btn", "n_clicks"),
    State("history-dropdown", "value"),
    State("dag-store", "data"),
    State("node-states-store", "data"),
    prevent_initial_call=True,
)
def on_export_image(n_clicks, history_task_ids, dag_store, node_states):
    """
    点击「⬇️ 导出图片」→ 从 dag-store（或历史任务）取数据
    → NetworkX + Matplotlib 绘制高清 PNG
    → dcc.send_file 触发浏览器下载

    不依赖前端 Cytoscape 实例，不依赖浏览器，
    不依赖 Chromium/Playwright/Selenium。100% 可靠。
    """
    # ── 确定数据源 ──
    if history_task_ids:
        task_id = history_task_ids[0] if isinstance(
            history_task_ids, list) else history_task_ids
        data = load_task_with_plan(task_id)
        if not data:
            logger.warning("[Export] 未找到任务数据: %s", task_id)
            return None
        nodes = data["plan"]["nodes"]
        edges = data["plan"]["edges"]
        task_id_str = str(task_id)[-8:]
    else:
        nodes = dag_store.get("nodes", [])
        edges = dag_store.get("edges", [])
        task_id_str = "current"

    if not nodes:
        logger.warning("[Export] 没有节点数据可导出")
        return None

    # ── 准备输出路径 ──
    tmp_dir = tempfile.mkdtemp(prefix="dag_export_")
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"flowchart_{task_id_str}_{timestamp}.png"
    output_path = os.path.join(tmp_dir, filename)

    # ── 导出 PNG ──
    try:
        from .model.pyvis_export import export_dag_to_png

        title = f"流程图 {task_id_str}"
        result_path = export_dag_to_png(
            nodes=nodes,
            edges=edges,
            output_path=output_path,
            node_states=node_states,
            title=title,
            width=1600,
            height=1000,
            dpi=200,
        )

        if not os.path.exists(result_path):
            logger.error("[Export] 文件未生成: %s", result_path)
            return None

        file_size = os.path.getsize(result_path)
        logger.info("[Export] ✅ 导出成功: %s (%.1f KB)",
                    result_path, file_size / 1024)

        return dcc.send_file(result_path, filename=filename)

    except Exception as e:
        logger.error("[Export] 图片导出失败: %s", e, exc_info=True)
        return None


# ══════════════════════════════════════════════════
#  图操作 Clientside Callbacks（带延迟 fit）
# ══════════════════════════════════════════════════
clientside_callback(
    """function(n_clicks) {
        if (!n_clicks) return window.dash_clientside.no_update;
        var cy = document.getElementById('flowchart') && document.getElementById('flowchart')._cyRef;
        if (!cy) return window.dash_clientside.no_update;
        setTimeout(function() {
            cy.layout({name:'dagre',rankDir:'TB',nodeSep:300,rankSep:450,edgeSep:80,fit:true,padding:80}).run();
            cy.fit(cy.elements(), 80);
        }, 300);
        return window.dash_clientside.no_update;
    }""",
    Output("fit-btn", "n_clicks"), Input("fit-btn", "n_clicks"),
)

clientside_callback(
    """function(n_clicks_in, n_clicks_out, current_value) {
        var ctx = window.dash_clientside.callback_context;
        if (!ctx || !ctx.triggered || ctx.triggered.length === 0) return window.dash_clientside.no_update;
        var cy = document.getElementById('flowchart') && document.getElementById('flowchart')._cyRef;
        if (!cy) return cy ? cy.zoom() : 0.6;
        var cur = cy.zoom();
        if (ctx.triggered[0].prop_id.indexOf('zoom-in') !== -1) cy.zoom(cur + 0.2);
        else if (ctx.triggered[0].prop_id.indexOf('zoom-out') !== -1) cy.zoom(Math.max(0.2, cur - 0.2));
        return cy.zoom();
    }""",
    Output("zoom-slider", "value"),
    Input("zoom-in-btn", "n_clicks"), Input("zoom-out-btn", "n_clicks"),
)

clientside_callback(
    """function(val) { if (val==null) return window.dash_clientside.no_update;
        var cy = document.getElementById('flowchart') && document.getElementById('flowchart')._cyRef;
        if (cy) cy.zoom(val); return window.dash_clientside.no_update; }""",
    Output("flowchart", "zoom"), Input("zoom-slider", "value"),
)

# ═══ 历史页面图控制 ═══
clientside_callback(
    """function(n_clicks) {
        if (!n_clicks) return window.dash_clientside.no_update;
        var cy = document.getElementById('history-flowchart') && document.getElementById('history-flowchart')._cyRef;
        if (!cy) return window.dash.clientside.no_update;
        setTimeout(function() {
            cy.layout({name:'dagre',rankDir:'TB',nodeSep:250,rankSep:380,edgeSep:60,fit:true,padding:60}).run();
            cy.fit(cy.elements(), 80);
        }, 300);
        return window.dash_clientside.no_update;
    }""",
    Output("history-fit-btn", "n_clicks"), Input("history-fit-btn", "n_clicks"),
)

clientside_callback(
    """function(n_clicks_in, n_clicks_out, current_value) {
        var ctx = window.dash_clientside.callback_context;
        if (!ctx || !ctx.triggered || ctx.triggered.length === 0) return window.dash_clientside.no_update;
        var cy = document.getElementById('history-flowchart') && document.getElementById('history-flowchart')._cyRef;
        if (!cy) return cy ? cy.zoom() : 0.6;
        var cur = cy.zoom();
        if (ctx.triggered[0].prop_id.indexOf('history-zoom-in') !== -1) cy.zoom(cur + 0.2);
        else if (ctx.triggered[0].prop_id.indexOf('history-zoom-out') !== -1) cy.zoom(Math.max(0.2, cur - 0.2));
        return cy.zoom();
    }""",
    Output("history-zoom-slider", "value"),
    Input("history-zoom-in-btn",
          "n_clicks"), Input("history-zoom-out-btn", "n_clicks"),
)

clientside_callback(
    """function(val) { if (val==null) return window.dash_clientside.no_update;
        var cy = document.getElementById('history-flowchart') && document.getElementById('history-flowchart')._cyRef;
        if (cy) cy.zoom(val); return window.dash_clientside.no_update; }""",
    Output("history-flowchart", "zoom"), Input("history-zoom-slider", "value"),
)

# ══════════════════════════════════════════════════
#  启动
# ══════════════════════════════════════════════════


def main() -> None:
    host = os.environ.get("DASH_HOST", "0.0.0.0")
    port = int(os.environ.get("DASH_PORT", "7860"))
    debug = os.environ.get("DASH_DEBUG", "false").lower() == "true"
    logger.info("🚀 启动 Dash | %s:%d debug=%s", host, port, debug)
    app.run(debug=debug, host=host, port=port)


if __name__ == "__main__":
    main()
