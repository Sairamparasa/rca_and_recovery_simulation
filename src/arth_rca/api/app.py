"""
FastAPI Application Entrypoint for ARTH RCA.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from arth_rca.api.routes.analytics import router as analytics_router
from arth_rca.api.routes.classification import router as classification_router
from arth_rca.api.routes.scenarios import router as scenarios_router
from arth_rca.api.routes.optimization import router as optimization_router
from arth_rca.api.routes.reasoning import router as reasoning_router
from arth_rca.db.database import init_db

app = FastAPI(
    title="ARTH RCA Engine",
    description="Automated Root Cause Analysis and Recovery Simulation for Construction & Capital Schedules",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    try:
        init_db()
    except Exception:
        pass

app.include_router(analytics_router)
app.include_router(classification_router)
app.include_router(scenarios_router)
app.include_router(optimization_router)
app.include_router(reasoning_router)

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "ARTH RCA Engine", "version": "1.0.0"}
