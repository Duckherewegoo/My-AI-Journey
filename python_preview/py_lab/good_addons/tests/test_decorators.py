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

print("[6] 装饰器")
from good_addons import trace, timed, fallback, retry, cached, CircuitBreaker, CircuitOpenError
@cached(ttl=10)
def add(a, b):
    add.calls += 1; return a + b
add.calls = 0
add(1,2); add(1,2); add(1,2)
check("cached 命中", add.calls == 1 and add(1,2) == 3)
@fallback(value="safe")
def fail(): raise Exception("x")
check("fallback 降级", fail() == "safe")
@retry(max_attempts=3, base_delay=0.01)
def retry_me():
    retry_me.n += 1
    if retry_me.n < 3: raise ValueError()
    return "ok"
retry_me.n = 0
check("retry 最终成功", retry_me() == "ok" and retry_me.n == 3)
cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
@cb
def flaky(): raise RuntimeError()
for _ in range(2):
    try: flaky()
    except RuntimeError: pass
check("熔断器 OPEN", cb.state.value == "open")
try:
    flaky(); check("熔断快速失败", False)
except CircuitOpenError: check("熔断快速失败", True)
import time as _t; _t.sleep(0.15)
check("熔断半开恢复", cb.state.value == "half_open")
@timed
def quick(): return 1
check("timed 可用", quick() == 1)
import asyncio
@trace
async def atraced(x): return x * 2
check("trace 异步", asyncio.run(atraced(3)) == 6)
from good_addons.core import rate_limited, RateLimitError
@rate_limited(rate=100, capacity=1)
def limited(): return 1
limited()
try:
    limited(); check("限流触发", False)
except RateLimitError: check("限流触发", True)
finish()
