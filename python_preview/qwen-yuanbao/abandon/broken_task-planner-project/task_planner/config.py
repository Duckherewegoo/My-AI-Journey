"""
config.py — 全局配置中心（生产最终版）
══════════════════════════════════════════════════
所有模块的唯一依赖源。集中管理：
  ✅ 日志 / DashScope / 模型 / 思考模式
  ✅ 超时重试 / MongoDB / Gradio
  ✅ 渲染导出（SVG / PNG / PDF / DOT / HTML / JSON）
  ✅ 任务状态枚举（全模块共用）
  ✅ Prompt 模板（JSON 大括号全部 {{}} 转义）
"""
import os

# ══════════════════════════════════════════════════
#  日志
# ══════════════════════════════════════════════════
DEBUG = os.getenv("DEBUG", "true").lower() == "true"
LOG_DIR = os.getenv("LOG_DIR", "/app/logs")
LOG_FILE = os.getenv("LOG_FILE", "task_planner.log")
LOG_MAX_DAYS = int(os.getenv("LOG_MAX_DAYS", "7"))
LOG_CONSOLE_LEVEL = "DEBUG" if DEBUG else "WARNING"

# ══════════════════════════════════════════════════
#  DashScope
# ══════════════════════════════════════════════════
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "") or None
DASHSCOPE_REGION = os.getenv("DASHSCOPE_REGION", "cn-beijing")
USE_MOCK_LLM = os.getenv("USE_MOCK_LLM", "false").lower() == "true"

# ══════════════════════════════════════════════════
#  模型（真实模型，零 Mock）
# ══════════════════════════════════════════════════
LLM_INTENT_MODEL = os.getenv("LLM_INTENT_MODEL", "qwen3.7-flash-2026-07-15")
LLM_PLANNER_MODEL = os.getenv("LLM_PLANNER_MODEL", "qwen3.7-flash-2026-07-15")
LLM_NODE_MODEL = os.getenv("LLM_NODE_MODEL", "qwen3.7-flash-2026-07-15")

# ══════════════════════════════════════════════════
#  思考模式
# ══════════════════════════════════════════════════
LLM_INTENT_ENABLE_THINKING = (
    os.getenv("LLM_INTENT_ENABLE_THINKING", "false").lower() == "true"
)
LLM_PLANNER_ENABLE_THINKING = (
    os.getenv("LLM_PLANNER_ENABLE_THINKING", "true").lower() == "true"
)
LLM_NODE_ENABLE_THINKING = (
    os.getenv("LLM_NODE_ENABLE_THINKING", "false").lower() == "true"
)
LLM_THINKING_BUDGET = int(os.getenv("LLM_THINKING_BUDGET", "81920"))

# ══════════════════════════════════════════════════
#  超时 / 重试
# ══════════════════════════════════════════════════
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))          # 秒
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
LLM_RETRY_BACKOFF = int(os.getenv("LLM_RETRY_BACKOFF", "2"))
LLM_TASK_TOTAL_TIMEOUT = int(os.getenv("LLM_TASK_TOTAL_TIMEOUT", "300"))
MAX_TASK_RETRIES = int(os.getenv("MAX_TASK_RETRIES", "3"))

# 单节点执行超时（秒）—— 防止一个节点卡死拖垮全局
LLM_NODE_TIMEOUT = int(os.getenv("LLM_NODE_TIMEOUT", "60"))

# ══════════════════════════════════════════════════
#  MongoDB
# ══════════════════════════════════════════════════
MONGO_HOST = os.getenv("MONGO_HOST", "task_mongodb")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DB = os.getenv("MONGO_DB", "task_planner_db")

# ══════════════════════════════════════════════════
#  Gradio
# ══════════════════════════════════════════════════
GRADIO_HOST = os.getenv("GRADIO_HOST", "0.0.0.0")
GRADIO_PORT = int(os.getenv("GRADIO_PORT", "7860"))
ENABLE_MCP = os.getenv("ENABLE_MCP", "false").lower() == "true"

# ══════════════════════════════════════════════════
#  渲染 / 导出
# ══════════════════════════════════════════════════
RENDER_DPI = int(os.getenv("RENDER_DPI", "300"))
RENDER_FONT = os.getenv("RENDER_FONT", "Noto Sans CJK SC")
RENDER_DIR = os.getenv("RENDER_DIR", "/app/exports")
RENDER_WIDTH = int(os.getenv("RENDER_WIDTH", "1200"))
RENDER_HEIGHT = int(os.getenv("RENDER_HEIGHT", "600"))

