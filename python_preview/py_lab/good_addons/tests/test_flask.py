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
print("\n[1] Flask")
from flask import Flask
app = Flask(__name__)

@app.get("/ok")
def ok():
    return {"hello": "world"}

@app.get("/boom")
def boom():
    raise ValueError("kaboom")

@app.get("/trace")
def trace_ep():
    from good_addons.core import RequestContext
    return {"tid": RequestContext.trace_id()}

rep = boost(app, backend="flask", log_level="WARNING", memory_watchdog=False, graceful_shutdown=False)
check("flask 报告含 backend", any(b["name"] == "flask" for b in rep["backends"]))
client = app.test_client()

r = client.get("/ok")
check("200 正常", r.status_code == 200)
check("安全头 X-Content-Type-Options", r.headers.get("X-Content-Type-Options") == "nosniff")
check("安全头 CSP 存在", "Content-Security-Policy" in r.headers)
check("回显 X-Request-ID", bool(r.headers.get("X-Request-ID")))
check("回显 X-Response-Time", r.headers.get("X-Response-Time", "").endswith("ms"))
check("机器可读 X-Response-Time-Ms", r.headers.get("X-Response-Time-Ms", "").replace(".","").isdigit())

r = client.get("/boom")
check("异常端点返回 500", r.status_code == 500)
body = r.get_json()
check("错误体含 fingerprint", body and "fingerprint" in body["error"])
check("错误体含 request_id", body and "request_id" in body["error"])
check("500 不泄漏内部消息", body["error"]["message"] == "Internal Server Error")

r = client.get("/trace", headers={"X-Trace-ID": "abc123"})
check("入站 trace_id 透传", r.get_json()["tid"] == "abc123")
r = client.get("/trace")
check("自动生成 trace_id", len(r.get_json()["tid"]) == 16)

check("metrics 计数", METRICS.snapshot().get("flask.requests", 0) >= 4)


finish()
