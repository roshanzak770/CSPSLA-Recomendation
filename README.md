# CloudSLA Recommender

An AI-powered cloud SLA recommendation engine. It ingests SLA documents from major cloud providers (AWS, Azure, GCP, Oracle, IBM), ranks them using a 6-stage pipeline (semantic search → TOPSIS → XGBoost), and explains recommendations in your desired language.

## Features

- Upload SLA PDFs, URLs, or paste raw text for any cloud provider
- Multi-language recommendation queries (18 languages supported)
- Side-by-side SLA comparison with metric trophies
- Real-time pricing data (AWS, Azure, GCP, Oracle, IBM)
- SLA change detection with email alerts and threshold rules
- RAG-based chat ("Ask your SLA documents a question")
- XGBoost re-ranking that improves with user feedback
- Auto-discovery of new SLA documents via web search

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, Tailwind CSS, TanStack Query, Framer Motion |
| Backend | FastAPI, SQLAlchemy, Celery |
| Database | PostgreSQL 15 |
| Vector Store | ChromaDB |
| Cache / Queue | Redis 7 |
| ML | XGBoost, sentence-transformers (multilingual-e5-base) |
| LLM | Groq (llama-3.1-8b) + HuggingFace |

---

## Prerequisites

Before starting, install:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)
- [Git](https://git-scm.com/)
- [Node.js 18+](https://nodejs.org/) — only needed for local frontend development without Docker
- [Python 3.11+](https://www.python.org/) — only needed for local backend development without Docker

---

## Quick Start (Docker — Recommended)

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/CloudSLA-Recommender.git
cd CloudSLA-Recommender
```

### 2. Create the environment file

```bash
cp .env.example .env
```

Open `.env` in any editor and fill in the required values (see [Environment Variables](#environment-variables) below).

### 3. Start all services

```bash
docker compose up --build
```

First build takes 5–10 minutes (downloads ML models). Subsequent starts are fast.

### 4. Open the app

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |

### 5. Stop the app

```bash
docker compose down
```

To also delete all stored data (database, vector store):

```bash
docker compose down -v
```

---

## Environment Variables

Copy `.env.example` to `.env` and set these values:

### Required

| Variable | Description | Example |
|---|---|---|
| `HF_TOKEN` | HuggingFace API token — needed to download embedding models | `hf_xxxxxxxxxxxx` |
| `GROQ_API_KEY` | Groq API key — powers the LLM explanation and RAG chat | `gsk_xxxxxxxxxxxx` |
| `SECRET_KEY` | Random string used for internal signing | `openssl rand -hex 32` |
| `ADMIN_API_KEY` | Key required to call `/api/admin/*` endpoints | any strong password |

### Database (pre-filled, change only if needed)

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://user:password@postgres:5432/cloudsla` | PostgreSQL connection string |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string |
| `CHROMA_HOST` | `chromadb` | ChromaDB container hostname |
| `CHROMA_PORT` | `8000` | ChromaDB port |

### Email Alerts (optional)

Only needed if you want to receive SLA threshold breach emails.

| Variable | Description |
|---|---|
| `SMTP_HOST` | SMTP server (default: `smtp.gmail.com`) |
| `SMTP_PORT` | SMTP port (default: `465`) |
| `SMTP_USER` | Your Gmail address |
| `SMTP_PASSWORD` | Gmail [App Password](https://myaccount.google.com/apppasswords) (not your regular password) |

### How to get API keys

**HuggingFace token:**
1. Create an account at https://huggingface.co
2. Go to Settings → Access Tokens → New Token
3. Select "Read" scope and copy the token

**Groq API key:**
1. Create an account at https://console.groq.com
2. Go to API Keys → Create API Key
3. Copy the key (starts with `gsk_`)

**Gmail App Password (for email alerts):**
1. Enable 2-factor authentication on your Google account
2. Go to https://myaccount.google.com/apppasswords
3. Create a new app password, copy the 16-character code

---

## Frontend Environment (optional)

The frontend reads one optional variable from `frontend/.env`:

```bash
# frontend/.env
VITE_ADMIN_KEY=your_admin_api_key_here
```

If not set, it defaults to `dev-admin-key`. Set this to match `ADMIN_API_KEY` in your backend `.env`.

---

## First Use — Ingest SLA Documents

The app ships with no SLA data. After starting:

1. Open http://localhost:3000
2. Go to **Add SLA Docs** in the sidebar
3. Choose one of three methods:
   - **Auto-fetch** — automatically discovers and ingests official SLA documents from cloud provider websites
   - **Search** — search DuckDuckGo for SLA PDFs and select which to ingest
   - **Upload** — drag and drop a PDF, paste a URL, or paste raw SLA text

After ingestion (takes 1–2 minutes per document), go to **Recommend** and try a query like:

> "I need 99.99% uptime with GDPR compliance in Europe"

---

## Running Services Individually

You can start only specific services if needed:

```bash
# Start only the core services (no background tasks)
docker compose up api frontend postgres redis chromadb

# Start with Celery workers (enables scheduled tasks and background jobs)
docker compose up api frontend postgres redis chromadb celery_worker celery_beat
```

### What each service does

| Service | Role |
|---|---|
| `api` | FastAPI backend on port 8000 |
| `frontend` | React app served by Nginx on port 3000 |
| `postgres` | Stores providers, documents, metrics, feedback, alerts |
| `redis` | Celery task queue and result backend |
| `chromadb` | Vector store for semantic SLA search |
| `celery_worker` | Runs background tasks (ingest, retrain, pricing refresh) |
| `celery_beat` | Schedules recurring tasks (see schedule below) |

### Scheduled tasks

| Task | Schedule | Description |
|---|---|---|
| `refresh_pricing` | Daily 02:00 UTC | Fetches live pricing from AWS, Azure, GCP, Oracle, IBM |
| `refresh_all_sla_documents` | Sunday 02:00 UTC | Re-fetches SLA PDFs and detects changes |
| `discover_and_ingest_new_slas` | Monday 03:00 UTC | Web-searches for new SLA documents and auto-ingests them |
| `retrain_xgboost` | Tuesday 04:00 UTC | Retrains the XGBoost ranking model from accumulated feedback |

---

## Local Development (without Docker)

### Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp ../.env.example ../.env
# Edit .env with your values

# Run database migrations (requires a running PostgreSQL instance)
# Then start the API
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Create frontend env file
echo "VITE_ADMIN_KEY=dev-admin-key" > .env

# Start dev server (proxies /api to localhost:8000)
npm run dev
```

Frontend will be available at http://localhost:5173

---

## Project Structure

```
CloudSLA-Recommender/
├── backend/
│   ├── app/
│   │   ├── api/routes/        # FastAPI route handlers
│   │   ├── core/              # Config, schemas
│   │   ├── db/                # Database session
│   │   ├── models/            # SQLAlchemy models
│   │   ├── services/          # Business logic (ranking, ingestion, LLM, pricing)
│   │   └── tasks/             # Celery background tasks
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/               # API client
│   │   ├── components/        # Reusable UI components
│   │   └── pages/             # Page components
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
├── .env.example               # Template — copy to .env and fill in values
└── README.md
```

---

## API Reference

Full interactive docs available at http://localhost:8000/docs when the app is running.

Key endpoints:

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/query` | Run a recommendation query |
| `GET` | `/api/compare` | Compare providers side by side |
| `POST` | `/api/ask` | Chat with SLA documents (RAG) |
| `POST` | `/api/feedback` | Submit thumbs up/down feedback |
| `POST` | `/api/admin/upload` | Upload a SLA PDF |
| `POST` | `/api/admin/ingest-url` | Ingest SLA from a URL |
| `GET` | `/api/admin/feedback/stats` | View feedback and model training status |
| `POST` | `/api/admin/retrain-now` | Manually trigger XGBoost retraining |
| `GET` | `/api/pricing/live` | Get latest cached pricing data |
| `GET` | `/api/alerts` | Get SLA change alerts |

Admin endpoints require the `X-Admin-Key` header matching `ADMIN_API_KEY` in your `.env`.

---

## Troubleshooting

**Containers keep restarting:**
Check logs: `docker compose logs api`
Most common cause: missing or incorrect values in `.env`.

**"No SLA documents ingested" on first query:**
Go to Add SLA Docs and run Auto-fetch, or upload a document manually.

**Embedding model download is slow:**
The `intfloat/multilingual-e5-base` model (~1.1 GB) is downloaded from HuggingFace on first start. This is cached in `~/.cache/huggingface` and only downloads once.

**Out of memory on 8 GB RAM:**
Skip the Celery workers to reduce memory usage:
```bash
docker compose up api frontend postgres redis chromadb
```

**Port conflict:**
If ports 3000, 8000, 5432, 6379, or 8001 are in use, edit the `ports` section of `docker-compose.yml`.
