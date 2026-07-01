from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime


# --- Query schemas ---

class QueryRequest(BaseModel):
    text: str
    weights: Optional[dict] = None  # user-adjustable TOPSIS weights
    lang: str = "English"           # response language chosen by user
    # When set, rankings are computed per-service within this category
    # instead of per-provider monolith. One of compute/storage/database/
    # network/serverless (see SERVICE_CATEGORIES in service_catalog.py).
    # None / omitted = current monolithic per-provider behaviour.
    service_category: Optional[str] = None


class ParsedRequirements(BaseModel):
    uptime_required_pct: Optional[float] = None
    rto_hours: Optional[float] = None
    rpo_hours: Optional[float] = None
    region: Optional[str] = None
    country: Optional[str] = None
    compliance: List[str] = []
    category: Optional[str] = None
    sensitivity: Optional[str] = None
    budget_usd_monthly: Optional[float] = None


class ProviderRanking(BaseModel):
    provider_id: UUID
    provider_name: str
    rank_position: int
    final_score: float
    topsis_score: Optional[float]
    xgb_score: Optional[float]
    xgb_cold_start: bool = True
    cosine_score: Optional[float]
    cost_usd: Optional[float]
    value_score: Optional[float]
    explanation: Optional[str]
    meets_uptime: Optional[bool]
    meets_rto: Optional[bool]
    meets_region: Optional[bool]
    compliance_tags: List[str] = []
    sla_url: Optional[str] = None
    # Populated when the user filtered by service_category. Lets the UI
    # show e.g. "AWS — Amazon S3 Standard (99.9 %)" instead of just "AWS".
    service_name:        Optional[str]   = None
    service_uptime_pct:  Optional[float] = None
    service_rto_hours:   Optional[float] = None
    service_rpo_hours:   Optional[float] = None
    service_category:    Optional[str]   = None


class QueryResponse(BaseModel):
    query_id: UUID
    detected_lang: Optional[str]
    parsed_requirements: Optional[ParsedRequirements]
    rankings: List[ProviderRanking]
    low_confidence: Optional[bool] = None
    suggestion: Optional[str] = None
    auto_fetch_available: Optional[bool] = None
    message: Optional[str] = None
    lang: Optional[str] = None  # echoed back so frontend can label explanations


# --- Feedback schemas ---

class FeedbackRequest(BaseModel):
    query_id: UUID
    provider_id: UUID
    signal: str  # thumbs_up | thumbs_down | clicked_provider | accepted_recommendation


class FeedbackResponse(BaseModel):
    success: bool


class FeedbackStatsResponse(BaseModel):
    total_feedbacks: int
    by_signal: dict
    unique_training_pairs: int
    retrain_threshold: int
    can_retrain: bool
    feedbacks_until_auto_retrain: int
    auto_retrain_every: int
    xgboost_model_exists: bool


# --- Provider schemas ---

class ProviderSchema(BaseModel):
    id: UUID
    name: str
    website: Optional[str]
    logo_url: Optional[str]

    class Config:
        from_attributes = True


class SLAMetricsSchema(BaseModel):
    id: UUID
    provider_id: UUID
    uptime_sla_pct: Optional[float]
    rto_hours: Optional[float]
    rpo_hours: Optional[float]
    support_response_min: Optional[int]
    penalty_credit_pct: Optional[int]
    regions: Optional[List[str]]
    compliance: Optional[List[str]]
    source_clause: Optional[str]
    extracted_at: Optional[datetime]

    class Config:
        from_attributes = True


# --- Alert schemas ---

class AlertSchema(BaseModel):
    id: UUID
    provider_id: UUID
    provider_name: Optional[str]
    change_type: Optional[str]
    old_value: Optional[str]
    new_value: Optional[str]
    affected_clause: Optional[str]
    severity: Optional[str]
    detected_at: Optional[datetime]

    class Config:
        from_attributes = True


# --- Admin schemas ---

class IngestRequest(BaseModel):
    provider: str
    pdf_path: str
    service_category: Optional[str] = None   # compute|storage|database|network|serverless


class IngestUrlRequest(BaseModel):
    provider: str
    url: str
    service_category: Optional[str] = None


class IngestResponse(BaseModel):
    chunks_created: int
    embedding_time_sec: float


# --- Ask / RAG schemas ---

class AskRequest(BaseModel):
    question: str
    provider: Optional[str] = None  # optional filter to a specific provider
    # Optional service-category filter — when set we look for chunks tagged
    # with this service category first, and fall back to provider-only with
    # a heads-up note when no category-tagged content exists yet.
    service_category: Optional[str] = None
    lang: str = "English"  # response language chosen by user


class AskResponse(BaseModel):
    answer: str
    sources: List[dict]
    # Human-readable note explaining when we fell back (e.g. "No storage-
    # specific SLA found for AWS — showing general AWS SLA instead").
    # null in the happy path. Frontend renders this above the answer.
    info: Optional[str] = None


# --- Web search / discovery schemas ---

class SLASearchRequest(BaseModel):
    query: str
    max_results: int = 10


class SLASearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    is_pdf: bool
    relevance_score: int


class SLASearchResponse(BaseModel):
    query: str
    results: List[SLASearchResult]
    total: int
    info: Optional[str] = None


class IngestSelectedRequest(BaseModel):
    provider: str
    urls: List[str]
    service_category: Optional[str] = None


class IngestTextRequest(BaseModel):
    provider: str
    text: str
    title: str = "Manual paste"
    service_category: Optional[str] = None


class BatchIngestResult(BaseModel):
    url: str
    chunks_created: int = 0
    error: Optional[str] = None


class BatchIngestResponse(BaseModel):
    results: List[BatchIngestResult]


class AutoFetchRequest(BaseModel):
    query: str
    provider: Optional[str] = None


class AutoFetchResponse(BaseModel):
    ingested: int
    message: str


class ParseWebRequest(BaseModel):
    url: str
    provider: str


class ParseWebResponse(BaseModel):
    summary: str
    metrics: Optional[dict] = None
    ingested: bool = False
    chunks_created: int = 0
    error: Optional[str] = None


# --- Alert Threshold schemas ---

class AlertThresholdCreate(BaseModel):
    email: str
    provider_id: Optional[UUID] = None   # null = watch all providers
    metric: str                           # uptime_sla_pct | rto_hours | rpo_hours | penalty_credit_pct
    operator: str                         # below | above
    threshold_value: float


class AlertThresholdSchema(BaseModel):
    id: UUID
    email: str
    provider_id: Optional[UUID]
    provider_name: Optional[str] = None
    metric: str
    operator: str
    threshold_value: float
    active: bool
    created_at: Optional[datetime]
    last_triggered_at: Optional[datetime] = None

    class Config:
        from_attributes = True
