from fastapi import FastAPI

app = FastAPI(title="API Request Generator")

@app.get("/health")
def health():
    return {"status": "ok"}