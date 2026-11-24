
from fastapi import FastAPI
from good_addons import boost
app=FastAPI()
@app.get("/ping")
async def ping(): return {"ok":True}
boost(app, backend="fastapi", server="uvicorn", log_level="INFO")
