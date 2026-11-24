
from quart import Quart
from good_addons import boost
app=Quart(__name__)
@app.get("/ping")
async def ping(): return {"ok":True}
boost(app, backend="quart", server="hypercorn", log_level="INFO")
