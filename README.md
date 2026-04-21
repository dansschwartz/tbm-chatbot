# TBM Chatbot

Multi-tenant AI chatbot service for not-for-profit organizations. Drop a chat widget on any NFP's website — it answers visitor questions using the org's own content via RAG (Retrieval-Augmented Generation).

**Live demo:** [tbm-chatbot-production.up.railway.app/demo](https://tbm-chatbot-production.up.railway.app/demo)

## Architecture

```
Visitor's Browser                    Your Platform
    ↓ (chat widget)                      ↓ (webhooks, API)
┌───────────────────────────────────────────────────┐
│              TBM Chatbot API (FastAPI)             │
│                                                     │
│  ┌─────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Tenant  │  │ Document │  │   RAG Pipeline    │  │
│  │ Manager │  │ Ingester │  │ Embed→Search→LLM  │  │
│  └─────────┘  └──────────┘  └──────────────────┘  │
│                      ↓                              │
│  ┌─────────────────────────────────────────────┐   │
│  │   Neon Postgres + pgvector                   │   │
│  │   (tenants, docs, chunks, conversations)     │   │
│  └─────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────┘
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.12 + FastAPI (async) |
| Database | Neon (Postgres + pgvector) |
| LLM | OpenAI GPT-4o-mini |
| Embeddings | OpenAI text-embedding-3-small (1536 dim) |
| Widget | Vanilla JS + CSS (~1,000 lines, no dependencies) |
| Hosting | Railway (Docker) |

## Features (22)

### AI & Knowledge Base
- ✅ RAG pipeline with vector similarity search
- ✅ Automatic document chunking (~500 tokens with overlap)
- ✅ Source citations in responses
- ✅ Follow-up question suggestions (AI-generated)
- ✅ Meta instructions / guidance rules per tenant
- ✅ Fallback detection (tracks when bot can't answer)
- ✅ Context-only answers (won't hallucinate beyond the knowledge base)

### Chat Widget
- ✅ Embeddable on any website (single `<script>` tag)
- ✅ Custom branding per tenant (colors, name, avatar)
- ✅ Quick reply buttons (configurable)
- ✅ Proactive launcher teaser message
- ✅ Pre-chat form (name + email collection)
- ✅ Conversation persistence via localStorage (24hr)
- ✅ Rich message formatting (markdown: bold, lists, links)
- ✅ Typing indicator with timeout
- ✅ Chat transcript export/download
- ✅ Mobile responsive

### Human Handoff & Support
- ✅ Contact form with email routing
- ✅ Business hours / away mode (timezone-aware)
- ✅ Support email configuration per tenant

### Feedback & Analytics
- ✅ Thumbs up/down on bot messages
- ✅ CSAT survey (1-5 star rating after N messages)
- ✅ Full analytics endpoint (conversations, resolution rate, CSAT, top tags, volume over time)
- ✅ Unanswered questions log (content gap analysis)
- ✅ Auto-tagging conversations by topic
- ✅ Conversation search (full-text)

### Integration & Admin
- ✅ Webhook notifications (contact requests, negative feedback, fallbacks)
- ✅ Bulk document ingestion API
- ✅ Content re-ingestion (refresh when source changes)
- ✅ Per-tenant daily message quotas
- ✅ Multi-tenant isolation (data never leaks between orgs)
- ✅ Widget fully driven by tenant config API (zero hardcoded values)

## Quick Start

### 1. Environment Variables

```env
DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
OPENAI_API_KEY=sk-...
ADMIN_API_KEY=your-admin-key
CORS_ORIGINS=*
```

### 2. Deploy to Railway

Connect this repo to Railway. It auto-deploys on push. Tables auto-create on first startup.

### 3. Create a Tenant

```bash
curl -X POST https://your-app.up.railway.app/api/tenants \
  -H "X-Admin-Key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "DC Soccer Club",
    "slug": "dcsc",
    "system_prompt": "You are a helpful assistant for DC Soccer Club...",
    "support_email": "info@dcsoccerclub.org",
    "quick_replies": ["How do I register?", "What programs do you offer?"]
  }'
```

### 4. Upload Content

```bash
curl -X POST https://your-app.up.railway.app/api/tenants/{id}/documents/bulk \
  -H "X-Admin-Key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"documents": [{"title": "Rec League", "content": "..."}]}'
```

### 5. Embed the Widget

```html
<script src="https://your-app.up.railway.app/widget/chat-widget.js" data-org="dcsc"></script>
<link rel="stylesheet" href="https://your-app.up.railway.app/widget/chat-widget.css">
```

## Cost Estimate

Using GPT-4o-mini + text-embedding-3-small:
- **~500 conversations for $1** in API costs
- A typical NFP site (50 chats/day): **~$3/month**
- Neon free tier: **$0**
- Railway: **$5/month** (hobby plan)

**Total: ~$8/month** vs Intercom's $130+/month

## API Documentation

See [docs/API-REFERENCE.md](docs/API-REFERENCE.md) for the complete API reference.

## Project Structure

```
tbm-chatbot/
├── app/
│   ├── main.py              # FastAPI app + startup
│   ├── config.py             # Environment config
│   ├── database.py           # Async Postgres/pgvector
│   ├── models.py             # SQLAlchemy models (8 tables)
│   ├── schemas.py            # Pydantic request/response schemas
│   ├── routers/
│   │   ├── chat.py           # Chat endpoint + auto-tagging
│   │   ├── tenants.py        # Tenant CRUD
│   │   ├── documents.py      # Document upload + bulk + reingest
│   │   ├── contact.py        # Contact form / human handoff
│   │   ├── feedback.py       # Thumbs up/down
│   │   └── admin.py          # Analytics, search, CSAT, unanswered
│   └── services/
│       ├── rag.py            # RAG pipeline + guidance + suggestions
│       ├── embeddings.py     # OpenAI embedding service
│       ├── chunking.py       # Document chunking
│       └── openai_client.py  # OpenAI API wrapper
├── widget/
│   ├── chat-widget.js        # Production embeddable widget
│   └── chat-widget.css       # Widget styles
├── demo/
│   └── index.html            # Demo page (DC Soccer Club mockup)
├── data/
│   ├── raw/                  # Raw crawled website data
│   └── clean/                # Cleaned, categorized data for ingestion
├── docs/
│   ├── API-REFERENCE.md      # Complete API documentation
│   └── CLIENT-PITCH.md       # Client-facing pitch document
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## License

Private — proprietary software.
