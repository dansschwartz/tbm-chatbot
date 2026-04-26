# TBM Chatbot

Multi-tenant AI chatbot platform for not-for-profit organizations. Drop an embeddable chat widget on any website — it answers visitor questions using the org's own content via RAG (Retrieval-Augmented Generation).

**Live demo:** [tbm-chatbot-production.up.railway.app/demo](https://tbm-chatbot-production.up.railway.app/demo)
**Admin dashboard:** [tbm-chatbot-production.up.railway.app/admin](https://tbm-chatbot-production.up.railway.app/admin)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        VISITOR'S BROWSER                             │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Chat Widget (vanilla JS/CSS, single <script> tag)          │    │
│  │  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌─────────────────┐  │    │
│  │  │Pre-chat │ │Quick     │ │CSAT    │ │ Article Browser │  │    │
│  │  │Form     │ │Replies   │ │Survey  │ │ (KB Search)     │  │    │
│  │  └─────────┘ └──────────┘ └────────┘ └─────────────────┘  │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
└─────────────────────────────┼────────────────────────────────────────┘
                              │ HTTPS (REST API)
┌─────────────────────────────▼────────────────────────────────────────┐
│                    TBM CHATBOT API (FastAPI)                          │
│                                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────┐ │
│  │ Tenant       │  │ Document     │  │ RAG Pipeline               │ │
│  │ Manager      │  │ Ingester     │  │ Query → Embed → Vector     │ │
│  │              │  │ (crawl/bulk) │  │ Search → Context → LLM     │ │
│  └──────────────┘  └──────────────┘  └────────────────────────────┘ │
│                                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────┐ │
│  │ Analytics    │  │ Feedback     │  │ Webhooks / Email           │ │
│  │ Engine       │  │ & CSAT       │  │ Notifications              │ │
│  └──────────────┘  └──────────────┘  └────────────────────────────┘ │
│                              │                                        │
│  ┌───────────────────────────▼───────────────────────────────────┐   │
│  │              Neon Postgres + pgvector                          │   │
│  │  tenants │ documents │ chunks │ conversations │ messages      │   │
│  │  feedback │ csat │ contacts │ embeddings (1536-dim vectors)   │   │
│  └───────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
  ┌───────────┐      ┌──────────────┐      ┌──────────────┐
  │ OpenAI    │      │ External     │      │ WhatsApp     │
  │ GPT-4o-   │      │ Webhooks     │      │ Business     │
  │ mini      │      │              │      │ API          │
  └───────────┘      └──────────────┘      └──────────────┘
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.12 + FastAPI (fully async) |
| Database | Neon (Postgres + pgvector) |
| LLM | OpenAI GPT-4o-mini |
| Embeddings | OpenAI text-embedding-3-small (1536 dim) |
| Widget | Vanilla JS + CSS (~1,000 lines, zero dependencies) |
| Admin | Single-page dashboard (vanilla JS) |
| Hosting | Railway (Docker) |
| CI/CD | Git push → Railway auto-deploy |

---

## Features (45)

### AI & Knowledge Base
1. RAG pipeline with vector similarity search (pgvector cosine distance)
2. Automatic document chunking (~500 tokens with overlap)
3. Source citations in responses (collapsible in widget)
4. Follow-up question suggestions (AI-generated per response)
5. Meta instructions / guidance rules per tenant
6. Fallback detection (tracks when bot can't answer from knowledge base)
7. Context-only answers (won't hallucinate beyond the knowledge base)
8. Auto-tagging conversations by topic (AI-powered)
9. Banned words filtering per tenant
10. Smart insights engine (content gaps, performance, engagement analysis)

### Chat Widget
11. Embeddable on any website (single `<script>` tag)
12. Custom branding per tenant (colors, logo, name)
13. Quick reply buttons (configurable per tenant)
14. Proactive launcher teaser message (timed popup)
15. Pre-chat form (name + email collection with validation)
16. Conversation persistence via localStorage (24hr TTL)
17. Rich message formatting (markdown: bold, italic, lists, links, emails)
18. Typing indicator with smooth pulse animation
19. Chat transcript export/download (text file)
20. Mobile responsive (full-width on small screens)
21. Knowledge base article browser (search + browse by category)
22. Suggestion chips with gradient borders
23. Smooth open/close slide animation
24. Bot avatar + org name in header with online status
25. "AI support can make mistakes" footer disclaimer

### Human Handoff & Support
26. Contact form with email routing
27. Business hours / away mode (timezone-aware indicator)
28. Support email configuration per tenant
29. Escalation triggers (configurable keywords that suggest human contact)

### Feedback & Analytics
30. Thumbs up/down on bot messages
31. CSAT survey (1-5 star rating, triggered after N messages)
32. Full analytics endpoint (conversations, resolution rate, CSAT, top tags, volume)
33. Unanswered questions log (content gap analysis)
34. Conversation search (full-text across all messages)
35. Satisfaction trend visualization (approval rate bar)
36. Per-tenant daily message quotas

### Integration & Admin
37. Webhook notifications (contact requests, negative feedback, fallbacks)
38. Bulk document ingestion API
39. URL crawling (scrape & ingest web pages)
40. Content re-ingestion (refresh when source changes)
41. Multi-tenant isolation (data never leaks between orgs)
42. Widget fully driven by tenant config API (zero hardcoded values)
43. Conversation export (CSV + JSON)
44. A/B testing for greeting variants
45. New tenant onboarding wizard (5-step guided setup)

### Platform
- Multi-language support (EN, ES, FR, DE, PT, IT, ZH, JA, KO, AR)
- Custom CSS injection per tenant
- Widget position customization (left/right, offsets)
- WhatsApp Business API integration
- Email notifications for contact requests
- Admin dashboard with live monitor (5s polling)
- Smart insights & recommendations engine

---

## Quick Start

### 1. Environment Variables

```env
DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
OPENAI_API_KEY=sk-...
ADMIN_API_KEY=your-admin-key
CORS_ORIGINS=*
```

### 2. Deploy to Railway

Connect this repo to Railway. It auto-deploys on push. Tables auto-create on first startup via SQLAlchemy.

```bash
# Or run locally
pip install -r requirements.txt
uvicorn app.main:app --reload
```

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

Or use the **Admin Dashboard** wizard at `/admin` for guided setup.

### 4. Upload Content

```bash
# Single document
curl -X POST https://your-app.up.railway.app/api/tenants/{id}/documents \
  -H "X-Admin-Key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"title": "Rec League", "content": "...", "category": "Programs"}'

# Bulk upload
curl -X POST https://your-app.up.railway.app/api/tenants/{id}/documents/bulk \
  -H "X-Admin-Key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"documents": [{"title": "FAQ", "content": "..."}]}'

# Crawl a URL
curl -X POST https://your-app.up.railway.app/api/tenants/{id}/documents/crawl \
  -H "X-Admin-Key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.org/about"}'
```

### 5. Embed the Widget

```html
<script src="https://your-app.up.railway.app/widget/chat-widget.js" data-org="your-slug"></script>
```

That's it. One line. The widget auto-loads its CSS, fetches tenant config, and renders itself.

Optional attributes:
- `data-org` — tenant slug (required)
- `data-api` — custom API base URL (defaults to same origin as script)

---

## API Endpoint Summary

### Public (No Auth)
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/chat` | Send a chat message (RAG pipeline) |
| `GET` | `/api/tenants/public/{slug}` | Get public tenant config (widget) |
| `POST` | `/api/contact` | Submit contact/handoff form |
| `POST` | `/api/feedback` | Submit thumbs up/down |
| `POST` | `/api/csat` | Submit CSAT rating |
| `GET` | `/api/tenants/{slug}/articles` | Search knowledge base articles |
| `GET` | `/health` | Health check + uptime |

### Admin (X-Admin-Key header)
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/tenants` | List all tenants |
| `POST` | `/api/tenants` | Create tenant |
| `GET` | `/api/tenants/{id}` | Get tenant details |
| `PATCH` | `/api/tenants/{id}` | Update tenant config |
| `POST` | `/api/tenants/{id}/documents` | Add document |
| `POST` | `/api/tenants/{id}/documents/bulk` | Bulk add documents |
| `POST` | `/api/tenants/{id}/documents/crawl` | Crawl URL → document |
| `DELETE` | `/api/tenants/{id}/documents/{doc_id}` | Delete document |
| `POST` | `/api/tenants/{id}/documents/reingest` | Re-chunk & re-embed |
| `GET` | `/api/admin/usage` | Usage stats per tenant |
| `GET` | `/api/admin/analytics` | Full analytics (30d) |
| `GET` | `/api/admin/feedback` | Feedback entries |
| `GET` | `/api/admin/unanswered` | Unanswered questions |
| `GET` | `/api/admin/insights` | Smart recommendations |
| `GET` | `/api/admin/contacts` | Contact form submissions |
| `GET` | `/api/admin/tenants/{id}/conversations` | Conversations list |
| `GET` | `/api/admin/conversations/{id}/messages` | Conversation messages |
| `GET` | `/api/admin/search` | Full-text message search |
| `GET` | `/api/admin/ab-test-results` | A/B test performance |
| `GET` | `/api/admin/export/conversations` | Export CSV/JSON |

---

## Widget Embed Instructions

### Basic Embed (one line)
```html
<script src="https://tbm-chatbot-production.up.railway.app/widget/chat-widget.js" data-org="dcsc"></script>
```

### Features auto-configured from tenant settings:
- Brand colors (primary + text)
- Logo / avatar
- Welcome message
- Quick reply buttons
- Launcher teaser message
- Pre-chat form toggle
- Business hours / away mode
- CSAT survey trigger
- Escalation triggers
- Custom CSS overrides
- Language + placeholder text
- Widget position (left/right, offsets)

### Self-hosted embed
```html
<script src="https://your-domain.com/widget/chat-widget.js"
        data-org="your-slug"
        data-api="https://your-api.up.railway.app"></script>
```

---

## Cost Breakdown

Using GPT-4o-mini ($0.15/1M input, $0.60/1M output) + text-embedding-3-small ($0.02/1M tokens):

| Component | Cost |
|-----------|------|
| ~500 conversations | ~$1 in OpenAI API costs |
| Typical NFP (50 chats/day) | ~$3/month API |
| Neon Postgres (free tier) | $0/month |
| Railway (Hobby plan) | $5/month |
| **Total** | **~$8/month** |

**Comparison:** Intercom starts at $130/month. Zendesk at $89/month. Drift at $200/month.

---

## Project Structure

```
tbm-chatbot/
├── app/
│   ├── main.py              # FastAPI app, CORS, static mounts, startup
│   ├── config.py             # Environment variable config
│   ├── database.py           # Async Postgres + pgvector connection pool
│   ├── models.py             # SQLAlchemy models (8 tables)
│   ├── schemas.py            # Pydantic request/response schemas
│   ├── middleware/
│   │   └── auth.py           # Admin API key verification
│   ├── routers/
│   │   ├── chat.py           # Chat endpoint (RAG + auto-tag + suggestions)
│   │   ├── tenants.py        # Tenant CRUD + public config
│   │   ├── documents.py      # Document upload, bulk, crawl, reingest
│   │   ├── admin.py          # Analytics, search, insights, export, A/B test
│   │   ├── contact.py        # Contact form / human handoff
│   │   ├── feedback.py       # Thumbs up/down
│   │   ├── csat.py           # CSAT survey submissions
│   │   ├── articles.py       # KB article search endpoint
│   │   └── whatsapp.py       # WhatsApp Business API integration
│   └── services/
│       ├── rag.py            # RAG pipeline (embed → search → generate)
│       ├── embeddings.py     # OpenAI embedding service
│       ├── chunking.py       # Document chunking (~500 tokens)
│       ├── openai_client.py  # OpenAI API wrapper
│       ├── crawler.py        # URL scraping service
│       ├── email.py          # Email notification service
│       └── webhooks.py       # Webhook dispatch service
├── widget/
│   ├── chat-widget.js        # Embeddable widget (vanilla JS, ~1000 lines)
│   └── chat-widget.css       # Widget styles (brand-themed)
├── demo/
│   └── index.html            # Showcase demo page (DC Soccer Club)
├── admin/
│   ├── index.html            # Admin dashboard shell
│   ├── admin.js              # Admin SPA logic (~770 lines)
│   └── admin.css             # Admin styles (brand-themed)
├── data/
│   ├── raw/                  # Raw crawled website data
│   └── clean/                # 39+ cleaned markdown files for ingestion
├── docs/
│   ├── API-REFERENCE.md      # Complete API documentation
│   ├── CLIENT-PITCH.md       # Client-facing pitch document
│   └── PRODUCT-BROCHURE.md   # Feature brochure
├── tests/                    # Test suite
├── migrations/               # Database migrations
├── scripts/                  # Utility scripts
├── Dockerfile                # Production Docker image
├── docker-compose.yml        # Local development setup
└── requirements.txt          # Python dependencies
```

## License

Private — proprietary software.
