"""
config.py — 全局配置中心
═══════════════════════════════════════════════════════════════
单一事实来源（Single Source of Truth）。
本文件仅包含运行时配置与业务常量，不包含 UI 样式、JS 模板和 Prompt 模板。

依赖方向（自上而下，禁止反向引用）：
  [0] 环境基础设施  →  [1] 外部服务  →  [2] LLM  →  [3] 业务枚举
  →  [4] 派生映射   →  [5] 安全/正则  →  [6] 向后兼容

外置模块：
  - prompts.py        : Prompt 模板库
  - clientside.py     : Cytoscape JS 模板与图配置注册表
  - ui_styles.py      : Dash/Cytoscape 样式常量、CSS 动画、按钮样式
═══════════════════════════════════════════════════════════════
"""

import os
import re
import logging
import warnings
from typing import Any, Callable, FrozenSet

# ─────────────────────────────────────────────────────────────
#  0. 环境基础设施
# ─────────────────────────────────────────────────────────────

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)


def _env(key: str, default: Any = None, cast: Callable = str) -> Any:
    """
    防御性环境变量解析器。
    - bool 转换支持 true/1/yes/on/y（大小写不敏感）
    - 转换失败时记录 WARNING 并返回默认值，永不抛出异常
    """
    val = os.getenv(key)
    if val is None:
        return default
    try:
        if cast is bool:
            return val.strip().lower() in ("true", "1", "yes", "on", "y")
        return cast(val)
    except (ValueError, TypeError):
        logger.warning(
            "环境变量 %s='%s' 无法转换为 %s，回退默认值: %s",
            key, val, cast.__name__, default,
        )
        return default


# ─────────────────────────────────────────────────────────────
#  1. 外部服务连接
# ─────────────────────────────────────────────────────────────

# MongoDB
MONGO_HOST = _env("MONGO_HOST", "task_mongodb")
MONGO_PORT = _env("MONGO_PORT", 27017, int)
MONGO_DB = _env("MONGO_DB", "task_planner_db")

# DashScope
DASHSCOPE_API_KEY = _env("DASHSCOPE_API_KEY", "")
_dashscope_url = _env("DASHSCOPE_BASE_URL", "")
DASHSCOPE_BASE_URL = _dashscope_url if _dashscope_url else None
DASHSCOPE_REGION = _env("DASHSCOPE_REGION", "cn-beijing")
USE_MOCK_LLM = _env("USE_MOCK_LLM", False, bool)

# Gradio
GRADIO_HOST = _env("GRADIO_HOST", "0.0.0.0")
GRADIO_PORT = _env("GRADIO_PORT", 7860, int)
ENABLE_MCP = _env("ENABLE_MCP", False, bool)

# Dash
DASH_HOST = _env("DASH_HOST", "0.0.0.0")
DASH_PORT = _env("DASH_PORT", 7860, int)
VALID_PORT_RANGE = range(1, 65536)

# 日志
DEBUG = _env("DEBUG", True, bool)
LOG_DIR = _env("LOG_DIR", os.path.join(_PROJECT_ROOT, "logs"))
LOG_FILE = _env("LOG_FILE", "task_planner.log")
LOG_MAX_DAYS = _env("LOG_MAX_DAYS", 7, int)
LOG_CONSOLE_LEVEL = "DEBUG" if DEBUG else "INFO"

# ─────────────────────────────────────────────────────────────
#  2. LLM 模型与推理参数
# ─────────────────────────────────────────────────────────────

# 模型选择
LLM_INTENT_MODEL = _env("LLM_INTENT_MODEL", "qwen3.7-flash-2026-07-15")
LLM_PLANNER_MODEL = _env("LLM_PLANNER_MODEL", "qwen3.7-flash-2026-07-15")
LLM_NODE_MODEL = _env("LLM_NODE_MODEL", "qwen3.7-flash-2026-07-15")

# 思考模式
LLM_INTENT_ENABLE_THINKING = _env("LLM_INTENT_ENABLE_THINKING", False, bool)
LLM_PLANNER_ENABLE_THINKING = _env("LLM_PLANNER_ENABLE_THINKING", True, bool)
LLM_NODE_ENABLE_THINKING = _env("LLM_NODE_ENABLE_THINKING", False, bool)
LLM_THINKING_BUDGET = _env("LLM_THINKING_BUDGET", 81920, int)

# 超时与重试
LLM_TIMEOUT = _env("LLM_TIMEOUT", 120, int)
LLM_MAX_RETRIES = _env("LLM_MAX_RETRIES", 3, int)
LLM_RETRY_BACKOFF = _env("LLM_RETRY_BACKOFF", 2, int)
LLM_TASK_TOTAL_TIMEOUT = _env("LLM_TASK_TOTAL_TIMEOUT", 300, int)
MAX_TASK_RETRIES = _env("MAX_TASK_RETRIES", 3, int)
LLM_NODE_TIMEOUT = _env("LLM_NODE_TIMEOUT", 60, int)

