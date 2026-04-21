# TBM Chatbot

Multi-tenant RAG chatbot service for not-for-profit (NFP) organizations. Each client gets an isolated knowledge base, customizable chat widget, and usage tracking.

## Architecture

```
Client Website                    TBM Chatbot Service
┌──────────────┐                 ┌─────────────────────────────┐
│ Embedded     │  POST /api/chat │  FastAPI                    │
│ Chat Widget  │ ───────────────>│  ├─ Tenant Resolution       │
│ (vanilla JS) │                 │  ├─ Rate Limiting           │
│              │<─────────────── │  ├─ RAG Pipeline            │
│              │  JSON response  │  │  ├─ Embed query (OpenAI) │
└──────────────┘                 │  │  ├─ Vector search        │
                                 │  │  └─ Generate (GPT-4o-mini│
                                 │  └─ Conversation storage    │
                                 └──────────┬──────────────────┘
                                            │
                                 ┌──────────▼──────────────────┐
                                 │  Neon (Postgres + pgvector)  │
                                 │  ├─ tenants                  │
                                 │  ├─ documents                │
                                 │  ├─ document_chunks          │
                                 │  ├─ conversations            │
                                 │  └─ messages                 │
                                 └──────────────────────────────┘
```

**Stack:** Python 3.12, FastAPI, Neon/Postgres + pgvector, OpenAI API (GPT-4o-mini + text-embedding-3-small), vanilla JS widget

## Local Development

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- OpenAI API key

### Setup

```bash
# Clone and configure
cp .env.example .env
# Edit .env with your OPENAI_API_KEY

# Start services
docker compose up -d

# Or run locally against your own Postgres:
pip install -r requirements.txt
python scripts/migrate.py
python scripts/seed_demo.py
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`. Health check: `GET /health`.

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `DATABASE_URL` | Neon/Postgres connection string (asyncpg format) | Yes |
| `OPENAI_API_KEY` | OpenAI API key | Yes |
| `ADMIN_API_KEY` | Secret key for admin endpoints | Yes |
| `CORS_ORIGINS` | Comma-separated allowed origins | No (default: `http://localhost:3000`) |
| `LOG_LEVEL` | Logging level | No (default: `INFO`) |

## API Documentation

### Health Check
```
GET /health
→ { "status": "healthy", "service": "tbm-chatbot" }
```

### Chat
```
POST /api/chat
Content-Type: application/json

{
  "org_id": "my-nfp-slug",
  "message": "How can I volunteer?",
  "session_id": "sess_abc123"
}

→ {
  "response": "You can volunteer by...",
  "sources": [
    { "document_title": "Volunteer Guide", "source_url": "...", "relevance_score": 0.87 }
  ],
  "session_id": "sess_abc123",
  "conversation_id": "uuid"
}
```

### Tenant Management (requires `X-Admin-Key` header)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/tenants` | Create tenant |
| `GET` | `/api/tenants` | List all tenants |
| `GET` | `/api/tenants/{id}` | Get tenant details |
| `PATCH` | `/api/tenants/{id}` | Update tenant |
| `DELETE` | `/api/tenants/{id}` | Delete tenant |
| `GET` | `/api/tenants/public/{slug}` | Get public widget config (no auth) |

### Document Management (requires `X-Admin-Key` header)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/tenants/{id}/documents` | Upload document (auto-chunks & embeds) |
| `GET` | `/api/tenants/{id}/documents` | List documents |
| `GET` | `/api/tenants/{id}/documents/{doc_id}` | Get document status |
| `DELETE` | `/api/tenants/{id}/documents/{doc_id}` | Delete document and chunks |

### Admin (requires `X-Admin-Key` header)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/admin/usage` | Usage stats per tenant |
| `GET` | `/api/admin/tenants/{id}/conversations` | Conversation logs |
| `GET` | `/api/admin/conversations/{id}/messages` | Message history |

## Widget Integration

Add to any website:

```html
<script src="https://your-api-domain.com/widget/chat-widget.js" data-org="your-org-slug"></script>
```

The widget auto-loads branding config from the API. See `widget/README.md` for full details.

## Deployment (Docker)

```bash
# Build and run
docker compose up -d --build

# Run migrations (if not using docker-compose init scripts)
docker compose exec app python scripts/migrate.py

# Seed demo data
docker compose exec app python scripts/seed_demo.py
```

For production, point `DATABASE_URL` to your Neon instance and set a strong `ADMIN_API_KEY`.

## Cost Estimates

Approximate costs per 1,000 chat messages (assuming ~5 chunks retrieved per query):

| Component | Cost |
|---|---|
| GPT-4o-mini (chat) | ~$0.15 |
| text-embedding-3-small (query embeddings) | ~$0.002 |
| Neon (Free tier) | $0 for up to 0.5 GB storage |
| Neon (Pro) | From $19/mo for production workloads |

Document ingestion costs depend on volume — embedding 1,000 chunks costs ~$0.02.
