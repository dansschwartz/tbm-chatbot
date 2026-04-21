# TBM Chatbot — API Reference

Base URL: `https://your-deployment.up.railway.app`

## Authentication

Admin endpoints require `X-Admin-Key` header matching the `ADMIN_API_KEY` environment variable.

Public endpoints (chat, contact, widget config) authenticate by tenant `org_id` or `slug`.

---

## Public Endpoints (No Auth Required)

### Chat
```
POST /api/chat
```
Send a message and get an AI response grounded in the tenant's knowledge base.

**Body:**
```json
{
  "org_id": "dcsc-slug",
  "message": "How do I register?",
  "session_id": "visitor-abc123",
  "visitor_name": "Jane Doe",        // optional, from pre-chat form
  "visitor_email": "jane@example.com" // optional
}
```

**Response:**
```json
{
  "response": "You can register through PlayMetrics...",
  "sources": [
    {"title": "Rec League", "url": "https://dcsoccerclub.org/rec-league"}
  ],
  "suggestions": ["What does registration cost?", "When does the season start?"],
  "conversation_id": "uuid",
  "is_away": false
}
```

### Contact Form (Human Handoff)
```
POST /api/contact
```
Submit a contact request when the bot can't help.

**Body:**
```json
{
  "tenant_id": "uuid",
  "visitor_name": "Jane Doe",
  "visitor_email": "jane@example.com",
  "message": "I need help with a refund",
  "conversation_id": "uuid"  // optional
}
```

### Feedback (Thumbs Up/Down)
```
POST /api/feedback
```
**Body:**
```json
{
  "message_id": "uuid",
  "conversation_id": "uuid",
  "tenant_id": "uuid",
  "rating": "positive"  // or "negative"
}
```

### CSAT Rating
```
POST /api/csat
```
**Body:**
```json
{
  "conversation_id": "uuid",
  "tenant_id": "uuid",
  "rating": 5,           // 1-5
  "comment": "Very helpful!"  // optional
}
```

### Widget Configuration
```
GET /api/tenants/public/{slug}
```
Returns all widget-facing configuration. Used by the embeddable widget on page load.

**Response:**
```json
{
  "name": "DC Soccer Club",
  "slug": "dcsc",
  "widget_config": {
    "primary_color": "#c41e3a",
    "welcome_message": "Hi! How can I help?",
    "bot_name": "DCSC Assistant",
    "bot_avatar": "⚽",
    "prechat_enabled": true,
    "prechat_fields": ["name", "email"]
  },
  "quick_replies": ["How do I register?", "What programs do you offer?"],
  "launcher_teaser": "Need help with registration?",
  "business_hours": {
    "timezone": "America/New_York",
    "hours": {"mon": ["9:00","17:00"], "tue": ["9:00","17:00"]}
  },
  "away_message": "We're currently offline but the bot can still help!",
  "csat_enabled": true
}
```

---

## Admin Endpoints (Require X-Admin-Key)

### Tenant Management
```
POST   /api/tenants              — Create tenant
GET    /api/tenants              — List all tenants
GET    /api/tenants/{id}         — Get tenant details
PATCH  /api/tenants/{id}         — Update tenant (including guidance_rules, support_email, etc.)
DELETE /api/tenants/{id}         — Delete tenant
```

**Create Tenant Body:**
```json
{
  "name": "DC Soccer Club",
  "slug": "dcsc",
  "system_prompt": "You are a helpful assistant for DC Soccer Club...",
  "guidance_rules": "Always recommend financial aid when cost is mentioned.\nNever discuss competitor clubs.",
  "support_email": "info@dcsoccerclub.org",
  "quick_replies": ["How do I register?", "What programs do you offer?", "Do you offer financial aid?"],
  "launcher_teaser": "Need help with registration?",
  "business_hours": {"timezone": "America/New_York", "hours": {"mon": ["9:00","17:00"]}},
  "away_message": "We're offline, but the bot can still help!",
  "widget_config": {"primary_color": "#c41e3a", "bot_name": "DCSC Assistant", "bot_avatar": "⚽"},
  "csat_enabled": true,
  "daily_message_limit": 1000
}
```

### Document Management
```
POST   /api/tenants/{id}/documents         — Upload single document
GET    /api/tenants/{id}/documents         — List documents
GET    /api/tenants/{id}/documents/{docid} — Get document
DELETE /api/tenants/{id}/documents/{docid} — Delete document
POST   /api/tenants/{id}/documents/bulk    — Bulk upload documents
PUT    /api/tenants/{id}/documents/{docid}/reingest — Re-process document
```

**Single Document Body:**
```json
{
  "title": "Rec League",
  "content": "DC Soccer Club's recreational program...",
  "source_url": "https://dcsoccerclub.org/rec-league"
}
```

**Bulk Upload Body:**
```json
{
  "documents": [
    {"title": "Rec League", "content": "...", "source_url": "..."},
    {"title": "Travel Program", "content": "...", "source_url": "..."}
  ]
}
```

### Analytics & Admin
```
GET /api/admin/analytics?tenant_id=...&days=30  — Full analytics summary
GET /api/admin/usage                              — Usage stats per tenant
GET /api/admin/contacts?tenant_id=...            — Contact form submissions
GET /api/admin/feedback?tenant_id=...            — Message feedback (thumbs)
GET /api/admin/csat?tenant_id=...                — CSAT ratings
GET /api/admin/unanswered?tenant_id=...          — Fallback/unanswered questions
GET /api/admin/conversations/search?tenant_id=...&q=... — Search conversations
GET /api/admin/tenants/{id}/conversations        — List conversations
GET /api/admin/conversations/{id}/messages       — Get conversation messages
```

**Analytics Response:**
```json
{
  "total_conversations": 156,
  "total_messages": 892,
  "avg_messages_per_conversation": 5.7,
  "total_contact_requests": 12,
  "resolution_rate": 0.92,
  "avg_csat_score": 4.3,
  "top_tags": [
    {"tag": "registration", "count": 45},
    {"tag": "financial-aid", "count": 23}
  ],
  "messages_per_day": [
    {"date": "2026-04-20", "count": 34},
    {"date": "2026-04-21", "count": 41}
  ],
  "busiest_hours": [10, 14, 16]
}
```

---

## Webhooks

Configure `webhook_url` on a tenant to receive real-time event notifications.

**Supported events:** `contact_request.created`, `conversation.started`, `feedback.negative`, `fallback.detected`

**Payload format:**
```json
{
  "event": "contact_request.created",
  "tenant_id": "uuid",
  "timestamp": "2026-04-21T16:30:00Z",
  "data": {
    "visitor_name": "Jane Doe",
    "visitor_email": "jane@example.com",
    "message": "I need help with a refund"
  }
}
```

---

## Widget Embed

Add to any website (Squarespace, WordPress, Wix, raw HTML):

```html
<script src="https://your-deployment.up.railway.app/widget/chat-widget.js" data-org="dcsc"></script>
<link rel="stylesheet" href="https://your-deployment.up.railway.app/widget/chat-widget.css">
```

The widget auto-configures based on the tenant slug in `data-org`.
