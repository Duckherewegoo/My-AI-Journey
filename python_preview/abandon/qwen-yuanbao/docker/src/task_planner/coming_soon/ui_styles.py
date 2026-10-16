"""Dash / Cytoscape UI 样式常量。从 config.py 解耦，保持配置文件纯净。"""

CYTO_STYLESHEET = [...]      # 原 CYTO_STYLESHEET 完整移入
PULSE_CSS = "..."            # 原 PULSE_CSS 完整移入
PROGRESS_CSS = "..."         # 原 PROGRESS_CSS 完整移入
BAR_DONE = {...}             # 原 BAR_DONE 完整移入
BAR_ERROR = {...}            # 原 BAR_ERROR 完整移入
BAR_LOADING = {...}          # 原 BAR_LOADING 完整移入
EMPTY_BAR_STYLE = {...}      # 原 EMPTY_BAR_STYLE 完整移入
EMPTY_BAR_MINI_STYLE = {...}  # 原 EMPTY_BAR_MINI_STYLE 完整移入
MARKDOWN_PRE_STYLE = {...}   # 原 MARKDOWN_PRE_STYLE 完整移入
HINT_BASE_STYLE = {...}      # 原 HINT_BASE_STYLE 完整移入
HINT_STYLES = {...}          # 原 HINT_STYLES 完整移入
BASE_BTN_STYLE = {...}       # 原 BASE_BTN_STYLE 完整移入
STATE_COLORS = {...}         # 原 STATE_COLORS 完整移入
STATE_LABELS = {...}         # 原 STATE_LABELS 完整移入
EDGE_STYLES = {...}          # 原 EDGE_STYLES 完整移入（依赖 config.EDGE_TYPE_*）
DEFAULT_EDGE_STYLE = EDGE_STYLES["hard"]