# ⚠️ 自动校正：思考模式下节点超时不低于全局超时
if LLM_NODE_ENABLE_THINKING and LLM_NODE_TIMEOUT < LLM_TIMEOUT:
    warnings.warn(
        f"[Config] LLM_NODE_TIMEOUT({LLM_NODE_TIMEOUT}s) < LLM_TIMEOUT({
            LLM_TIMEOUT}s) "
        f"且节点思考模式已开启，自动提升至 {LLM_TIMEOUT}s",
        UserWarning,
    )
    LLM_NODE_TIMEOUT = LLM_TIMEOUT

# Mock 标识
MOCK_RESPONSE_PREFIX: str = "[MOCK_LLM_RESPONSE]"

# ─────────────────────────────────────────────────────────────
#  3. 业务枚举（原子常量，无外部依赖）
# ─────────────────────────────────────────────────────────────

# 任务状态码
TASK_STATUS = {
    "PENDING": 0, "RUNNING": 1, "SUCCESS": 2,
    "FAILED": 3, "TIMEOUT": 4, "SKIPPED": 5,
}

# 边类型
EDGE_TYPE_HARD = "hard"
EDGE_TYPE_SOFT = "soft"
EDGE_TYPE_CONDITIONAL = "conditional"
EDGE_TYPE_RETRY = "retry"
DEFAULT_EDGE_TYPE = EDGE_TYPE_HARD

VALID_EDGE_TYPES: FrozenSet[str] = frozenset({
    EDGE_TYPE_HARD, EDGE_TYPE_SOFT, EDGE_TYPE_CONDITIONAL, EDGE_TYPE_RETRY,
})

# 意图分类白名单
VALID_INTENT_CATEGORIES: FrozenSet[str] = frozenset({
    "cooking", "engineering", "logistics", "learning",
    "life_admin", "creative", "consultation", "other",
})
VALID_INTENT_COMPLEXITIES: FrozenSet[str] = frozenset(
    {"simple", "medium", "complex"})

# ─────────────────────────────────────────────────────────────
#  4. 派生映射（仅依赖上方原子常量）
# ─────────────────────────────────────────────────────────────

# 状态 → 展示属性
STATUS_TEXT = {0: "⏳ 待处理", 1: "🔄 进行中",
               2: "✅ 成功", 3: "❌ 失败", 4: "⏰ 超时", 5: "⏭️ 已跳过"}
STATUS_ICONS = {0: "⏳", 1: "🔄", 2: "✅", 3: "❌", 4: "⏰", 5: "⏭️"}
STATUS_COLOR = {0: "#fff3e0", 1: "#e3f2fd", 2: "#e8f5e9",
                3: "#ffebee", 4: "#f3e5f5", 5: "#f5f5f5"}
STATUS_BORDER = {0: "#f59e0b", 1: "#3b82f6", 2: "#10b981",
                 3: "#ef4444", 4: "#9c27b0", 5: "#9e9e9e"}
NODE_TEXT_COLORS = {0: "#92400e", 1: "#1e3a8a",
                    2: "#14532d", 3: "#991b1b", 4: "#6b21a8", 5: "#374151"}

# 聚合节点颜色元组 (bg, border, text)
NODE_COLORS = {
    name: (STATUS_COLOR[code], STATUS_BORDER[code],
           NODE_TEXT_COLORS.get(code, "#374151"))
    for name, code in {"pending": 0, "running": 1, "done": 2, "failed": 3, "timeout": 4, "skipped": 5}.items()
}
NODE_COLORS["completed"] = NODE_COLORS["done"]
NODE_COLORS["default"] = ("#ffffff", "#e5e7eb", "#374151")

# 节点样式快捷查找
NODE_STYLES = {code: {"bg": STATUS_COLOR[code], "border": STATUS_BORDER[code],
                      "icon": STATUS_ICONS[code]} for code in STATUS_COLOR}
NODE_OPERABLE_STATES = {"pending", "running", "failed"}
NODE_STATUS_CODE_MAP = {0: "pending", 1: "running",
                        2: "done", 3: "failed", 4: "skipped"}

# 节点操作行为契约
NODE_ACTION_CONFIG = {
    "done":    {"unlock_downstream": True,  "label": "完成", "icon": "✅"},
    "skipped": {"unlock_downstream": False, "label": "跳过", "icon": "⏭️"},
    "failed":  {"unlock_downstream": False, "label": "失败", "icon": "❌"},
}

# 边类型 → 渲染属性
EDGE_TYPE_CSS = {EDGE_TYPE_HARD: "edge-hard", EDGE_TYPE_SOFT: "edge-soft",
                 EDGE_TYPE_CONDITIONAL: "edge-conditional", EDGE_TYPE_RETRY: "edge-retry"}
EDGE_TYPE_COLOR = {EDGE_TYPE_HARD: "#64748b", EDGE_TYPE_SOFT: "#94a3b8",
                   EDGE_TYPE_CONDITIONAL: "#f59e0b", EDGE_TYPE_RETRY: "#ef4444"}
EDGE_TYPE_STYLE = {EDGE_TYPE_HARD: "solid", EDGE_TYPE_SOFT: "dashed",
                   EDGE_TYPE_CONDITIONAL: "dashdot", EDGE_TYPE_RETRY: "dotted"}
