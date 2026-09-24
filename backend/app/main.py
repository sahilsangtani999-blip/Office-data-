"""
RSSB Office Data Platform — FastAPI Application.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.database import engine

from app.api.documents import router as documents_router
from app.api.validation import router as validation_router
from app.api.query import router as query_router
from app.api.sources import router as sources_router

app = FastAPI(
    title="RSSB Office Data Platform",
    description="API for the RSSB Office Data Platform",
    version="0.1.0",
)

# Enable CORS for local Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents_router)
app.include_router(validation_router)
app.include_router(query_router)
app.include_router(sources_router)


@app.get("/health")
def health_check():
    """
    Health check endpoint.

    Returns the API status and database connectivity.
    """
    db_status = "healthy"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"unhealthy: {exc}"

    return {
        "status": "healthy",
        "database": db_status,
    }
