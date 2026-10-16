# AI 任务规划看板 v3.0

## 功能清单
- 🤖 LLM 任务拆解 (Qwen / Mock 双模式)
- 🎨 Vis.js 交互式流程图 (节点颜色 = 状态)
- 🔄 节点状态管理 (单击循环切换, 双击直接完成)
- 📋 历史任务列表 (MongoDB 持久化)
- 📸 PNG 导出 (matplotlib 服务端生成, 状态着色)
- 🌙 暗色模式 (Gradio 6.x 原生主题切换)
- 🛡️ 提示词注入防御 + 输入清洗
- 📊 完整链路日志 (请求ID追踪 / 耗时 / 分级落盘 / 7天轮转)
- 🔌 节点状态 API (FastAPI 路由, 供前端 JS fetch 调用)

## 环境变量
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEBUG` | true | true=控制台DEBUG, false=仅WARNING+ |
| `USE_MOCK_LLM` | false | true=使用Mock数据,无需API Key |
| `DASHSCOPE_API_KEY` | (空) | 阿里云百炼 API Key |
| `DASHSCOPE_MODEL` | qwen-turbo | 模型名称 |
| `LLM_MAX_RETRIES` | 3 | 最大重试次数 |
| `LLM_TIMEOUT` | 30 | 单次调用超时(秒) |
| `PORT` | 7860 | 服务端口 |
| `ENABLE_MCP` | false | 是否开启 MCP Server |

## 启动方式
```bash
# Mock 模式 (无需 API Key)
export USE_MOCK_LLM=true
python app_final.py

# 真实 Qwen 模式
export DASHSCOPE_API_KEY=your_key_here
export USE_MOCK_LLM=false
python app_final.py

# Docker
docker compose up --build
```

## API 路由
- `POST /api/node-status` — 节点状态更新
  - Body: `{"task_id": "task_xxx", "node_id": 1, "action": "set"|"cycle", "status": 0|1|2}`
- `GET /api/health` — 健康检查

## 架构设计
```
前端 Vis.js ←→ fetch API → FastAPI 路由 → Python 业务逻辑 → MongoDB
                  ↓
            Gradio 事件链 (生成/加载/导出)
                  ↓
            LLM Harness (Mock/Qwen 双模式 + 重试)
```

## 日志说明
- 控制台: DEBUG 模式=全部, 生产模式=仅 WARNING+
- 文件: `logs/task_planner.log` 始终 DEBUG 级别
- 轮转: 按天切割, 保留 7 天
- 请求追踪: 每个请求分配短 UUID, 全链路打在日志里
