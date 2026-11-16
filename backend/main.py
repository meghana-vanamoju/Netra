from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from db.session import get_db, init_db
from api_devices import router as devices_router
from api_discovery import router as discovery_router
from api_classification import router as classification_router
from api_dns import router as dns_router
from api_audit import router as audit_router, device_router as audit_device_router
from api_policy import router as policy_router
from api_consent import router as consent_router
from api_snapshot import router as snapshot_router
from api_capabilities import router as capabilities_router
from api_enforcement import router as enforcement_router
from api_verification import router as verification_router

@asynccontextmanager
async def lifespan(app):
    init_db()
    yield

app = FastAPI(title="Netra API", version="0.1.0", lifespan=lifespan)
app.include_router(devices_router)
app.include_router(discovery_router)
app.include_router(classification_router)
app.include_router(dns_router)
app.include_router(audit_router)
app.include_router(audit_device_router)
app.include_router(policy_router)
app.include_router(consent_router)
app.include_router(snapshot_router)
app.include_router(capabilities_router)
app.include_router(enforcement_router)
app.include_router(verification_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "netra-backend", "version": "0.1.0"}

@app.get("/api/db/health")
def db_health(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
