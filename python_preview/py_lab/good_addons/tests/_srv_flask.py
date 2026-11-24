
from flask import Flask
from good_addons import boost
app=Flask(__name__)
@app.get("/ping")
def ping(): return {"ok":True}
boost(app, backend="flask", log_level="INFO")

app.run(port=8139)
