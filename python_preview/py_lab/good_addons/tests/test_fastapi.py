"""good_addons v7.0 端到端功能验证（真实框架测试客户端）。"""

from pathlib import Path as _P
import sys as _s
_s.path.insert(0, str(_P(__file__).resolve().parent.parent.parent))

import warnings
warnings.filterwarnings("ignore")

import good_addons
from good_addons import boost, Security
from good_addons.core import EVENTS, METRICS, HEALTH


results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(f"  {'✅' if cond else '❌'} {name}")
def finish():
    passed = sum(1 for _, c in results if c)
    failed = [n for n, c in results if not c]
    print(f"--> {passed}/{len(results)} 通过" + (f" | 失败: {failed}" if failed else ""))
    import sys; sys.exit(1 if failed else 0)
from good_addons import boost, Security
from good_addons.core import METRICS, HEALTH
print("\n[2] FastAPI 增强")
from fastapi import FastAPI, HTTPException
fapp = FastAPI()

@fapp.get("/ping")
async def ping():
    return {"pong": True}

@fapp.get("/err")
async def err():
    raise RuntimeError("async boom")

@fapp.get("/http-err")
async def http_err():
    raise HTTPException(status_code=418, detail="teapot")

boost(fapp, backend="fastapi", log_level="WARNING", graceful_shutdown=False)
from starlette.testclient import TestClient
fc = TestClient(fapp, raise_server_exceptions=False)

r = fc.get("/ping")
check("fastapi 200", r.status_code == 200)
check("fastapi 安全头", r.headers.get("X-Frame-Options") == "DENY")
check("fastapi X-Request-ID", bool(r.headers.get("X-Request-ID")))

r = fc.get("/err")
check("fastapi 异常 500", r.status_code == 500)
check("fastapi 错误体 fingerprint", "fingerprint" in r.json()["error"])

r = fc.get("/http-err")
check("HTTPException 保留 418", r.status_code == 418)
check("HTTPException 消息透传", r.json()["error"]["message"] == "teapot")


finish()
