# 🤖 Task Planner — 通用任务规划助手

基于 **Qwen3.7** 大模型的智能任务规划系统，将任意复杂任务自动分解为**有向无环图（DAG）**，可视化渲染为交互式流程图。

## ✨ 功能特性

- 🧠 **意图识别** — 自动判断任务是否需要多步规划
- 📊 **DAG 规划** — 生成有依赖关系的任务节点图
- 🔧 **节点细化** — 每个步骤补充具体操作细节、前置条件、重试策略
- 🎨 **交互式渲染** — pyvis + vis-network，支持点击/悬停/缩放
- 📤 **多格式导出** — SVG / PNG / PDF / DOT / HTML / JSON
- 📈 **Agent 评估 Harness** — 自动化能力评估 + 报告生成
- 🐳 **Docker 一键部署** — 含 MongoDB + 健康检查

## 📁 项目结构

```
task-planner/
├── pyproject.toml          # ✅ 统一项目配置（依赖/工具/入口）
├── requirements.txt         # 运行时依赖（兼容旧部署）
├── requirements-dev.txt    # 开发/测试依赖
├── Dockerfile              # 生产镜像
├── docker-compose.yml      # 一键启动（App + MongoDB）
├── Makefile                # 常用命令快捷方式
├── .env.example           # 环境变量模板
├── .dockerignore
├── .github/
│   └── workflows/
│       └── ci.yml         # GitHub Actions CI
├── task_planner/           # 主包
│   ├── __init__.py
│   ├── config.py          # 全局配置
│   ├── logger_setup.py    # 日志系统
│   ├── llm_client.py      # LLM 调用封装
│   ├── agent.py           # Agent 主逻辑
│   ├── database.py        # MongoDB 操作
│   ├── flowchart_pro.py   # 流程图渲染
│   └── app.py            # Gradio UI
└── tests/                 # 测试 + 评估
    ├── __init__.py
    ├── conftest.py
    ├── run_eval.py         # 评估入口
    ├── test_agent_harness.py
    ├── harness/
    │   ├── __init__.py
    │   ├── agent_harness.py   # 核心 Harness
    │   ├── evaluators.py      # 评分函数
    │   └── reporters.py       # 报告生成
    └── output/                # 报告输出（自动生成）
```

## 🚀 快速开始

### 方式 1：Docker（推荐生产环境）

```bash
# 1. 准备环境变量
cp .env.example .env
vim .env  # 填入 DASHSCOPE_API_KEY

# 2. 一键启动
make docker-up
# 或
docker compose --env-file .env up -d --build

# 3. 查看日志
make docker-logs
```

访问 `http://localhost:7860`

### 方式 2：本地开发

```bash
# 1. 创建虚拟环境
python3.11 -m venv .venv
source .venv/bin/activate

# 2. 安装（含开发依赖）
make install-dev
# 或
pip install -e ".[dev]"

# 3. 配置环境变量
export DASHSCOPE_API_KEY=你的key
export USE_MOCK_LLM=false

# 4. 启动 MongoDB（需要 Docker）
docker run -d --name mongodb -p 27017:27017 mongo:7.0

# 5. 启动应用
python -m task_planner.app
```

## 🧪 测试与评估

```bash
# 代码检查
make lint

# 格式化
make format

# 单元测试（Mock 模式，秒级完成）
make test

# 集成测试（真实 LLM，需要 API Key）
make test-real

# Agent 能力评估（8 个用例 + 报告）
make eval

# 测试覆盖率
make cov
```

## 📊 Agent 评估 Harness

`tests/harness/` 提供完整的评估框架：

| 维度 | 评估内容 |
|------|-----------|
| `intent` | 意图识别准确率（needs_planning / category） |
| `planning` | 规划合理性（成功标志/节点数/耗时） |
| `e2e` | 端到端成功率 + 耗时分桶 |

运行后自动生成：
- `tests/output/eval_report.md` — 人读报告
- `tests/output/eval_report.json` — 机器读数据
- `tests/output/raw_results.json` — 原始运行数据

## ⚙️ 配置说明

所有配置通过环境变量注入，模板见 `.env.example`：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DASHSCOPE_API_KEY` | 阿里云百炼 API Key | （必填） |
| `DASHSCOPE_BASE_URL` | MaaS 自定义地址 | （可选） |
| `LLM_INTENT_MODEL` | 意图识别模型 | qwen3.7-flash-2026-07-15 |
| `LLM_PLANNER_MODEL` | 规划模型 | qwen3.7-flash-2026-07-15 |
| `LLM_NODE_MODEL` | 节点细化模型 | qwen3.7-flash-2026-07-15 |
| `USE_MOCK_LLM` | 是否使用 Mock | false |
| `MONGO_HOST` | MongoDB 地址 | task_mongodb |
| `DEBUG` | 调试模式 | true |

## 🔧 开发工作流

```bash
# 修改代码后
make format      # 格式化
make lint        # 检查
make test        # 跑测试
make eval        # 跑评估
make docker-up   # 构建并启动
```

## 📄 License

MIT