EDGE_DASH_MAP = {"dashed": [10, 5], "dashdot": [15, 5, 5, 5], "dotted": [3, 3]}

# 渲染参数
RENDER_DPI = _env("RENDER_DPI", 300, int)
RENDER_FONT = _env("RENDER_FONT", "Noto Sans CJK SC")
RENDER_DIR = _env("RENDER_DIR", os.path.join(_PROJECT_ROOT, "exports"))
RENDER_WIDTH = _env("RENDER_WIDTH", 1200, int)
RENDER_HEIGHT = _env("RENDER_HEIGHT", 600, int)
RENDER_EDGE_WIDTH = _env("RENDER_EDGE_WIDTH", 2.0, float)
RENDER_EDGE_LABEL_FONT_SIZE = _env("RENDER_EDGE_LABEL_FONT_SIZE", 10, int)
RENDER_SHOW_EDGE_LABELS = _env("RENDER_SHOW_EDGE_LABELS", True, bool)
FONT_FACE = "'Noto Sans CJK SC', 'WenQuanYi Zen Hei', 'Microsoft YaHei', 'SimHei', 'DejaVu Sans', Arial, sans-serif"
SUPPORTED_EXPORT_FORMATS = ["svg", "png", "pdf", "dot", "html", "json"]
DEFAULT_EXPORT_FORMAT = "svg"

# 空状态哨兵对象（避免每次创建新字典）
EMPTY_DAG = {"nodes": [], "edges": []}
EMPTY_STATES = {}

# 视图字段白名单
USER_VISIBLE_NODE_FIELDS = {"id", "name", "details", "status", "result"}
HISTORY_LABEL_MAX_LEN = 30

HINT_TEMPLATES = {
    "running": "✅ 已选中节点 {nid}，现在可以「开始执行」或「跳过/做不到」",
    "done":    "✅ 节点 {nid} 已完成",
    "skipped": "⏭️ 节点 {nid} 已跳过",
    "failed":  "❌ 节点 {nid} 标记为做不到",
    "pending": "⏳ 节点 {nid} 等待前置条件完成，暂时无法操作",
}

# ─────────────────────────────────────────────────────────────
#  5. 安全与正则
# ─────────────────────────────────────────────────────────────

MAX_INPUT_LENGTH = 2000
MAX_CACHE_INPUT_BYTES = 10 * 1024 * 1024  # 10 MB
SESSION_TTL = 3600

THINK_RE = re.compile(r'<think>.*?</think>', re.DOTALL)
_UNREPLACED_PATTERN = re.compile(r'\$\{(\w+)\}|(?<!\$)\$(\w+)')

SKIP_PLANNING_PATTERNS = [
    re.compile(r"不[需要]?(?:要|用).{0,6}(?:流程图|DAG|图表|拆解|步骤|规划)"),
    re.compile(
        r"(?:直接|只要|请).{0,8}(?:告诉|教|回答|给出|说明).{0,10}(?:方法|策略|建议|结论|做法|答案)"),
    re.compile(r"(?:跳过|别|莫).{0,4}(?:规划|画图|拆解|流程)"),
    re.compile(r"不[需要]?(?:要|用).{0,4}画.{0,4}图"),
]

_SENSITIVE_PATTERNS_CONFIG = [
    (r'sk-[a-zA-Z0-9]{20,}', '[REDACTED_API_KEY]'),
    (r'AKIA[A-Z0-9]{16,}', '[REDACTED_AWS_KEY]'),
    (r'ghp_[a-zA-Z0-9]{36,}', '[REDACTED_GITHUB_TOKEN]'),
    (r'xox[bpr]-[a-zA-Z0-9-]+', '[REDACTED_SLACK_TOKEN]'),
    ((r'password\s*[:=]\s*\S{1,200}', re.IGNORECASE), 'password=[REDACTED]'),
    ((r'token\s*[:=]\s*\S{1,200}', re.IGNORECASE), 'token=[REDACTED]'),
    ((r'api_key\s*[:=]\s*\S{1,200}', re.IGNORECASE), 'api_key=[REDACTED]'),
    ((r'secret\s*[:=]\s*\S{1,200}', re.IGNORECASE), 'secret=[REDACTED]'),
    (r'\b1[3-9]\d{9}\b', '[REDACTED_PHONE]'),
    (r'\b\d{17}[\dXx]\b', '[REDACTED_ID_CARD]'),
]

SENSITIVE_PATTERNS = [
    (re.compile(p) if isinstance(p, str) else re.compile(*p), r)
    for p, r in _SENSITIVE_PATTERNS_CONFIG
]

BLOCKED_WORDS: set = set()  # TODO: 从配置文件/数据库加载

# ─────────────────────────────────────────────────────────────
#  6. 向后兼容别名（集中管理，便于未来清理）
# ─────────────────────────────────────────────────────────────

NODE_STATUS_COLORS = STATUS_COLOR
NODE_STATUS_BORDERS = STATUS_BORDER
NODE_STATUS_ICONS = STATUS_ICONS
