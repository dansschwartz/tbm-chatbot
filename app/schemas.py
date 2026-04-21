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
    # Feature 3: Pre-chat form config
    prechat_enabled: bool = False
    prechat_fields: list[str] = []
    # Feature 6: Launcher teaser
    launcher_teaser: str | None = None


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
    # Feature 1: Meta instructions
    guidance_rules: str | None = None
    # Feature 2: Support email
    support_email: str | None = None
    # Feature 5: Quick replies
    quick_replies: list[str] | None = None
    # Feature 8: Business hours & away mode
    business_hours: dict | None = None
    away_message: str | None = None


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    api_key: str
    system_prompt: str
    widget_config: dict
    created_at: datetime
    active: bool
    guidance_rules: str | None = None
    support_email: str | None = None
    quick_replies: list | None = None
    business_hours: dict | None = None
    away_message: str | None = None

    model_config = {"from_attributes": True}


class TenantPublicResponse(BaseModel):
    name: str
    slug: str
    widget_config: dict
    quick_replies: list | None = None
    support_email: str | None = None
    business_hours: dict | None = None
    away_message: str | None = None

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
    # Feature 3: Pre-chat form data
    visitor_name: str | None = None
    visitor_email: str | None = None


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
    message_id: uuid.UUID | None = None
    is_fallback: bool = False


# --- Contact schemas (Feature 2) ---

class ContactCreate(BaseModel):
    org_id: str = Field(..., min_length=1)
    visitor_name: str = Field(..., min_length=1, max_length=255)
    visitor_email: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None


class ContactResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    visitor_name: str
    visitor_email: str
    message: str
    conversation_id: uuid.UUID | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Feedback schemas (Feature 7) ---

class FeedbackCreate(BaseModel):
    message_id: uuid.UUID
    rating: str = Field(..., pattern=r"^(positive|negative)$")


class FeedbackResponse(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    tenant_id: uuid.UUID
    rating: str
    created_at: datetime

    model_config = {"from_attributes": True}


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
    visitor_name: str | None = None
    visitor_email: str | None = None
    tags: list | None = None

    model_config = {"from_attributes": True}


class MessageLog(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    tokens_used: int
    created_at: datetime
    is_fallback: bool | None = False

    model_config = {"from_attributes": True}


class UnansweredMessage(BaseModel):
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    session_id: str
    user_question: str
    bot_response: str
    created_at: datetime

    model_config = {"from_attributes": True}
