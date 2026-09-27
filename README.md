# My-AI-Journey

> 我的 AI 学习之旅 — 探索大模型、Agent、RAG 与多模态应用的实验田(含Vibe-Coding)

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Docker](https://img.shields.io/badge/Docker-Ready-green.svg)](https://www.docker.com/)

---

## 项目简介

这是一个个人 AI 学习项目，记录了我从入门到大模型应用开发的完整学习路径。项目涵盖了 **LLM 应用开发、Agent 架构设计、RAG 检索增强生成、向量数据库、多模态处理** 等多个方向的技术实践与实验。

项目以 python_preview/ 为核心代码目录，按技术方向和实验主题组织为多个子项目，每个子项目相对独立，可单独运行和实验。

---

## 目录结构

    My-AI-Journey/
    ├── .gitignore                  # Git 忽略规则
    ├── LICENSE                     # GPL-3.0 开源协议
    ├── README.md                   # 项目说明（本文件）
    ├── python_preview/             # 核心代码目录
    │   ├── deepseek-qwen/          # DeepSeek + Qwen 任务规划器
    │   ├── doubao-yuanbao/         # 豆包/元宝大模型实验
    │   ├── qwen-yuanbao/           # 千问/元宝大模型实验
    │   ├── qwen/                   # Qwen RAG 相关实验
    │   └── *.py                    # 各类独立脚本与实验代码
    ├── docs/                       # 项目文档（进行中）
    └── web_ref/                    # 网页参考素材

---

## 子项目说明

### 1. DeepSeek-Qwen 任务规划器

路径：python_preview/deepseek-qwen/new_task_planner/

基于 LangGraph 构建的智能任务规划系统，使用 DeepSeek/Qwen 大模型作为核心推理引擎。

**核心特性：**

- 基于有向无环图（DAG）的任务工作流编排
- 支持流式响应与实时进度展示
- 内置评估测试套件（Eval Suite）
- Docker 容器化部署，一键启动
- Cytoscape / PyVis 可视化工作流图

**技术栈：** Python、LangGraph、Dash、Docker、SQLite

**快速开始：**

    cd python_preview/deepseek-qwen/new_task_planner
    pip install -e .
    # 或直接用 Docker
    docker-compose up

---

### 2. 豆包/元宝大模型实验

路径：python_preview/doubao-yuanbao/

围绕字节跳动豆包/腾讯元宝等大模型的能力探索与工具开发。

#### 2.1 DeepDream 图像生成 Agent

路径：python_preview/doubao-yuanbao/deepdream/

基于 LLM 驱动的 AI 绘画工具，支持多种艺术风格（Normal / Crazy / Nightmare / Sweet / Mist 等），通过 Agent 节点自动理解用户意图并生成图像。

**架构：** Intent Node -> LLM Node -> Tool Node -> Dream Gen Node -> Output Node

#### 2.2 LangGraph Agent 演示

路径：python_preview/doubao-yuanbao/langgraph-agent-demo/

LangGraph 框架的 Agent 开发模板，包含 MCP（Model Context Protocol）工具集成、多轮对话管理、内容审核等实用功能。

#### 2.3 多 Agent 协作系统

路径：python_preview/doubao-yuanbao/langgraph-multi-agent/

基于 LangGraph 的多 Agent 协作框架，包含 Researcher（研究）、Writer（写作）、Reviewer（审核）、Editor（编辑）四个角色 Agent，实现自动化内容生产流水线。

#### 2.4 Nano Harness - Agent 评估框架

路径：python_preview/doubao-yuanbao/nano-harness/

轻量级 AI Agent 评估与测试框架，支持多模态输入（文本/图像/音频/视频）、技能注册、MCP 工具调用、Web UI 可视化等能力。

---

### 3. 千问/元宝大模型实验

路径：python_preview/qwen-yuanbao/

围绕通义千问等大模型的应用实验，重点探索任务规划器的工程化落地。

#### Docker 化任务规划器

路径：python_preview/qwen-yuanbao/docker/

将任务规划器容器化部署的完整方案，包含：

- Dockerfile + docker-compose 编排
- Dash Web UI 可视化界面
- 任务流程图导出（SVG）
- 完整的测试评估体系

#### 历史实验项目

路径：python_preview/qwen-yuanbao/broken_task-planner-project/

任务规划器的早期实验版本（标记为 broken，记录迭代过程），包含完整的 CI/CD 配置和测试框架。

---

### 4. RAG 与向量检索实验

路径：python_preview/qwen/、python_preview/rag_comparison_*.json

RAG（检索增强生成）相关实验代码与结果数据，涵盖：

- 不同向量检索策略对比（HNSW / FAISS / HNSW-FAISS 混合）
- RAG 效果评估与可视化
- 中文检索优化实验

---

### 5. 独立脚本与工具

python_preview/ 根目录下还包含一系列独立脚本，用于快速实验和工具开发：

| 脚本文件 | 功能说明 |
|---------|---------|
| abird.py / bbird.py | 鸟类数据相关实验 |
| bilibili_agent.py | B站相关 Agent 实验 |
| catrag.py | 猫图 RAG 实验 |
| cuda-topk.py | CUDA 加速 TopK 检索 |
| doggrag.py | 狗狗图片 RAG 实验 |
| doubantop250.py | 豆瓣 Top250 数据抓取 |
| extract_tags.py | 文本标签提取工具 |
| fonts_viewer.py | 字体预览工具 |
| hnsw-faiss.py | HNSW + FAISS 向量检索 |
| langchainasyncio.py | LangChain AsyncIO 实验 |
| linux_agent.py | Linux 操作 Agent |
| lsapp.py | 应用列表工具 |
| memorysaver.py | 内存优化工具 |
| qwen_rag_final.py | Qwen RAG 最终版 |
| train_text.txt | 训练文本数据 |

---

## 技术栈总览

| 类别 | 技术选型 |
|------|---------|
| **大模型** | DeepSeek、通义千问（Qwen）、豆包、元宝 |
| **Agent 框架** | LangGraph、LangChain |
| **向量数据库** | ChromaDB、FAISS、HNSW |
| **Web 框架** | Dash、FastAPI |
| **容器化** | Docker、docker-compose |
| **评估测试** | 自研 Eval Suite、pytest |
| **可视化** | Cytoscape.js、PyVis、Vis.js Network |
| **协议** | MCP（Model Context Protocol） |

---

## 使用说明

### 环境要求

- Python >= 3.10
- Docker >= 20.10（可选，用于容器化部署）

### 安装依赖

各子项目通常包含独立的 requirements.txt 或 pyproject.toml，建议在子项目目录下单独安装依赖：

    # 以 deepseek-qwen 任务规划器为例
    cd python_preview/deepseek-qwen/new_task_planner
    pip install -e .

    # 或以 langgraph-agent-demo 为例
    cd python_preview/doubao-yuanbao/langgraph-agent-demo
    pip install -r requirements.txt

### 环境变量配置

部分项目需要配置 .env 文件，可参考项目中的 .env.example 模板：

    cp .env.example .env
    # 编辑 .env 填入你的 API Key

---

## 开源协议

本项目采用 GPL-3.0 开源协议。

---

## 联系方式

- GitHub: [Duckherewegoo](https://github.com/Duckherewegoo)
- Email: dakeginger@qq.com
