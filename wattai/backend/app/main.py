"""
WattAI FastAPI backend
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.endpoints import auth, devices, readings, subscriptions, admin, provisioning, tariffs

app = FastAPI(
    title="WattAI API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router,          prefix="/api/v1/auth",          tags=["auth"])
app.include_router(devices.router,       prefix="/api/v1/devices",       tags=["devices"])
app.include_router(readings.router,      prefix="/api/v1/readings",       tags=["readings"])
app.include_router(subscriptions.router, prefix="/api/v1/subscriptions",  tags=["subscriptions"])
app.include_router(tariffs.router,       prefix="/api/v1/tariffs",        tags=["tariffs"])
app.include_router(provisioning.router,  prefix="/api/v1/provisioning",   tags=["provisioning"])
app.include_router(admin.router,         prefix="/api/v1/admin",          tags=["admin"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
