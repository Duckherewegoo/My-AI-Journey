# 多智能体协作写作系统

基于 LangGraph + LangChain + Gradio 构建的多智能体协作写作平台。

## 功能特点

- 🤖 **四个智能体协作**：研究专家、写作专家、审核专家、总编辑
- 🔄 **自动迭代优化**：审核不通过自动返回修改，最多迭代指定次数
- 🎨 **美观的Web界面**：基于Gradio构建，操作简单直观
- ⚙️ **灵活配置**：支持自定义模型、温度、迭代次数等参数
- 📝 **完整的工作流**：从资料收集到最终润色，全流程自动化

## 系统架构

```
用户输入主题
    ↓
[研究专家] 收集信息、整理研究笔记
    ↓
[写作专家] 根据研究素材撰写文章草稿
    ↓
[审核专家] 多维度审核，提供修改建议
    ↓
    ├─ 需要修改？ → 返回写作专家（最多N次迭代）
    └─ 审核通过 →
              ↓
        [总编辑] 最终润色和优化
              ↓
        输出最终文章
```

## 安装

### 1. 创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows
```

### 2. 安装依赖

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env` 并填写你的配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```
OPENAI_API_KEY=你的OpenAI API密钥
OPENAI_BASE_URL=https://api.openai.com/v1  # 可选，自定义API地址
MODEL_NAME=gpt-3.5-turbo
TEMPERATURE=0.7
MAX_ITERATIONS=3
```

## 使用

### 启动Web界面

```bash
python main.py
```

然后在浏览器中打开 `http://localhost:7860`

### 使用说明

1. 在左侧输入写作主题
2. （可选）在高级设置中调整参数
3. 点击「开始写作」按钮
4. 等待系统完成写作流程
5. 在右侧查看最终文章、研究笔记和审核反馈

## 项目结构

```
langgraph-multi-agent/
├── agents/                 # 智能体模块
│   ├── __init__.py
│   ├── base_agent.py       # 基础智能体类
│   ├── researcher.py       # 研究智能体
│   ├── writer.py           # 写作智能体
│   ├── reviewer.py         # 审核智能体
│   └── editor.py           # 编辑智能体
├── graph/                  # 工作流模块
│   ├── __init__.py
│   └── workflow.py         # LangGraph工作流定义
├── utils/                  # 工具函数模块
│   ├── __init__.py
│   └── helpers.py          # 辅助函数
├── outputs/                # 输出目录（自动创建）
├── main.py                 # 主程序入口
├── requirements.txt        # 依赖列表
├── .env.example            # 环境变量示例
└── README.md               # 项目说明
```

## 技术栈

- **LangGraph**：多智能体工作流编排
- **LangChain**：大语言模型应用框架
- **Gradio**：Web界面框架
- **Pydantic**：数据验证
- **Python 3.10+**

## 智能体说明

### 研究专家（ResearchAgent）
- 负责收集主题相关的信息和素材
- 输出结构化的研究笔记
- 确保信息的全面性和准确性

### 写作专家（WriterAgent）
- 根据研究素材撰写文章草稿
- 确保文章结构清晰、内容充实
- 支持根据审核反馈进行修改

### 审核专家（ReviewerAgent）
- 从多个维度审核文章质量
- 提供具体的修改建议
- 判断是否需要继续修改

### 总编辑（EditorAgent）
- 对文章进行最终润色和优化
- 优化标题、语言、结构等
- 确保文章达到出版级别

## 许可证

MIT License
