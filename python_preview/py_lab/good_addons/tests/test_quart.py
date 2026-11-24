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
print("\n[3] Quart 增强")
from quart import Quart
qapp = Quart(__name__)

@qapp.get("/hello")
async def hello():
    return {"hi": "quart"}

@qapp.get("/qboom")
async def qboom():
    raise KeyError("nope")

boost(qapp, backend="quart", log_level="WARNING", graceful_shutdown=False)
qc = qapp.test_client()
_aw = lambda v: __import__('asyncio').run(v) if __import__('inspect').iscoroutine(v) else v

r = _aw(qc.get("/hello"))
check("quart 200", r.status_code == 200)
check("quart 安全头", "Content-Security-Policy" in r.headers)
r = _aw(qc.get("/qboom"))
check("quart 异常 500", r.status_code == 500)
check("quart 错误体", "fingerprint" in _aw(r.get_json())["error"])


finish()
