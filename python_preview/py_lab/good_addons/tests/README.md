# good_addons v7.0 端到端测试

运行：`python run_tests.py`（在仓库根目录，Python 3.11+）

| 文件 | 覆盖 |
|---|---|
| test_flask.py | Flask 后端：安全头、请求上下文、异常指纹、访问日志 |
| test_fastapi.py | FastAPI 后端：中间件、HTTPException、校验异常 |
| test_quart.py | Quart 后端（async test client） |
| test_dash.py | 用伪 Dash 对象验证 app_kind 钩子（回调包装、CSP 例外） |
| test_dashreal.py | 真实 Dash 4.5 + Flask：回调重抛、async 回调、JSON 日志 |
| test_common.py | core 通用能力：脱敏、指纹、健康检查、diag、registry、__all__ |
| test_decorators.py | @timed/@fallback/@retry/@circuit_breaker/@rate_limited/@cached/@trace |
| test_server.py | 真实服务器子进程冒烟：`python tests/test_server.py <port> <uvicorn|hypercorn|flask>`，验证 200、trace 透传、安全头齐全 |
