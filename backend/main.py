from fastapi import FastAPI

app = FastAPI(title="CarBot V2 Minimal API")


@app.get("/health")
async def health():
    return {"status": "ok"}
