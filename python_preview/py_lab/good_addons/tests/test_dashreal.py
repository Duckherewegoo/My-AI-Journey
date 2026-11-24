"""真实 Dash 应用端到端验证：装配后首页、安全头、同步/异步回调、JSON 日志。"""


from pathlib import Path as _P
import sys as _s
_s.path.insert(0, str(_P(__file__).resolve().parent.parent.parent))

import warnings, asyncio; warnings.filterwarnings('ignore')
from good_addons.tests.test_common import *  # noqa: F403
from dash import Dash, html, Input, Output, callback
import os
os.environ['GOOD_ADDONS_LOG_JSON']='true'   # 同时验证 JSON 日志
app = Dash(__name__)
app.layout = html.Div([html.Div("hi", id="o")])
@callback(Output("o","children"), Input("o","id"))
def cb(v):
    if v == "bad": raise ValueError("cb boom")
    return v
async def acb(v): return v
app.callback(Output("o","title"), Input("o","id"))(acb)
rep = boost(app, log_level="INFO", graceful_shutdown=False, memory_watchdog=False)
print("[8] 真实 Dash", dash.__version__)
check("识别为 Dash", rep.get("app_kind_report",{}).get("app_kind")=="dash")
check("兜底 backend=flask", any(b["name"]=="flask" for b in rep["backends"]))
check("回调包装=2", rep["app_kind_report"].get("callbacks_wrapped")==2)
check("Dash 默认 CSP 兼容", "unsafe-eval" in rep.get("csp",""))
c = app.server.test_client()
r = c.get("/")
check("Dash 首页 200", r.status_code==200)
check("Dash 安全头", r.headers.get("Content-Security-Policy") and r.headers.get("X-Request-ID"))
try:
    cb("bad"); check("同步回调重抛", False)
except ValueError: check("同步回调重抛", True)
check("异步回调仍为协程", asyncio.iscoroutine(acb(1)) and asyncio.run(acb(3))==3)
check("JSON 日志生效", logging.getLogger("good_addons")._log_json_format is True)
finish()
