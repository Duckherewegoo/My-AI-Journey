# LangGraph 全特性智能体 Demo

包含 ReAct 循环、审核机制、人机交互、MCP 协议、CSV 分析、计算器、天气查询的工程化智能体。

## 覆盖特性
- ✅ 自定义 State + `add_messages` 消息归约 + 上下文自动截断记忆
- ✅ 完整 ReAct 推理循环 + 最大步数防死循环机制
- ✅ 输入内容审核节点，可扩展敏感校验规则
- ✅ 人机交互（Human-in-the-Loop）：基于 LangGraph 原生 `Interrupt` 中断机制
- ✅ 4类工具体系：安全计算器、CSV数据分析、天气查询、MCP协议工具
- ✅ 模拟 MCP 服务 + MCP 客户端，1:1 复现真实 MCP 调用流程
- ✅ 写作+分析双输出节点，适配文案生成、数据分析报告场景
- ✅ 配置与代码分离，兼容硅基流动等免费 OpenAI 兼容接口

## 快速启动
1. 复制 `.env.example` 为 `.env`，填入你的 API 密钥
2. 安装依赖：`pip install -e .`
3. 运行示例：`python src/main.py`
