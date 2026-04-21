import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# --- Tenant schemas ---

class WidgetConfig(BaseModel):
    primary_color: str = "#2563eb"
    text_color: str = "#ffffff"
    logo_url: str | None = None
    welcome_message: str = "Hi! How can I help you today?"
    placeholder_text: str = "Type your message..."
    position: str = "bottom-right"


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    system_prompt: str = "You are a helpful assistant for a not-for-profit organization."
    widget_config: WidgetConfig = WidgetConfig()


class TenantUpdate(BaseModel):
    name: str | None = None
    system_prompt: str | None = None
    widget_config: WidgetConfig | None = None
    active: bool | None = None


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    api_key: str
    system_prompt: str
    widget_config: dict
    created_at: datetime
    active: bool

    model_config = {"from_attributes": True}


class TenantPublicResponse(BaseModel):
    name: str
    slug: str
    widget_config: dict

    model_config = {"from_attributes": True}


# --- Document schemas ---

class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    source_url: str | None = None


class DocumentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    title: str
    source_url: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Chat schemas ---

class ChatRequest(BaseModel):
    org_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str = Field(..., min_length=1, max_length=100)


class SourceReference(BaseModel):
    document_title: str
    chunk_content: str
    source_url: str | None = None
    relevance_score: float


class ChatResponse(BaseModel):
    response: str
    sources: list[SourceReference] = []
    session_id: str
    conversation_id: uuid.UUID


# --- Admin schemas ---

class UsageStats(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    total_conversations: int
    total_messages: int
    total_tokens: int
    documents_count: int


class ConversationLog(BaseModel):
    id: uuid.UUID
    session_id: str
    started_at: datetime
    last_message_at: datetime
    message_count: int

    model_config = {"from_attributes": True}


class MessageLog(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    tokens_used: int
    created_at: datetime

    model_config = {"from_attributes": True}
