🧠 通用任务规划助手 (Task Planner)

AI 自动分解任务为 DAG 流程图，逐步执行，可视化交互

基于 LangGraph 的多步任务规划 Agent，配合 Dash + Cytoscape.js 提供流畅的 DAG 流程图交互体验。支持节点悬停详情、流式执行进度、历史记录回溯、多格式导出。

✨ 核心特性

特性 说明

🧩 DAG 自动规划 LLM 将复杂任务自动分解为有向无环图，节点间支持依赖关系

🔄 流式执行 LangGraph 后台流式推进，前端 500ms 轮询实时更新流程图

🎯 可交互流程图 鼠标悬停/点击节点显示完整信息（详情、前置/后置条件、重试策略）

🎨 状态可视化 5 种节点状态（待处理/进行中/成功/失败/超时）自动着色

💾 MongoDB 持久化 所有任务、计划、执行结果存入 MongoDB，支持历史回溯

📤 多格式导出 支持 PNG / PDF / SVG / JSON / HTML / DOT 六种格式导出

⏹️ 任务控制 支持中途停止、节点级重试

🔧 节点细化 可选的子步骤自动细化，提升执行精度

🏗️ 系统架构


┌─────────────────────────────────────────────────────────────┐
│  前端 (Dash + Cytoscape.js)                                │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ 新建任务 Tab │  │ 历史记录 Tab  │  │ 节点详情面板       │  │
│  │ · 流式进度   │  │ · 任务列表    │  │ · 悬停/点击实时更新│  │
│  │ · 开始/停止  │  │ · 查看/删除   │  │ · 前置/后置条件    │  │
│  └──────┬──────┘  └──────┬───────┘  └───────────────────┘  │
│         │                │                                  │
│    dcc.Interval (500ms)  │                                  │
│         │                │                                  │
├─────────▼────────────────▼──────────────────────────────────┤
│  后端 (Python)                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ StreamManager│  │  LangGraph   │  │  MongoDB         │  │
│  │ 后台线程管理 │──│  Agent 引擎   │──│  任务/计划持久化  │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│         │                  │                                 │
│  ┌──────▼──────────────────▼─────────────────────────────┐ │
│  │  DAG → Cytoscape Adapter（数据格式转换）                │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘


🚀 快速开始

环境要求

• Python >= 3.10

• MongoDB >= 4.4

• 可用的 LLM API（OpenAI 兼容接口）

安装

# 克隆仓库
git clone https://github.com/yourname/task-planner.git
cd task-planner

# 安装依赖（默认包含 Dash UI）
pip install -e .

# 如需旧版 Gradio UI（并存保留）
pip install -e ".[gradio]"

# 开发环境
pip install -e ".[dev,gradio,dashscope]"


配置

创建 .env 文件：
# LLM 配置
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1   # 或兼容接口地址

# MongoDB 配置（默认）
MONGO_HOST=localhost
MONGO_PORT=27017
MONGO_DB=task_planner

# 服务端口
DASH_PORT=7860
DASH_DEBUG=false


启动

# Dash 版（默认，推荐）
task-planner

# 或 Python 直接运行
python -m task_planner.dash_app

# 旧版 Gradio UI
task-planner-gradio


浏览器打开：http://localhost:7860

📖 使用说明

🚀 新建任务

1. 在输入框中描述你的任务需求（如"教我做甜口西红柿炒鸡蛋"）
2. 勾选"节点细化"以启用子步骤自动拆分
3. 点击 🚀 开始规划
4. 流程图实时渲染，节点颜色随执行状态变化
5. 鼠标悬停节点查看详细信息
6. 可随时点击 ⏹️ 停止 终止任务

📜 历史记录

1. 切换到"历史记录" Tab
2. 从下拉列表选择任务（支持多选删除）
3. 流程图自动加载，可交互查看
4. 支持 刷新列表 / 删除选中 / 导出

📤 导出

支持 6 种格式：

格式 说明

PNG 300 DPI 高清位图

PDF 矢量文档

SVG 可缩放矢量图

JSON 原始节点/边数据

HTML 独立交互式 HTML 文件

DOT Graphviz DOT 格式

📁 项目结构


task_planner/
├── __init__.py              # 包入口
├── dash_app.py              # Dash 主应用（推荐 UI）
├── app.py                   # Gradio 旧版 UI（并存保留）
├── cytoscape_adapter.py     # DAG → Cytoscape 数据转换
├── stream_manager.py        # 后台流式任务管理
├── flowchart_pro.py         # 流程图渲染器（pyvis + 导出）
├── config.py                # 全局配置
├── model/
│   ├── agent.py             # LangGraph Agent 核心
│   ├── database.py          # MongoDB 数据层
│   ├── llm.py               # LLM 接口封装
│   └── logger_setup.py      # 日志配置
├── tests/                   # 测试
└── pyproject.toml           # 项目配置


⚙️ 配置项说明

环境变量 默认值 说明

OPENAI_API_KEY - LLM API 密钥

OPENAI_BASE_URL https://api.openai.com/v1 API 地址

MONGO_HOST localhost MongoDB 主机

MONGO_PORT 27017 MongoDB 端口

MONGO_DB task_planner 数据库名

DASH_HOST 0.0.0.0 Dash 监听地址

DASH_PORT 7860 Dash 监听端口

DASH_DEBUG false 调试模式

RENDER_DIR ./renders 导出文件目录

🔧 开发

# 代码格式化
black src/ tests/
isort src/ tests/

# 类型检查
pyright

# 运行测试
pytest

# 覆盖率
pytest --cov=task_planner


📋 依赖说明

核心依赖

包 用途

langgraph>=1.2.11 Agent 工作流引擎

dash>=2.14.0 Web UI 框架

dash-cytoscape>=0.3.0 DAG 流程图渲染

plotly>=5.18.0 图表基础库

mongoengine>=0.27.0 MongoDB ODM

pydantic>=2.0.0 数据校验
可选依赖
组 说明

gradio 旧版 Gradio UI

dashscope 阿里云 DashScope LLM

dev 开发工具链

🐛 常见问题

Q: 流程图不显示？
• 确认 MongoDB 已启动且连接正常

• 检查浏览器 Console 是否有 JS 错误

• 确认 dash-cytoscape 已正确安装

Q: 流式更新延迟？
• 默认 500ms 轮询间隔，可在 dash_app.py 中调整 dcc.Interval 的 interval 参数

Q: 如何切换回 Gradio？
• 安装 pip install -e ".[gradio]"，然后用 task-planner-gradio 启动

Q: 导出 PNG/PDF 失败？
• 确认 cairosvg 已安装：pip install cairosvg

• 系统可能需要 libcairo2：apt-get install libcairo2

📄 许可证

GPL-3.0-or-later

🙏 致谢

• https://github.com/langchain-ai/langgraph — Agent 编排引擎

• https://dash.plotly.com/ — 交互式 Web UI

• https://js.cytoscape.org/ — 网络图可视化

• https://pyvis.readthedocs.io/ — 流程图导出支持
