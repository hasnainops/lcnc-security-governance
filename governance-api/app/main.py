from fastapi import FastAPI

app = FastAPI(
    title="LCNC Security Governance API",
    description="Governance control plane for low-code/no-code applications",
    version="0.1.0"
)

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "governance-api",
        "version": "0.1.0"
    }
