from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime


# --- Query schemas ---

class QueryRequest(BaseModel):
    text: str
    weights: Optional[dict] = None  # user-adjustable TOPSIS weights
    lang: str = "English"           # response language chosen by user


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
    cosine_score: Optional[float]
    cost_usd: Optional[float]
    value_score: Optional[float]
    explanation: Optional[str]
    meets_uptime: Optional[bool]
    meets_rto: Optional[bool]
    meets_region: Optional[bool]
    compliance_tags: List[str] = []


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


class IngestUrlRequest(BaseModel):
    provider: str
    url: str


class IngestResponse(BaseModel):
    chunks_created: int
    embedding_time_sec: float


# --- Ask / RAG schemas ---

class AskRequest(BaseModel):
    question: str
    provider: Optional[str] = None  # optional filter to a specific provider
    lang: str = "English"  # response language chosen by user


class AskResponse(BaseModel):
    answer: str
    sources: List[dict]


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


class IngestTextRequest(BaseModel):
    provider: str
    text: str
    title: str = "Manual paste"


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
