import uuid
from datetime import datetime, date

from pydantic import BaseModel, Field


# --- Tenant schemas ---

class WidgetPosition(BaseModel):
    side: str = "right"  # "right" or "left"
    bottom_offset: int = 20
    side_offset: int = 20


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
    # Feature 33: Widget position customization
    widget_position: WidgetPosition = WidgetPosition()


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
    # Feature 11: Webhooks
    webhook_url: str | None = None
    webhook_events: list[str] | None = None
    # Feature 12: CSAT
    csat_enabled: bool | None = None
    csat_trigger_after: int | None = None
    # Feature 22: Daily message quota
    daily_message_limit: int | None = None
    # Feature 25: Custom CSS
    custom_css: str | None = None
    # Feature 26: Multi-language
    default_language: str | None = None
    supported_languages: list[str] | None = None
    # Feature 27: Greeting variants
    greeting_variants: list[str] | None = None
    # Feature 28: Escalation triggers
    escalation_triggers: list[str] | None = None
    # Feature 34: Banned words
    banned_words: list[str] | None = None
    # Feature 39: WhatsApp
    whatsapp_enabled: bool | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_whatsapp_number: str | None = None
    # Feature 40: Email notifications
    email_notifications_enabled: bool | None = None
    # Feature 44: A/B testing
    ab_test_enabled: bool | None = None


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
    webhook_url: str | None = None
    webhook_events: list | None = None
    csat_enabled: bool = False
    csat_trigger_after: int = 5
    daily_message_limit: int | None = None
    custom_css: str | None = None
    default_language: str = "en"
    supported_languages: list | None = None
    greeting_variants: list | None = None
    escalation_triggers: list | None = None
    banned_words: list | None = None
    whatsapp_enabled: bool = False
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_whatsapp_number: str | None = None
    email_notifications_enabled: bool = False
    ab_test_enabled: bool = False

    model_config = {"from_attributes": True}


class TenantPublicResponse(BaseModel):
    name: str
    slug: str
    widget_config: dict
    quick_replies: list | None = None
    support_email: str | None = None
    business_hours: dict | None = None
    away_message: str | None = None
    csat_enabled: bool = False
    csat_trigger_after: int = 5
    # Feature 25: Custom CSS
    custom_css: str | None = None
    # Feature 26: Multi-language
    default_language: str = "en"
    supported_languages: list | None = None
    # Feature 27: Greeting variants
    greeting_variants: list | None = None
    # Feature 28: Escalation triggers
    escalation_triggers: list | None = None

    model_config = {"from_attributes": True}


# --- Document schemas ---

class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    source_url: str | None = None
    # Feature 23: Category for article browser
    category: str | None = None
    # Feature 30: PDF support — "text" or "pdf"
    content_type: str = "text"


class DocumentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    title: str
    source_url: str | None
    status: str
    created_at: datetime
    last_ingested_at: datetime | None = None
    content_type: str = "text"
    category: str | None = None

    model_config = {"from_attributes": True}


# --- Bulk document ingestion (Feature 17) ---

class BulkDocumentItem(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    source_url: str | None = None


class BulkDocumentRequest(BaseModel):
    documents: list[BulkDocumentItem] = Field(..., min_length=1)


class BulkDocumentResponse(BaseModel):
    total: int
    succeeded: int
    failed: int


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
    suggestions: list[str] = []


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
    summary: str | None = None
    channel: str = "web"
    greeting_variant_used: str | None = None

    model_config = {"from_attributes": True}


class MessageLog(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    tokens_used: int
    created_at: datetime
    is_fallback: bool | None = False
    response_time_ms: int | None = None

    model_config = {"from_attributes": True}


class UnansweredMessage(BaseModel):
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    session_id: str
    user_question: str
    bot_response: str
    created_at: datetime

    model_config = {"from_attributes": True}


# --- CSAT schemas (Feature 12) ---

class CSATCreate(BaseModel):
    conversation_id: uuid.UUID
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None


class CSATResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    tenant_id: uuid.UUID
    rating: int
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Analytics summary (Feature 20) ---

class MessagesPerDay(BaseModel):
    date: str
    count: int


class TagCount(BaseModel):
    tag: str
    count: int


class AnalyticsSummary(BaseModel):
    total_conversations: int
    total_messages: int
    avg_messages_per_conversation: float
    total_contact_requests: int
    resolution_rate: float  # percentage of non-fallback responses
    avg_csat_score: float | None
    top_tags: list[TagCount]
    messages_per_day: list[MessagesPerDay]
    busiest_hours: list[int]
    daily_message_usage: int | None = None  # Feature 22
    avg_response_time_ms: float | None = None  # Feature 32


# --- Conversation search (Feature 21) ---

class ConversationSearchResult(BaseModel):
    conversation_id: uuid.UUID
    session_id: str
    visitor_name: str | None = None
    visitor_email: str | None = None
    message_id: uuid.UUID
    role: str
    snippet: str
    created_at: datetime


# --- Feature 23: Article browser ---

class ArticleItem(BaseModel):
    id: uuid.UUID
    title: str
    snippet: str
    source_url: str | None = None
    category: str | None = None

    model_config = {"from_attributes": True}


# --- Feature 29: Scheduled messages ---

class ScheduledMessageCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    target: str = Field(default="all_new", pattern=r"^(all_new|returning)$")
    active: bool = True
    start_date: datetime | None = None
    end_date: datetime | None = None


class ScheduledMessageResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    message: str
    target: str
    active: bool
    start_date: datetime | None
    end_date: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Feature 31: Conversation notes ---

class ConversationNoteCreate(BaseModel):
    author: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1, max_length=4000)


class ConversationNoteResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    tenant_id: uuid.UUID
    author: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Feature 36: Health dashboard ---

class HealthDashboard(BaseModel):
    status: str
    db_connected: bool
    total_tenants: int
    total_documents: int
    total_conversations: int
    uptime_seconds: float
    version: str


# --- Feature 42: Document auto-crawler ---

class CrawlRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2000)
    title: str | None = None
    category: str | None = None


# --- Feature 44: A/B Testing analytics ---

class ABTestResult(BaseModel):
    variant: str
    conversation_count: int
    avg_messages: float


# --- Feature 45: Smart Insights ---

class Insight(BaseModel):
    type: str  # "content_gap", "performance", "engagement"
    title: str
    description: str
    priority: str = "medium"  # "high", "medium", "low"
