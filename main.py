from fastapi import FastAPI
from routers import scan, clearwing, watch

app = FastAPI(title="FixAI", version="1.0.0", description="Code analysis and refactoring suggestion service")

app.include_router(scan.router)
app.include_router(clearwing.router)
app.include_router(watch.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "fixai", "port": 8005}
