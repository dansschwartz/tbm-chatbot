import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import admin, chat, documents, tenants
from app.services.openai_client import close_client

logging.basicConfig(level=getattr(logging, settings.log_level), format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(
    title="TBM Chatbot API",
    description="Multi-tenant RAG chatbot service for not-for-profit organizations",
    version="1.0.0",
)

# CORS
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins + ["*"],  # Widget needs to be embedded anywhere
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(chat.router)
app.include_router(tenants.router)
app.include_router(documents.router)
app.include_router(admin.router)

# Serve widget static files
app.mount("/widget", StaticFiles(directory="widget"), name="widget")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "tbm-chatbot"}


@app.on_event("shutdown")
async def shutdown():
    await close_client()
