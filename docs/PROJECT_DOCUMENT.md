# CloudSLA Recommender — Complete Project Document

> NLP-Based Cloud Service Provider Recommendation System using SLA Documents
> Version: 1.0
> Status: Planning / Pre-Development

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Problem Statement](#2-problem-statement)
3. [Core User Flow](#3-core-user-flow)
4. [Features](#4-features)
5. [System Architecture](#5-system-architecture)
6. [Tech Stack](#6-tech-stack)
7. [Ranking Pipeline](#7-ranking-pipeline)
8. [SLA Document Processing Pipeline](#8-sla-document-processing-pipeline)
9. [Cost Analysis Module](#9-cost-analysis-module)
10. [User Feedback Loop](#10-user-feedback-loop)
11. [Multi-Language Support](#11-multi-language-support)
12. [SLA Alert System](#12-sla-alert-system)
13. [AI Models](#13-ai-models)
14. [Database Schema](#14-database-schema)
15. [API Endpoints](#15-api-endpoints)
16. [Frontend UI Specification](#16-frontend-ui-specification)
17. [Hardware Requirements](#17-hardware-requirements)
18. [Environment Variables](#18-environment-variables)
19. [Docker Setup](#19-docker-setup)
20. [Build Order](#20-build-order)
21. [Known Limitations](#21-known-limitations)

---

## 1. Project Overview

**Project Name:** CloudSLA Recommender
**Type:** Full-Stack AI Application
**Purpose:** Recommend and rank Cloud Service Providers (CSPs) based on user natural language input, using real publicly available SLA (Service Level Agreement) documents as the knowledge base.
**Rating:** 9/10 (Production-grade architecture for a student/bootcamp project)
**Cost:** $0 — 100% open-source, zero paid APIs or services

---

## 2. Problem Statement

Choosing a cloud provider (AWS, Azure, GCP, Oracle Cloud, IBM Cloud) requires reading dense, technical SLA documents. Most users cannot interpret these documents. Key pain points:

- SLA documents are 20–50 page PDFs written in legal/technical language
- No tool exists that compares providers based on natural language requirements
- Users cannot easily map their requirements (uptime, region, compliance) to SLA clauses
- SLAs change over time with no notification to affected users
- Cost vs SLA quality trade-off is never presented together

This system lets a user describe their needs in plain language and returns ranked CSP recommendations with scores, cost estimates, and clause-level explanations — all sourced from actual SLA documents.

---

## 3. Core User Flow

```
User Input (any language, plain text):
"I'm building a hospital app, data must stay in Germany,
 need 99.99% uptime, and recovery within 2 hours."

        │
        ▼

Step 1: Detect language → translate to English if needed
Step 2: LLM extracts structured requirements from query
Step 3: Semantic search retrieves relevant SLA clauses
Step 4: LLM extracts metrics from retrieved SLA text
Step 5: TOPSIS scores providers on objective criteria
Step 6: XGBoost re-ranks using learned user preferences
Step 7: LLM generates human-readable explanation per provider
Step 8: Cost API adds live pricing data
Step 9: Translate response back to user's language

        │
        ▼

System Output:
#1 Azure  — 92/100 — $340/mo — "Meets all requirements. Business Critical
                                 tier guarantees 99.995% uptime in Germany
                                 North with 1hr RTO. HIPAA BAA available."

#2 GCP    — 74/100 — $210/mo — "Uptime 99.95% slightly below your 99.99%
                                 requirement. Frankfurt region available.
                                 RTO of 2hrs meets your requirement."

#3 AWS    — 61/100 — $390/mo — "RTO of 4hrs exceeds your 2hr requirement
                                 on standard tier. Multi-AZ deployment
                                 needed to meet RTO — increases cost."
```

---

## 4. Features

### 4.1 Core Features

| Feature | Description |
|---|---|
| Natural Language Query | User types in plain language, no technical jargon required |
| SLA Document RAG | PDFs from AWS/Azure/GCP ingested, chunked, embedded, stored in vector DB |
| Multi-Criteria Ranking | TOPSIS + XGBoost LambdaMART ranking pipeline |
| LLM Re-ranking | LLM reads top results and adds clause-level reasoning |
| Comparison Mode | Side-by-side comparison of 2–3 providers on extracted SLA criteria |
| SHAP Explainability | Explains exactly which criteria drove each provider's score |
| Compliance Filter | Tags providers by GDPR, HIPAA, SOC2, ISO27001 from SLA content |

### 4.2 Extended Features

| Feature | Description |
|---|---|
| Cost Analysis | Live pricing from AWS/Azure/GCP public pricing APIs combined with SLA score |
| User Feedback Loop | Thumbs up/down + click signals retrain XGBoost model automatically |
| Multi-Language Support | Queries in Arabic, French, German, Spanish, Chinese auto-translated |
| SLA Alert System | Weekly re-fetch detects changes, alerts admins and affected users |
| Weight Adjustment | Users adjust ranking criteria weights via UI sliders |
| Query History | Saved queries and comparisons per user account |

---

## 5. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (React + TypeScript)         │
│   Search  │  Results  │  Cost View  │  Compare  │ Alerts │
└──────────────────────────┬──────────────────────────────┘
                           │ REST API (HTTP/JSON)
┌──────────────────────────▼──────────────────────────────┐
│                     BACKEND (FastAPI)                    │
│                                                          │
│  /query  → LangDetect → LibreTranslate → RAG → Rank     │
│  /feedback → Store signal → Trigger XGBoost retrain     │
│  /cost     → AWS / Azure / GCP pricing APIs             │
│  /alerts   → SLA diff engine → Notify users             │
└──────────┬───────────────────────────┬──────────────────┘
           │                           │
    ┌──────▼──────┐           ┌────────▼──────┐
    │  ChromaDB   │           │  PostgreSQL   │
    │  (SLA       │           │  (users,      │
    │   vectors)  │           │   feedback,   │
    └─────────────┘           │   alerts,     │
                              │   queries)    │
                              └───────────────┘
                                     │
                      ┌──────────────▼──────────────┐
                      │      Celery + Redis           │
                      │  - XGBoost retraining         │
                      │  - Weekly SLA re-fetch        │
                      │  - Alert email dispatch       │
                      └──────────────────────────────┘
                                     │
                      ┌──────────────▼──────────────┐
                      │   HuggingFace Inference API  │
                      │  - Llama-3.1-8B (extraction) │
                      │  - Qwen2.5-7B (reasoning)    │
                      └──────────────────────────────┘
```

---

## 6. Tech Stack

### 6.1 Backend

| Layer | Technology | Version | License | Purpose |
|---|---|---|---|---|
| API Framework | FastAPI | 0.111+ | MIT | REST API server |
| NLP / RAG | LangChain | 0.2+ | MIT | Document loading, chunking, retrieval |
| Vector DB | ChromaDB | 0.5+ | Apache 2.0 | Store and search SLA embeddings |
| Embeddings | sentence-transformers | 3.0+ | Apache 2.0 | Convert text to vectors |
| LLM (extraction) | HF Inference API — Llama-3.1-8B | — | Meta Llama | JSON extraction from SLA text |
| LLM (reasoning) | HF Inference API — Qwen2.5-7B | — | Apache 2.0 | Query understanding, ranking explanation |
| ML Ranking | XGBoost | 2.0+ | Apache 2.0 | LambdaMART learning-to-rank |
| Explainability | SHAP | 0.45+ | MIT | Feature importance per prediction |
| PDF Parsing | PyMuPDF + pdfplumber | latest | AGPL / MIT | Extract text from SLA PDFs |
| Translation | LibreTranslate | latest | AGPL-3.0 | Self-hosted, free translation |
| Lang Detection | langdetect | 1.0+ | Apache 2.0 | Detect input language |
| Task Queue | Celery | 5.3+ | BSD | Async retraining and scheduling |
| Message Broker | Redis | 7+ | BSD | Celery broker and result backend |
| Database | PostgreSQL | 15+ | PostgreSQL | Users, feedback, alerts, queries |
| ORM | SQLAlchemy | 2.0+ | MIT | Database models and queries |
| Validation | Pydantic | 2.0+ | MIT | Data validation and serialization |

### 6.2 Frontend

| Layer | Technology | Version | License | Purpose |
|---|---|---|---|---|
| Framework | React + TypeScript | 18+ | MIT | UI framework |
| UI Components | shadcn/ui | latest | MIT | Pre-built accessible components |
| Charts | Recharts | 2.0+ | MIT | Radar chart, bar chart for SLA comparison |
| State Management | React Query + Zustand | latest | MIT | Server state and client state |
| HTTP Client | Axios | 1.0+ | MIT | API calls to FastAPI backend |
| Forms | React Hook Form | 7.0+ | MIT | Query input and settings forms |

### 6.3 Infrastructure

| Component | Technology | Purpose |
|---|---|---|
| Containerization | Docker + Docker Compose | Run all services together |
| Web Server | Uvicorn | ASGI server for FastAPI |
| Email | SMTP + Gmail | Free alert email dispatch |

---

## 7. Ranking Pipeline

### Overview

```
User Query (natural language)
       │
       ▼
Stage 1: Query Understanding  (Qwen2.5-7B via HF API)
       │
       ▼
Stage 2: Semantic Retrieval   (multilingual-e5-base + ChromaDB)
       │
       ▼
Stage 3: Metrics Extraction   (Llama-3.1-8B via HF API)
       │
       ▼
Stage 4: TOPSIS Scoring       (Python / NumPy — local)
       │
       ▼
Stage 5: XGBoost Re-ranking   (XGBoost LambdaMART — local)
       │
       ▼
Stage 6: LLM Explanation      (Qwen2.5-7B via HF API)
       │
       ▼
Final Ranked List with Scores + Explanations + Cost
```

### Stage 1 — Query Understanding

```python
# Input: raw user text (any language, already translated to English)
# Output: structured JSON

{
  "uptime_required_pct": 99.99,
  "rto_hours": 2,
  "rpo_hours": null,
  "region": "eu-west",
  "country": "Germany",
  "compliance": ["HIPAA", "GDPR"],
  "category": "database",
  "sensitivity": "HIGH",
  "budget_usd_monthly": null
}
```

### Stage 2 — Semantic Retrieval

- Embed user query using `intfloat/multilingual-e5-base`
- Search ChromaDB for top-5 SLA chunks per provider using cosine similarity
- Returns relevant SLA text excerpts per CSP

### Stage 3 — SLA Metrics Extraction

```python
# LLM reads retrieved SLA chunks and extracts per provider:

{
  "provider": "Azure",
  "uptime_sla_pct": 99.995,
  "rto_hours": 1.0,
  "rpo_hours": 0.5,
  "support_response_min": 15,
  "penalty_credit_pct": 30,
  "regions": ["Germany North", "Germany West Central"],
  "compliance": ["GDPR", "HIPAA", "SOC2", "ISO27001"],
  "source_clause": "Azure SQL Business Critical tier guarantees..."
}
```

### Stage 4 — TOPSIS Scoring

TOPSIS (Technique for Order of Preference by Similarity to Ideal Solution) handles multi-criteria ranking with configurable weights.

**Default Criteria Weights (user-adjustable via UI):**

| Criterion | Weight | Type |
|---|---|---|
| uptime_sla_pct | 0.30 | Benefit (higher = better) |
| rto_hours | 0.20 | Cost (lower = better) |
| rpo_hours | 0.15 | Cost (lower = better) |
| support_response_min | 0.15 | Cost (lower = better) |
| penalty_credit_pct | 0.10 | Benefit (higher = better) |
| region_coverage | 0.10 | Benefit (higher = better) |

**TOPSIS Formula:**
```
1. Build weighted normalized decision matrix:
   v_ij = w_j × (x_ij / sqrt(Σ x_ij²))

2. Identify Ideal Best (A+) and Ideal Worst (A-):
   A+ = max for benefit criteria, min for cost criteria
   A- = min for benefit criteria, max for cost criteria

3. Calculate Euclidean distance from A+ and A-:
   D+_i = sqrt(Σ (v_ij - A+_j)²)
   D-_i = sqrt(Σ (v_ij - A-_j)²)

4. Relative Closeness Score (0 to 1, higher = better):
   C_i = D-_i / (D+_i + D-_i)
```

### Stage 5 — XGBoost LambdaMART Re-ranking

**Model Configuration:**
```python
xgb.XGBRanker(
    objective="rank:ndcg",
    learning_rate=0.1,
    n_estimators=100,
    max_depth=6
)
```

**Input Features per (query, provider) pair:**
```
cosine_similarity_score     # from vector search
topsis_score                # from Stage 4
uptime_delta                # required_uptime - actual_uptime
rto_meets_requirement       # binary: 0 or 1
region_match                # binary: 0 or 1
compliance_overlap_pct      # % of required certs provider has
cost_efficiency_score       # 1 - (cost / max_cost)
query_category_encoded      # database=0, compute=1, storage=2 etc.
```

**Cold Start Strategy:**
- Day 1: TOPSIS scores used as initial training labels
- Retrains every 100 new user feedback entries via Celery async task
- Model improves continuously as users interact

### Stage 6 — Final Score

```
final_score = (0.50 × topsis_score) +
              (0.20 × cosine_similarity) +
              (0.30 × llm_reasoning_score)
```

---

## 8. SLA Document Processing Pipeline

### 8.1 SLA Document Sources (All Free, Public)

```
AWS:    https://aws.amazon.com/legal/service-level-agreements/
Azure:  https://azure.microsoft.com/en-us/support/legal/sla/
GCP:    https://cloud.google.com/terms/sla
Oracle: https://www.oracle.com/cloud/sla/
IBM:    https://www.ibm.com/support/customer/csol/terms/
```

### 8.2 Ingestion Pipeline

```
SLA PDF
   │
   ▼
PyMuPDF loader         → raw text extraction from PDF pages
   │
   ▼
LangChain splitter     → RecursiveCharacterTextSplitter
                          chunk_size=500, chunk_overlap=50
   │
   ▼
multilingual-e5-base   → convert each chunk to 768-dim vector
   │
   ▼
ChromaDB               → store vectors with metadata:
                          {provider, source_file, page_number, chunk_id}
```

### 8.3 Chunking Strategy

```python
splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    separators=["\n\n", "\n", ".", " "]
)
```

Each chunk stored with metadata:
```json
{
  "provider": "AWS",
  "source_file": "aws_ec2_sla.pdf",
  "page_number": 12,
  "chunk_id": "aws_chunk_0042",
  "ingested_at": "2026-04-01T10:00:00Z"
}
```

---

## 9. Cost Analysis Module

### 9.1 Data Sources (All Free, No Auth Required)

```python
AWS_PRICING   = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/index.json"
AZURE_PRICING = "https://prices.azure.com/api/retail/prices"
GCP_PRICING   = "https://cloudpricingcalculator.appspot.com/static/data/pricelist.json"
```

### 9.2 Combined Value Score Formula

```
cost_efficiency_score = 1 - (provider_cost / max_cost_across_providers)
value_score = (sla_score × 0.60) + (cost_efficiency_score × 0.40)
```

### 9.3 Refresh Schedule

- Pricing data refreshed daily via Celery Beat
- Cached in PostgreSQL with `fetched_at` timestamp

---

## 10. User Feedback Loop

### 10.1 Feedback Signal Types

| Signal | Weight | How Collected |
|---|---|---|
| clicked_provider | 0.3 | User clicks on a provider result |
| accepted_recommendation | 1.0 | User proceeds after viewing recommendation |
| thumbs_up | 1.5 | Explicit positive button click |
| thumbs_down | -1.5 | Explicit negative button click |
| ignored_top_result | -0.5 | Top result not clicked, lower one chosen |

### 10.2 Retraining Trigger

```
Every 100 new feedback entries:
   → Celery async task fires
   → Build new feature matrix from feedback data
   → Retrain XGBoost LambdaMART
   → Replace model in memory
   → Log model version to PostgreSQL
```

### 10.3 Storage Schema

```sql
feedback (
  id          UUID PRIMARY KEY,
  query_id    UUID REFERENCES queries(id),
  provider_id UUID REFERENCES providers(id),
  signal_type VARCHAR(50),
  weight      FLOAT,
  user_id     UUID REFERENCES users(id),
  created_at  TIMESTAMP
)
```

---

## 11. Multi-Language Support

### 11.1 Supported Languages

| Language | Code |
|---|---|
| English | en |
| Arabic | ar |
| French | fr |
| German | de |
| Spanish | es |
| Chinese | zh |

### 11.2 Processing Flow

```
Step 1: Detect language       → langdetect library
Step 2: Translate to English  → LibreTranslate (self-hosted Docker)
Step 3: Run NLP pipeline      → always in English internally
Step 4: Translate response    → LLM prompt: "Respond in {detected_language}"
```

### 11.3 LibreTranslate Docker Setup

```bash
docker run -ti --rm -p 5000:5000 libretranslate/libretranslate
```

```python
import requests

def translate(text: str, source: str, target: str) -> str:
    r = requests.post("http://localhost:5000/translate", json={
        "q": text, "source": source, "target": target
    })
    return r.json()["translatedText"]
```

### 11.4 Multilingual Embeddings

Use `intfloat/multilingual-e5-base` instead of `all-MiniLM-L6-v2`:
- Supports 100+ languages
- 278MB model size
- Runs locally on CPU, no GPU needed
- Arabic query → English SLA chunks found correctly via cross-lingual similarity

---

## 12. SLA Alert System

### 12.1 Detection Process

```
Celery Beat (runs every Sunday 02:00 local time):
  1. Re-fetch SLA PDFs from CSP documentation pages
  2. Re-embed document chunks
  3. Diff: cosine_similarity(new_chunk, old_chunk) < 0.95 → CHANGED
  4. LLM extracts human-readable description of change
  5. Classify severity: LOW | MEDIUM | HIGH | CRITICAL
  6. Store alert in PostgreSQL
  7. Notify admin via email
  8. Notify users whose saved queries are affected
```

### 12.2 Severity Classification

| Severity | Trigger |
|---|---|
| CRITICAL | Uptime SLA reduced OR compliance certification removed |
| HIGH | RTO/RPO increased OR penalty credit reduced |
| MEDIUM | Region removed OR support tier downgraded |
| LOW | Minor wording changes, non-metric updates |
| POSITIVE | Any improvement to SLA terms |

### 12.3 Alert Schema

```sql
sla_alerts (
  id              UUID PRIMARY KEY,
  provider_id     UUID REFERENCES providers(id),
  change_type     VARCHAR(50),   -- UPTIME_REDUCED, PENALTY_REDUCED etc.
  old_value       TEXT,
  new_value       TEXT,
  affected_clause TEXT,          -- exact SLA text excerpt
  severity        VARCHAR(20),   -- LOW, MEDIUM, HIGH, CRITICAL
  detected_at     TIMESTAMP,
  notified_at     TIMESTAMP
)

user_alerts (
  id         UUID PRIMARY KEY,
  user_id    UUID REFERENCES users(id),
  alert_id   UUID REFERENCES sla_alerts(id),
  read_at    TIMESTAMP
)
```

### 12.4 Email Setup (Free via Gmail SMTP)

```python
import smtplib
from email.mime.text import MIMEText

def send_alert_email(to: str, subject: str, body: str):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"]    = "cloudsla.alerts@gmail.com"
    msg["To"]      = to
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login("cloudsla.alerts@gmail.com", "YOUR_APP_PASSWORD")
        s.send_message(msg)
```

---

## 13. AI Models

### 13.1 Model Router

| Task | Model | Runs Where |
|---|---|---|
| SLA JSON extraction | `meta-llama/Llama-3.1-8B-Instruct` | HF Inference API |
| Query understanding | `Qwen/Qwen2.5-7B-Instruct` | HF Inference API |
| Ranking explanation | `Qwen/Qwen2.5-7B-Instruct` | HF Inference API |
| Multilingual reasoning | `Qwen/Qwen2.5-7B-Instruct` | HF Inference API |
| Text embeddings | `intfloat/multilingual-e5-base` | Local CPU |
| TOPSIS scoring | NumPy | Local CPU |
| XGBoost ranking | XGBoost | Local CPU |
| SHAP explanations | SHAP library | Local CPU |

### 13.2 Why These Models

**Llama-3.1-8B-Instruct** — SLA Extraction:
- Best-in-class at following strict JSON format instructions
- Does not hallucinate extra fields
- Available free on HF with access approval

**Qwen2.5-7B-Instruct** — Reasoning + Multilingual:
- Trained natively on Arabic, Chinese, Japanese, Korean, French, German, Spanish
- Significantly better multilingual quality than Llama
- Strong comparative reasoning for ranking explanations
- Apache 2.0 license — fully open source, no approval needed

**intfloat/multilingual-e5-base** — Embeddings:
- 100+ language support
- 278MB — runs fine on CPU
- Cross-lingual retrieval: Arabic query finds English SLA chunks correctly

### 13.3 HuggingFace Integration

```python
from huggingface_hub import InferenceClient

class LLMRouter:
    def __init__(self, hf_token: str):
        self.extractor = InferenceClient(
            model="meta-llama/Llama-3.1-8B-Instruct",
            token=hf_token
        )
        self.reasoner = InferenceClient(
            model="Qwen/Qwen2.5-7B-Instruct",
            token=hf_token
        )

    def extract_sla_metrics(self, sla_text: str) -> dict:
        response = self.extractor.chat_completion(
            messages=[{"role": "user", "content": f"""
                Extract SLA metrics from this text. Return ONLY valid JSON:
                {{
                  "uptime_sla_pct": float,
                  "rto_hours": float,
                  "rpo_hours": float,
                  "support_response_min": int,
                  "penalty_credit_pct": int,
                  "regions": ["string"],
                  "compliance": ["string"],
                  "source_clause": "exact quote"
                }}
                Text: {sla_text}
            """}],
            max_tokens=500,
            temperature=0
        )
        return response.choices[0].message.content

    def understand_query(self, query: str) -> dict:
        response = self.reasoner.chat_completion(
            messages=[{"role": "user", "content": f"""
                Extract cloud requirements from this user query. Return JSON:
                {{
                  "uptime_required_pct": float or null,
                  "rto_hours": float or null,
                  "region": "string or null",
                  "compliance": ["string"],
                  "category": "database|compute|storage|network",
                  "sensitivity": "LOW|MEDIUM|HIGH"
                }}
                Query: {query}
            """}],
            max_tokens=300,
            temperature=0
        )
        return response.choices[0].message.content

    def generate_explanation(self, query: str, providers: list, lang: str) -> str:
        response = self.reasoner.chat_completion(
            messages=[{"role": "user", "content": f"""
                User requirement: {query}
                Ranked providers: {providers}
                Explain the ranking citing specific SLA clauses.
                Respond in {lang}.
            """}],
            max_tokens=600,
            temperature=0.3
        )
        return response.choices[0].message.content
```

---

## 14. Database Schema

```sql
-- Cloud Service Providers
providers (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        VARCHAR(100) NOT NULL,     -- "AWS", "Azure", "GCP"
  website     VARCHAR(255),
  logo_url    VARCHAR(255),
  created_at  TIMESTAMP DEFAULT NOW()
)

-- SLA Documents
sla_documents (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id  UUID REFERENCES providers(id),
  version      VARCHAR(50),
  file_path    VARCHAR(255),
  file_hash    VARCHAR(64),              -- SHA256 for change detection
  ingested_at  TIMESTAMP DEFAULT NOW()
)

-- SLA Document Chunks
sla_chunks (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id  UUID REFERENCES sla_documents(id),
  chunk_text   TEXT NOT NULL,
  embedding_id VARCHAR(100),            -- ChromaDB reference ID
  page_number  INTEGER,
  chunk_index  INTEGER
)

-- Extracted SLA Metrics per Provider
sla_metrics (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id          UUID REFERENCES providers(id),
  document_id          UUID REFERENCES sla_documents(id),
  uptime_sla_pct       FLOAT,
  rto_hours            FLOAT,
  rpo_hours            FLOAT,
  support_response_min INTEGER,
  penalty_credit_pct   INTEGER,
  regions              TEXT[],
  compliance           TEXT[],
  source_clause        TEXT,
  extracted_at         TIMESTAMP DEFAULT NOW()
)

-- User Queries
queries (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID REFERENCES users(id),
  raw_input     TEXT NOT NULL,
  detected_lang VARCHAR(10),
  parsed_json   JSONB,
  created_at    TIMESTAMP DEFAULT NOW()
)

-- Rankings per Query
rankings (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_id      UUID REFERENCES queries(id),
  provider_id   UUID REFERENCES providers(id),
  topsis_score  FLOAT,
  xgb_score     FLOAT,
  llm_score     FLOAT,
  final_score   FLOAT,
  cost_usd      FLOAT,
  value_score   FLOAT,
  explanation   TEXT,
  rank_position INTEGER,
  created_at    TIMESTAMP DEFAULT NOW()
)

-- User Feedback
feedback (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_id     UUID REFERENCES queries(id),
  provider_id  UUID REFERENCES providers(id),
  signal_type  VARCHAR(50),
  weight       FLOAT,
  user_id      UUID REFERENCES users(id),
  created_at   TIMESTAMP DEFAULT NOW()
)

-- SLA Change Alerts
sla_alerts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id     UUID REFERENCES providers(id),
  change_type     VARCHAR(50),
  old_value       TEXT,
  new_value       TEXT,
  affected_clause TEXT,
  severity        VARCHAR(20),
  detected_at     TIMESTAMP DEFAULT NOW(),
  notified_at     TIMESTAMP
)

-- User Alert Subscriptions
user_alerts (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID REFERENCES users(id),
  alert_id   UUID REFERENCES sla_alerts(id),
  read_at    TIMESTAMP
)

-- Users
users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email         VARCHAR(255) UNIQUE NOT NULL,
  language_pref VARCHAR(10) DEFAULT 'en',
  is_admin      BOOLEAN DEFAULT FALSE,
  created_at    TIMESTAMP DEFAULT NOW()
)

-- Pricing Cache
pricing_cache (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id UUID REFERENCES providers(id),
  service     VARCHAR(100),
  region      VARCHAR(100),
  price_usd   FLOAT,
  fetched_at  TIMESTAMP DEFAULT NOW()
)
```

---

## 15. API Endpoints

### Query & Recommendations

```
POST /api/query
  Body:    { "text": "I need 99.99% uptime for a hospital app in Germany" }
  Returns: { query_id, rankings: [{provider, score, cost, explanation}] }

GET  /api/compare?providers=AWS,Azure,GCP&query_id=xxx
  Returns: side-by-side SLA metrics for selected providers
```

### Providers & SLA

```
GET  /api/providers
  Returns: list of all CSPs with metadata

GET  /api/providers/{id}/sla
  Returns: latest extracted SLA metrics for a provider

GET  /api/providers/{id}/cost
  Returns: current pricing from live API
```

### Feedback

```
POST /api/feedback
  Body:    { "query_id": "...", "provider_id": "...", "signal": "thumbs_up" }
  Returns: { "success": true }
```

### Alerts

```
GET  /api/alerts
  Returns: all SLA alerts (admin only, ordered by severity)

GET  /api/alerts/user
  Returns: alerts affecting current user's saved queries

POST /api/alerts/subscribe
  Body:    { "provider_ids": ["aws_id", "azure_id"] }
  Returns: { "subscribed": true }
```

### Admin

```
POST /api/admin/ingest
  Body:    { "provider": "AWS", "pdf_path": "/path/to/aws_sla.pdf" }
  Returns: { "chunks_created": 142, "embedding_time_sec": 8.3 }

POST /api/admin/refresh-sla
  Triggers: Celery task to re-fetch and diff all SLA documents
  Returns:  { "task_id": "celery_task_id" }
```

---

## 16. Frontend UI Specification

### 16.1 Pages

```
/               → Home / Search page
/results        → Ranked results for a query
/compare        → Side-by-side provider comparison
/provider/{id}  → Single provider SLA detail page
/alerts         → SLA change alerts (admin + user)
/history        → Saved queries and past comparisons
/settings       → Language preference, alert subscriptions, weight sliders
```

### 16.2 Search Page

```
┌──────────────────────────────────────────────────────────┐
│  CloudSLA Recommender                                     │
│                                                           │
│  "Describe what you need in plain language"              │
│  ┌─────────────────────────────────────────────────┐    │
│  │  I need a cloud database with 99.99% uptime...  │    │
│  └─────────────────────────────────────────────────┘    │
│                    [ Find Best Provider ]                 │
│                                                           │
│  Adjust Priorities:                                       │
│  Uptime    ████████░░  80%                               │
│  Cost      ████░░░░░░  40%                               │
│  Support   █████░░░░░  50%                               │
└──────────────────────────────────────────────────────────┘
```

### 16.3 Results Page

```
┌──────────────────────────────────────────────────────────┐
│  Results for: "hospital app, 99.99% uptime, Germany"     │
├──────────────────────────────────────────────────────────┤
│  #1  Azure    ████████████████████  92/100  $340/mo      │
│      ✅ Uptime  ✅ RTO  ✅ Germany  ✅ HIPAA  ✅ GDPR    │
│      "Business Critical tier guarantees 99.995%..."      │
│                                        [Details] [Select]│
├──────────────────────────────────────────────────────────┤
│  #2  GCP      ████████████████      74/100  $210/mo      │
│      ⚠️ Uptime  ✅ RTO  ✅ Germany  ✅ HIPAA  ✅ GDPR    │
���      "Uptime 99.95% slightly below 99.99% requirement"   │
│                                        [Details] [Select]│
├──────────────────────────────────────────────────────────┤
│  #3  AWS      ████████████          61/100  $390/mo      │
│      ✅ Uptime  ❌ RTO  ✅ Germany  ✅ HIPAA  ✅ GDPR    │
│      "RTO of 4hrs exceeds your 2hr requirement"          │
│                                        [Details] [Select]│
└──────────────────────────────────────────────────────────┘
              Was this helpful?  👍  👎
```

### 16.4 Comparison Page

```
┌─────────────────┬─────────────┬─────────────┬─────────────┐
│ Criterion       │ Azure       │ GCP         │ AWS         │
├─────────────────┼─────────────┼─────────────┼─────────────┤
│ Uptime SLA      │ 99.995% ✅  │ 99.95%  ⚠️  │ 99.99%  ✅  │
│ RTO             │ 1 hr    ✅  │ 2 hrs   ✅  │ 4 hrs   ❌  │
│ RPO             │ 30 min  ✅  │ 1 hr    ✅  │ 1 hr    ✅  │
│ Support         │ 15 min  ✅  │ 1 hr    ✅  │ 1 hr    ✅  │
│ Penalty Credit  │ 30%     ✅  │ 25%     ✅  │ 25%     ✅  │
│ GDPR            │ ✅          │ ✅          │ ✅          │
│ HIPAA           │ ✅          │ ✅          │ ✅          │
│ Monthly Cost    │ $340        │ $210        │ $390        │
│ Overall Score   │ 92/100      │ 74/100      │ 61/100      │
└─────────────────┴─────────────┴─────────────┴─────────────┘
```

### 16.5 Alert Dashboard

```
┌──────────────────────────────────────────────────────────┐
│  SLA Change Alerts                        🔴 2 Critical  │
├──────────────────────────────────────────────────────────┤
│  🔴 Azure  — Penalty credit dropped 30%→10%  (eu-west)   │
│     Detected: 2 days ago  │  Affects: 14 users           │
│                                                           │
│  🟡 AWS    — RTO increased 4hr→6hr (ap-southeast)        │
│     Detected: 5 days ago  │  Affects: 3 users            │
│                                                           │
│  🟢 GCP    — Uptime improved 99.95%→99.99% (eu-west3)    │
│     Detected: 1 week ago  │  Affects: 8 users            │
└──────────────────────────────────────────────────────────┘
```

---

## 17. Hardware Requirements

### Minimum (4GB RAM, No GPU)

```
CPU:     4 cores
RAM:     4GB
GPU:     None
Storage: 20GB free
```

Possible because: HuggingFace API handles all LLM inference remotely.
Local services: ChromaDB + PostgreSQL + Redis + FastAPI + embeddings model only.

### Recommended (Development)

```
CPU:     8 cores
RAM:     8–16GB
GPU:     Not required
Storage: 50GB SSD
Internet: Required (HF API calls)
```

### RAM Breakdown (All Services Running)

```
Service                    RAM Usage
──────────────────────────────────────
multilingual-e5-base       ~300MB
ChromaDB                   ~300MB
LibreTranslate (Docker)    ~2GB
PostgreSQL                 ~256MB
Redis                      ~128MB
Celery workers (x2)        ~512MB
FastAPI                    ~256MB
React dev server           ~512MB
──────────────────────────────────────
TOTAL                      ~4.3GB
```

### Storage Breakdown

```
Item                           Size
────────────────────────────────────
multilingual-e5-base model    278MB
LibreTranslate Docker image   ~1GB
ChromaDB data                 ~200MB
PostgreSQL data               ~500MB
Docker images (all services)  ~5GB
SLA PDFs (5 CSPs)             ~50MB
Project code                  ~100MB
────────────────────────────────────
TOTAL                         ~7–8GB
```

---

## 18. Environment Variables

```bash
# .env

# HuggingFace
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxx

# PostgreSQL
DATABASE_URL=postgresql://user:password@localhost:5432/cloudsla

# Redis
REDIS_URL=redis://localhost:6379/0

# LibreTranslate (self-hosted)
LIBRETRANSLATE_URL=http://localhost:5000

# ChromaDB
CHROMA_PERSIST_DIR=./chromadb

# Email Alerts (Gmail SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=cloudsla.alerts@gmail.com
SMTP_PASSWORD=your_gmail_app_password

# App
SECRET_KEY=your_secret_key_here
ENVIRONMENT=development
LOG_LEVEL=INFO

# Pricing API Refresh
PRICING_REFRESH_CRON=0 2 * * *

# SLA Re-fetch Schedule
SLA_REFETCH_CRON=0 2 * * 0
```

---

## 19. Docker Setup

```yaml
# docker-compose.yml

version: "3.9"

services:

  api:
    build: ./backend
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      - postgres
      - redis
      - chromadb
      - libretranslate
    volumes:
      - ./chromadb:/app/chromadb
      - ./sla_docs:/app/sla_docs

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - api

  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: cloudsla
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  chromadb:
    image: chromadb/chroma:latest
    ports:
      - "8001:8000"
    volumes:
      - chroma_data:/chroma/chroma

  libretranslate:
    image: libretranslate/libretranslate
    ports:
      - "5000:5000"

  celery_worker:
    build: ./backend
    command: celery -A app.celery worker --loglevel=info
    env_file: .env
    depends_on:
      - redis
      - postgres

  celery_beat:
    build: ./backend
    command: celery -A app.celery beat --loglevel=info
    env_file: .env
    depends_on:
      - redis

volumes:
  postgres_data:
  chroma_data:
```

---

## 20. Build Order

```
Week 1: Foundation
  ├── Set up Docker Compose (PostgreSQL, Redis, ChromaDB, LibreTranslate)
  ├── FastAPI project structure + database models
  └── SLA PDF ingestion pipeline (parse → chunk → embed → store)

Week 2: Core Ranking
  ├── Query understanding endpoint (LLM + Qwen2.5)
  ├── SLA metrics extraction (LLM + Llama-3.1)
  ├── TOPSIS ranker implementation
  └── /api/query endpoint working end-to-end

Week 3: Frontend
  ├── React project setup + shadcn/ui
  ├── Search page + query submission
  ├── Results page with scores and explanations
  └── Comparison page with table and radar chart

Week 4: ML + Feedback
  ├── XGBoost LambdaMART integration
  ├── Feature engineering pipeline
  ├── Feedback collection endpoints
  └── Celery retraining task

Week 5: Extended Features
  ├── Cost API integration (AWS/Azure/GCP pricing)
  ���── Multi-language support (LibreTranslate + lang detection)
  ├── SLA alert system (diff engine + email notifications)
  └── Admin dashboard for alerts

Week 6: Polish
  ├── SHAP explainability integration
  ├── Weight slider UI (user-adjustable TOPSIS weights)
  ├── Testing (pytest backend, Vitest frontend)
  └── Docker production build + README
```

---

## 21. Known Limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| XGBoost cold start | No ML ranking on day 1 | Bootstrap with TOPSIS scores as initial labels |
| PDF parsing fragility | Breaks if CSP changes document format | Add format validation + manual override endpoint |
| HF API rate limits | ~1000 req/day on free tier | Cache extraction results per SLA version in PostgreSQL |
| No live SLA status API | Weekly diff only | statuspage.io APIs for real-time uptime (future) |
| LibreTranslate quality | Lower than DeepL | Acceptable for project scope, can upgrade later |
| 5 CSPs only | Limited scope | Architecture supports adding more providers easily |

---

## Appendix — Free Hosting Options

| Platform | Service | Free Tier | Use For |
|---|---|---|---|
| Railway.app | Web service | 500 hrs/mo | FastAPI backend |
| Render.com | Web service | 750 hrs/mo | FastAPI backend |
| Neon.tech | PostgreSQL | 0.5GB | Production database |
| Upstash | Redis | 10k req/day | Celery broker |
| Hugging Face Spaces | Docker | CPU free | LibreTranslate |
| Vercel | Static/SSR | Unlimited | React frontend |
| Google Colab | GPU notebook | 12 hrs/session | Model testing |

---

*Document generated: 2026-04-01*
*Project: CloudSLA Recommender*
*All tools and APIs used are 100% open-source and free*
