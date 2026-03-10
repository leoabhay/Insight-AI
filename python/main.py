from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import connect_db, disconnect_db
from routers import csv_router, auth_router, health_router

app = FastAPI(
    title="Analytics Dashboard API",
    version="1.0.0",
    description="CSV ingestion, big-data processing, and chart data API.",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lifecycle
@app.on_event("startup")
async def startup():
    await connect_db()

@app.on_event("shutdown")
async def shutdown():
    await disconnect_db()

# Routers
app.include_router(health_router.router)
app.include_router(auth_router.router, prefix="/auth", tags=["auth"])
app.include_router(csv_router.router, prefix="/csv", tags=["csv"])