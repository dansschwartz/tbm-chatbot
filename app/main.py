import logging
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from sqlalchemy import text

from app.config import settings

logging.basicConfig(level=getattr(logging, settings.log_level), format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("app")

# Log masked DB URL for debugging
masked_url = re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', settings.database_url)
logger.info(f"DATABASE_URL (masked): {masked_url}")

from app.database import engine, db_url as resolved_db_url
from app.models import Base
from app.routers import admin, chat, contact, documents, feedback, tenants
from app.services.openai_client import close_client

masked_resolved = re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', resolved_db_url)
logger.info(f"Resolved DB URL (masked): {masked_resolved}")

app = FastAPI(
    title="TBM Chatbot API",
    description="Multi-tenant RAG chatbot service for not-for-profit organizations",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(chat.router)
app.include_router(tenants.router)
app.include_router(documents.router)
app.include_router(admin.router)
app.include_router(contact.router)
app.include_router(feedback.router)

# Serve widget static files
app.mount("/widget", StaticFiles(directory="widget"), name="widget")

# Serve demo page
app.mount("/demo", StaticFiles(directory="demo", html=True), name="demo")


@app.on_event("startup")
async def startup():
    """Create tables and enable pgvector on first run."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables ready")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        logger.error("Check your DATABASE_URL environment variable in Railway")
        # Don't crash the app — let health check report the issue
        pass


@app.get("/health")
async def health_check():
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "healthy", "service": "tbm-chatbot"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e), "hint": "Check DATABASE_URL"}
        )


@app.on_event("shutdown")
async def shutdown():
    await close_client()
