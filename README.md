# My-AI-Journey

> **我的 AI 学习旅程**——一个持续演进的实验田与孵化器。
> 探索大模型、Agent、RAG、多模态，以及 Vibe-Coding 的一切可能。
>
> 这里**不是**一个包含多个子项目的大仓库。
> 这里是**思考的过程、验证的足迹、学习的见证**。
> 成熟的想法会被拆分到独立仓库专门维护——这里保留孵化与记录的痕迹。

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Docker](https://img.shields.io/badge/Docker-Ready-green.svg)](https://www.docker.com/)
[![Journey](https://img.shields.io/badge/Status-On%20the%20journey-blueviolet.svg)](#)

---

## 项目简介

这是一个**个人 AI 学习仓库**，记录我从入门到大模型应用开发的完整路径。

它同时承担两个角色：

**1. 学习旅程的档案**

这里留下的不只是"成功的代码"，也包括走过的弯路、被放弃的实验、中途思考的碎片。
`abandon/` 与 `logs/` 是有意义的历史——它们记录了"当时的我怎么想、为什么这么做"。
未来的我（或偶遇的你）打开这里，看到的是一条可追溯的思考路径，而不是一堆孤立的结果。

**2. 想法的孵化器**

任何与 AI 相关、与学习相关的探索都可以在这里落地——不限于 Python，不限形式。
当一个实验被验证可行、值得对外承诺（`pip install`、给别人用、加 CI），
它就**拆分到独立仓库**专门维护。

**核心原则：**

- **独立仓库 = 对外承诺**——有 pip 入口 / README / CI / release
- **本仓库 = 学习过程**——没有对外承诺，只有实验与记录
- **绝不演变成"包含多个子项目的大仓"**——一旦出现这种趋势，立刻拆分

这样 `git log` 保持可读，`git blame` 保持准确，学习痕迹保持完整。

---

## 已拆分的独立项目

以下项目已经孵化成熟，拥有各自的仓库与维护节奏：

| 项目 | 独立仓库 | 说明 |
|------|---------|------|
| **Task Planner** | [task-planner](https://github.com/Duckherewegoo/task-planner) | 基于 LangGraph 的智能任务规划引擎（DAG 编排 + 流式执行 + 评估套件） |
| **Nano Harness** | [nano-harness](https://github.com/Duckherewegoo/Nano-Harness) | 功能完整的 AI 系统框架，集成了多智能体协作、MCP 协议、Skill 插件、提示词工程、多模态处理、Bash 执行等核心能力 |
| **Deepdream Agent** | [deepdream-agent](https://github.com/Duckherewegoo/deepdream-agent) | 基于 LangGraph + PyTorch 的工程化重构版本，使用千问大模型驱动的智能梦境生成助手  |
| **Langgraph Writer Multiagent** | [langgraph-writer-multiagent](https://github.com/Duckherewegoo/langgraph-writer-multiagent) | 包含 ReAct 循环、审核机制、人机交互、MCP 协议、CSV 分析、计算器、天气查询的工程化智能体 |
| **Langgraph Multi Agent** | [langgraph-multi-agent](https://github.com/Duckherewegoo/langgraph-multi-agent) | 基于 LangGraph 的智能任务规划引擎（DAG 编排 + 流式执行 + 评估套件） |

> 本仓库对应目录下保留最后版本的快照（`abandon/`），用于追溯历史。
> 具体维护走独立仓库。

---

## 目录结构

    My-AI-Journey/
    ├── .gitignore                  # Git 忽略规则
    ├── LICENSE                     # GPL-3.0
    ├── README.md                   # 本文件
    ├── docs/                       # 学习笔记 / 架构思考 / 实验记录
    ├── logs/                       # 运行日志 / 调试痕迹（保留，供回溯）
    ├── outputs/                    # 各类实验输出（图像 / 报告 / 数据）
    ├── py_lab/                     # 🧪 Python 实验场（孵化中）
    │   ├── <实验主题>/
    │   └── *.py                    # 快速实验脚本
    ├── abandon/                    # 🗄️ 已停止维护的项目快照
    │   ├── new_task_planner/       # 已拆分为独立仓库 task-planner
    │   ├── doubao-yuanbao/         # 豆包/元宝实验
    │   ├── qwen-yuanbao/           # 千问/元宝实验
    │   └── ...
    ├── web_ref/                    # 网页参考素材
    └── ...                         # 未来其他方向（不限于 Python）

---

## 仓库定位的三个细节

### 1. `py_lab/` —— 实验发生地

所有**正在孵化**的 Python 实验都在这里。没有预设立场，没有维护承诺。

- 可以随时新建、随时删除、随时重写
- 不需要 pyproject.toml、不需要 README、不需要测试
- 一个脚本跑通一次就算成功
- 一旦某实验稳定到"想给别人用" → 拆分为独立仓库

### 2. `abandon/` —— 不是"失败"，是"历史"

这里的项目**不在此仓库维护**。原因可能各不相同：

- 已升级为独立仓库（如 `new_task_planner` → `task-planner`）
- 实验结论已明确，不再继续
- 思路被其他实验吸收，独立形态已无必要

保留它们的目的：

- **历史可追溯**——回答"当时是怎么做的"
- **可对照**——新实验与旧实验对比，看进步在哪里
- **不重复踩坑**——避免"这个我之前试过吗"的疑问

### 3. `logs/` & `outputs/` —— 过程的痕迹

运行日志、实验产物、中间结果——**不删**。

它们不是"垃圾"，是**证据**：证明某次实验真的发生过、某次错误真的出现过、
某个想法当时是怎么演化的。定期整理归档，但不清理。

---

## 未来方向

**不限定 Python**。只要与 AI 相关、与学习相关，任何形式都可以：

- Prompt 工程实验
- Agent / RAG / 多模态方向的探索
- 论文复现
- 前端可视化实验（任何语言）
- 硬件 / 边缘 AI 尝试
- Vibe-Coding 的产品原型

**判断标准只有一条**：这是否属于"我的学习旅程"？

---

## 已归档项目索引

（本节列出 `abandon/` 下的项目，方便检索——细节见各自目录的 README）

### DeepSeek-Qwen 任务规划器 → [独立仓库](https://github.com/Duckherewegoo/task-planner)

**目录**：`abandon/new_task_planner/`
**说明**：基于 LangGraph 的智能任务规划引擎。已孵化成熟，拆分为独立仓库 `task-planner`。
**独立维护**：Issue / PR / Release 请走 [task-planner](https://github.com/Duckherewegoo/task-planner)。

### 豆包 / 元宝大模型实验

**目录**：`abandon/doubao-yuanbao/`
**包含**：
- DeepDream 图像生成 Agent（LLM 驱动绘画，多风格）
- LangGraph Agent 演示（含 MCP 工具集成）
- 多 Agent 协作系统（Researcher / Writer / Reviewer / Editor）
- Nano Harness（轻量 Agent 评估框架）
**说明** : 以上均分离作为独立项目进行进一步开发

### 千问 / 元宝大模型实验

**目录**：`abandon/qwen-yuanbao/`
**包含**：Docker 化任务规划器、早期 broken 版本（保留迭代痕迹）

### RAG 与向量检索实验

**目录**：`abandon/qwen/`、`abandon/rag_comparison_*.json`
**包含**：不同向量检索策略对比（HNSW / FAISS / 混合）、RAG 效果评估、中文检索优化

### 毕设
**目录** : `abandon/doubao/ct-sr`
**包含** : 根据本人毕设论文还原的代码（源代码因为sed失误导致数字和模型函数全部丢失,使用豆包从论文超参数和相关模型描述，基于残缺代码还原而成）, 目前还不能正常使用

### 独立脚本与工具

**目录**：`abandon/*.py`

| 脚本 | 功能 |
|------|------|
| `abird.py` / `bbird.py` | 鸟类数据实验 |
| `bilibili_agent.py` | B站相关 Agent |
| `catrag.py` / `doggrag.py` | 图像 RAG 实验 |
| `cuda-topk.py` | CUDA 加速 TopK 检索 |
| `hnsw-faiss.py` | HNSW + FAISS 向量检索 |
| `langchainasyncio.py` | LangChain AsyncIO |
| `linux_agent.py` | Linux 操作 Agent |
| `memorysaver.py` | 内存优化 |
| `qwen_rag_final.py` | Qwen RAG 最终版 |
| `doubantop250.py` | 豆瓣 Top250 抓取 |
| `extract_tags.py` | 文本标签提取 |
| `fonts_viewer.py` | 字体预览 |

（其余见 `abandon/` 目录）

---

## 技术栈（学习过程中接触过的）

| 类别 | 技术 |
|------|------|
| **大模型** | DeepSeek、通义千问（Qwen）、豆包、元宝 |
| **Agent 框架** | LangGraph、LangChain |
| **向量数据库** | ChromaDB、FAISS、HNSW |
| **Web 框架** | Dash、FastAPI |
| **容器化** | Docker、docker-compose |
| **评估测试** | pytest、自研 Eval Suite |
| **可视化** | Cytoscape.js、PyVis、Vis.js |
| **协议** | MCP（Model Context Protocol） |

（不构成"本项目使用这些技术"的声明——只是学习足迹的索引）

---

## 使用说明

### 环境要求

- Python >= 3.10
- Docker >= 20.10（可选）

### 使用本仓库中的实验代码

`py_lab/` 下的实验**通常不需要安装**——直接 `python <脚本>.py` 即可。

如某个实验需要额外依赖，其目录下会有 `requirements.txt` 或 `README.md`。

### 使用已拆分的独立项目

请访问对应独立仓库，那里有完整的安装与使用说明。

### 环境变量

各实验按需自带 `.env.example`。**密钥不入库**——`.gitignore` 已排除 `.env*`（保留 `.env.example`）。

---

## 关于"学习旅程"这个词

用这个词，不是哈气。

**大多数人的 GitHub 是"作品集"**——只展示成功、只保留最漂亮的版本、删除失败痕迹。
这没错，但那种仓库回答不了"我当时为什么这么选"。

**这个仓库想做的是"日志"**——包括失败、犹豫、半成品、返工。
它对未来的人（尤其是我自己）的价值，不在于"能跑"，而在于"能理解"。

所以：

- **不删 `abandon/`**——那些是历史的层次
- **不删 `logs/`**——那些是过程的证据
- **不怕乱**——只要可追溯
- **不追求"干净漂亮"**——追求"真实完整"

(代码部分含vibe-coding和aigc成分，所有项目和文件仅供自己学习和参考，不承诺能跑通)

---

## 开源协议

本项目采用 GPL-3.0 开源协议。

---

## 联系方式

- GitHub: [Duckherewegoo](https://github.com/Duckherewegoo)
- Email: dakeginger@qq.com

---

> "The journey is the reward."
> — 每一个 `git commit`，都是旅程本身。
