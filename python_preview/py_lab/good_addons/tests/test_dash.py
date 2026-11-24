"""good_addons v7.0 端到端功能验证（真实框架测试客户端）。"""

from pathlib import Path as _P
import sys as _s
_s.path.insert(0, str(_P(__file__).resolve().parent.parent.parent))

import flask
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
print("\n[4] Dash 应用层钩子")
class FakeDash:  # 模拟 Dash，避免装 dash 依赖
    def __init__(self):
        self.server = flask.Flask(__name__)
        self.callback_map = {
            "out1": {"callback": self._sync_cb},
            "out2": {"callback": self._async_cb},
        }
        self.layout = None
    def _sync_cb(self, x):
        if x == "bad":
            raise ValueError("sync cb fail")
        return x
    async def _async_cb(self, x):
        if x == "bad":
            raise RuntimeError("async cb fail")
        return x

import good_addons.good as G
dapp = FakeDash()
check("is_dash_app 识别", G.is_dash_app(dapp))
rep = boost(dapp, log_level="WARNING", graceful_shutdown=False)  # 不指定 backend，应兜底 flask
check("Dash 自动兜底 backend=flask", any(b["name"]=="flask" for b in rep["backends"]))
check("app_kind=dash 报告", rep.get("app_kind_report", {}).get("app_kind") == "dash")
check("回调包装数=2", rep["app_kind_report"].get("callbacks_wrapped") == 2)

# 包过的同步回调仍抛异常（不吞），但会记录
wrapped_sync = dapp.callback_map["out1"]["callback"]
import asyncio
try:
    wrapped_sync("bad")
    check("同步回调异常重抛", False)
except ValueError:
    check("同步回调异常重抛", True)
check("同步回调正常路径", wrapped_sync("ok") == "ok")

wrapped_async = dapp.callback_map["out2"]["callback"]
try:
    asyncio.run(wrapped_async("bad"))
    check("异步回调异常重抛", False)
except RuntimeError:
    check("异步回调异常重抛", True)
check("异步回调正常路径", asyncio.run(wrapped_async("ok")) == "ok")


finish()
