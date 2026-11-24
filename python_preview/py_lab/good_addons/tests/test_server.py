"""真实服务器冒烟：uvicorn(FastAPI) / hypercorn(Quart) / Flask(dev) 各起一个子进程。"""

from pathlib import Path as _P
import sys as _s
_ROOT = _P(__file__).resolve().parent.parent.parent
_s.path.insert(0, str(_ROOT))

import os, sys, time, subprocess, httpx, signal, os
PORT=int(sys.argv[1]) if len(sys.argv)>1 else 8137; MODE=sys.argv[2] if len(sys.argv)>2 else "uvicorn"
code={
"uvicorn":f"""
from fastapi import FastAPI
from good_addons import boost
app=FastAPI()
@app.get("/ping")
async def ping(): return {{"ok":True}}
boost(app, backend="fastapi", server="uvicorn", log_level="INFO")
""",
"hypercorn":f"""
from quart import Quart
from good_addons import boost
app=Quart(__name__)
@app.get("/ping")
async def ping(): return {{"ok":True}}
boost(app, backend="quart", server="hypercorn", log_level="INFO")
""",
"flask":f"""
from flask import Flask
from good_addons import boost
app=Flask(__name__)
@app.get("/ping")
def ping(): return {{"ok":True}}
boost(app, backend="flask", log_level="INFO")
"""
}[MODE]
cmd={"uvicorn":[sys.executable,"-m","uvicorn",f"good_addons.tests._srv_{MODE}:app","--port",str(PORT),"--log-level","warning"],
     "hypercorn":[sys.executable,"-m","hypercorn",f"good_addons.tests._srv_{MODE}:app","-b",f"127.0.0.1:{PORT}"],
     "flask":[sys.executable,str(_ROOT / "good_addons" / "tests" / f"_srv_{MODE}.py")]}[MODE]
open(_ROOT / "good_addons" / "tests" / f"_srv_{MODE}.py", "w").write(code)
if MODE=="flask":  # flask 不依赖外部服务器，脚本内自启动
    code += "\napp.run(port=%d)\n" % PORT
    open(_ROOT / "good_addons" / "tests" / f"_srv_{MODE}.py", "w").write(code)
p=subprocess.Popen(cmd,env={**os.environ, "PYTHONPATH": str(_ROOT)},stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,start_new_session=True)
try:
    for _ in range(60):
        try:
            r=httpx.get(f"http://127.0.0.1:{PORT}/ping",timeout=1)
            if r.status_code==200:
                print(f"✅ {MODE}: 200 {r.json()} headers={ {k:r.headers[k] for k in r.headers if k in ('Content-Security-Policy','X-Request-ID','X-Content-Type-Options')} }"); break
        except Exception: time.sleep(0.5)
    else: print(f"❌ {MODE}: 启动超时"); sys.exit(1)
    r=httpx.get(f"http://127.0.0.1:{PORT}/ping",headers={"X-Trace-ID":"abc123"},timeout=2)
    print(f"✅ trace 透传: {r.headers.get('X-Request-ID')}")
    hdrs={k.lower():v for k,v in r.headers.items()}
    need=["content-security-policy","x-content-type-options","x-frame-options","referrer-policy","permissions-policy"]
    miss=[h for h in need if h not in hdrs]
    print(("✅ 安全头齐全" if not miss else f"❌ 缺安全头 {miss}"), "| CSP:", hdrs.get("content-security-policy"))
finally:
    os.killpg(p.pid, signal.SIGTERM); p.wait()