# ✅ 导出格式 —— 全部真实可用
#     svg  : pyvis HTML → cairosvg 提取 SVG
#     png  : SVG → cairosvg 转 PNG (300DPI)
#     pdf  : SVG → cairosvg 转 PDF (300DPI, A4)
#     dot  : networkx → pydot → DOT 源码
#     html : pyvis 完整交互式 HTML
#     json : 节点/边 JSON 数据
SUPPORTED_EXPORT_FORMATS = ["svg", "png", "pdf", "dot", "html", "json"]
DEFAULT_EXPORT_FORMAT = "svg"

# ══════════════════════════════════════════════════
#  任务状态枚举（全模块共用）
# ══════════════════════════════════════════════════
TASK_STATUS = {
    "PENDING": 0,
    "RUNNING": 1,
    "SUCCESS": 2,
    "FAILED": 3,
    "TIMEOUT": 4,
}

# 状态 → 中文描述
STATUS_TEXT = {
    0: "⏳ 待处理",
    1: "🔄 进行中",
    2: "✅ 成功",
    3: "❌ 失败",
    4: "⏰ 超时",
}

# 状态 → 节点背景色
STATUS_COLOR = {
    0: "#fff3e0",
    1: "#e3f2fd",
    2: "#e8f5e9",
    3: "#ffebee",
    4: "#f3e5f5",
}

# 状态 → 边框色
STATUS_BORDER = {
    0: "#f59e0b",
    1: "#3b82f6",
    2: "#10b981",
    3: "#ef4444",
    4: "#9c27b0",
}

# 状态 → 图标
STATUS_ICONS = {
    0: "⏳",
    1: "🔄",
    2: "✅",
    3: "❌",
    4: "⏰",
}

# 兼容旧名
NODE_STATUS_COLORS = STATUS_COLOR
NODE_STATUS_BORDERS = STATUS_BORDER
NODE_STATUS_ICONS = STATUS_ICONS

# ══════════════════════════════════════════════════
#  Prompt 模板（JSON 大括号全部 {{}} 转义，仅留 {user_input} 等占位符）
# ══════════════════════════════════════════════════
INTENT_PROMPT = """你是一个通用任务规划意图识别器。
分析用户的任务需求，判断是否需要分解为有向无环图（DAG）。

⚠️ 严格遵守规则：
1. 仅返回标准JSON，无任何解释、Markdown、注释
2. category只能从以下值中选（必须英文小写）：cooking、engineering、logistics、learning、life_admin、creative、other
3. 所有字段必须存在，不能为null

返回格式：
{{
  "needs_planning": true,
  "category": "cooking",
  "summary": "用一句话概括任务核心目标",
  "complexity": "simple"
}}

判断标准：
- 多步骤/有依赖/可拆解 → needs_planning: true
- 纯问答/闲聊/单一指令 → needs_planning: false

用户输入：{user_input}
"""

PLANNER_PROMPT = """你是一个专业的通用任务规划助手。
将用户需求分解为有序的、可独立执行的有向无环图（DAG）节点。

⚠️ 严格遵守规则：
1. 仅返回标准JSON，无任何解释、Markdown、注释
2. 每个节点是原子化、可验证的行动步骤
3. 节点名称用「动词+宾语」格式，简洁明确
4. 边的label写清依赖条件

返回格式：
{{
  "task_name": "任务标题",
  "description": "任务整体描述",
  "nodes": [
    {{"id": 1, "name": "行动目标（动词+宾语）", "detail": "该步骤的具体说明"}},
    {{"id": 2, "name": "下一个行动目标", "detail": "该步骤的具体说明"}}
  ],
  "edges": [
    {{"from": 1, "to": 2, "label": "依赖条件说明"}}
  ]
}}

用户需求：{user_input}
任务类别：{category}
意图摘要：{summary}
"""

NODE_REFINE_PROMPT = """你是一个专业的通用任务执行专家。
对以下任务节点补充具体、可执行、可验证的行动细节。

⚠️ 仅返回标准JSON，无任何额外解释：
{{
  "name": "优化后的节点名称（动词+宾语，不超过20字）",
  "detail": "分步骤写清具体操作逻辑，用\\n分隔步骤。包含：关键参数、判断标准、注意事项、可能踩的坑",
  "meta": {{
    "preconditions": ["执行该节点的前置条件1", "前置条件2"],
    "postconditions": ["执行成功后的预期结果1", "预期结果2"],
    "retry_policy": "失败后怎么重试、最多几次、什么情况下放弃"
  }}
}}

节点信息：{node_json}
用户原始需求：{user_input}
任务领域：{category}
"""
