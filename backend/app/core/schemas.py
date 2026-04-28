from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime


# --- Query schemas ---

class QueryRequest(BaseModel):
    text: str
    weights: Optional[dict] = None  # user-adjustable TOPSIS weights


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


class AskResponse(BaseModel):
    answer: str
    sources: List[dict]
