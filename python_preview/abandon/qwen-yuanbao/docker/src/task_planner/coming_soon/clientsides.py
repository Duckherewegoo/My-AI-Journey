"""Cytoscape 客户端回调模板与图配置注册表。"""
import json
from dash import clientside_callback, Input, Output
from config import _GRAPH_CONFIGS  # 仅导入配置数据，不含 JS

FIT_JS_TEMPLATE = "..."
ZOOM_BTN_JS_TEMPLATE = "..."
ZOOM_SLIDER_JS_TEMPLATE = "..."


def register_graph_callbacks():
    """动态注册所有图的客户端回调。在 app.py 启动时调用一次。"""
    for key, cfg in _GRAPH_CONFIGS.items():
        clientside_callback(...)  # fit
        clientside_callback(...)  # zoom btn
        clientside_callback(...)  # zoom slider
