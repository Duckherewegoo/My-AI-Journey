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

from good_addons.core import ExceptionFingerprinter
print("[5] 通用组件")
check("CSP_DASH_COMPAT 含 unsafe-eval", "unsafe-eval" in Security.CSP_DASH_COMPAT)
check("CSP_STRICT", Security.CSP_STRICT == "default-src 'self'")
h = Security.hash_password("secret123")
check("口令校验", Security.verify_password("secret123", h) and not Security.verify_password("x", h))
check("SQL 注入探测", Security.detect_sql_injection("1 UNION SELECT * FROM users"))
check("HTML 转义", Security.sanitize_html("<b>") == "&lt;b&gt;")
fp1 = ExceptionFingerprinter.fingerprint(ValueError("x")); fp2 = ExceptionFingerprinter.fingerprint(ValueError("x"))
check("异常指纹稳定", fp1 == fp2 and len(fp1) == 12)
hrep = HEALTH.run()
check("健康检查 status", hrep["status"] in ("ok","degraded","down") and "system" in hrep["checks"] and "eventbus" in hrep["checks"])
check("异步健康检查", __import__("asyncio").run(HEALTH.run_async())["status"] in ("ok","degraded","down"))
import logging
rec = logging.LogRecord("t",20,"f",1,"token=abc123def456 secret: xyz",(),None)
__import__("good_addons")._sanitize_filter.filter(rec)
print("[7] diag()")
out = __import__("good_addons").diag(include_health=True)
check("diag 输出", "Performance" in out and "Health Report" in out)
check("registry 发现5个", len(__import__("good_addons.registry", fromlist=["x"]).discover()) == 5)
check("export 完整", len(__import__("good_addons").__all__) == 32)
finish()
