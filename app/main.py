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
from app.routers import admin, articles, chat, contact, csat, documents, feedback, tenants
from app.services.openai_client import close_client

masked_resolved = re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', resolved_db_url)
logger.info(f"Resolved DB URL (masked): {masked_resolved}")

APP_VERSION = "2.0.0"
_startup_time = None

app = FastAPI(
    title="TBM Chatbot API",
    description="Multi-tenant RAG chatbot service for not-for-profit organizations",
    version=APP_VERSION,
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
app.include_router(csat.router)
app.include_router(articles.router)

# Serve widget static files
app.mount("/widget", StaticFiles(directory="widget"), name="widget")

# Serve demo page
app.mount("/demo", StaticFiles(directory="demo", html=True), name="demo")


@app.on_event("startup")
async def startup():
    """Create tables and enable pgvector on first run."""
    global _startup_time
    import time as _time
    _startup_time = _time.time()
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            # Drop and recreate all tables (safe while no production data)
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables ready")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        logger.error("Check your DATABASE_URL environment variable in Railway")
        pass


# Feature 36: Enhanced health dashboard
@app.get("/health")
async def health_check():
    import time as _time
    from app.models import Tenant, Document, Conversation

    db_connected = False
    total_tenants = 0
    total_documents = 0
    total_conversations = 0

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
            db_connected = True
            row = await conn.execute(text("SELECT count(*) FROM tenants"))
            total_tenants = row.scalar() or 0
            row = await conn.execute(text("SELECT count(*) FROM documents"))
            total_documents = row.scalar() or 0
            row = await conn.execute(text("SELECT count(*) FROM conversations"))
            total_conversations = row.scalar() or 0
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "db_connected": False,
                "error": str(e),
                "hint": "Check DATABASE_URL",
                "version": APP_VERSION,
            },
        )

    uptime = round(_time.time() - _startup_time, 1) if _startup_time else 0

    return {
        "status": "healthy",
        "db_connected": db_connected,
        "total_tenants": total_tenants,
        "total_documents": total_documents,
        "total_conversations": total_conversations,
        "uptime_seconds": uptime,
        "version": APP_VERSION,
    }


@app.on_event("shutdown")
async def shutdown():
    await close_client()
