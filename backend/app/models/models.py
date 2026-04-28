import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TIMESTAMP,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Provider(Base):
    __tablename__ = "providers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    website = Column(String(255))
    logo_url = Column(String(255))
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    sla_documents = relationship("SLADocument", back_populates="provider")
    sla_metrics = relationship("SLAMetrics", back_populates="provider")
    pricing = relationship("PricingCache", back_populates="provider")
    alerts = relationship("SLAAlert", back_populates="provider")


class SLADocument(Base):
    __tablename__ = "sla_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("providers.id"))
    version = Column(String(50))
    file_path = Column(String(255))
    file_hash = Column(String(64))
    ingested_at = Column(TIMESTAMP, default=datetime.utcnow)

    provider = relationship("Provider", back_populates="sla_documents")
    chunks = relationship("SLAChunk", back_populates="document")
    metrics = relationship("SLAMetrics", back_populates="document")


class SLAChunk(Base):
    __tablename__ = "sla_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("sla_documents.id"))
    chunk_text = Column(Text, nullable=False)
    embedding_id = Column(String(100))
    page_number = Column(Integer)
    chunk_index = Column(Integer)

    document = relationship("SLADocument", back_populates="chunks")


class SLAMetrics(Base):
    __tablename__ = "sla_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("providers.id"))
    document_id = Column(UUID(as_uuid=True), ForeignKey("sla_documents.id"))
    uptime_sla_pct = Column(Float)
    rto_hours = Column(Float)
    rpo_hours = Column(Float)
    support_response_min = Column(Integer)
    penalty_credit_pct = Column(Integer)
    regions = Column(ARRAY(Text))
    compliance = Column(ARRAY(Text))
    source_clause = Column(Text)
    extracted_at = Column(TIMESTAMP, default=datetime.utcnow)

    provider = relationship("Provider", back_populates="sla_metrics")
    document = relationship("SLADocument", back_populates="metrics")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    language_pref = Column(String(10), default="en")
    is_admin = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    queries = relationship("Query", back_populates="user")
    feedback = relationship("Feedback", back_populates="user")
    user_alerts = relationship("UserAlert", back_populates="user")


class Query(Base):
    __tablename__ = "queries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    raw_input = Column(Text, nullable=False)
    detected_lang = Column(String(10))
    parsed_json = Column(JSONB)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    user = relationship("User", back_populates="queries")
    rankings = relationship("Ranking", back_populates="query")
    feedback = relationship("Feedback", back_populates="query")


class Ranking(Base):
    __tablename__ = "rankings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_id = Column(UUID(as_uuid=True), ForeignKey("queries.id"))
    provider_id = Column(UUID(as_uuid=True), ForeignKey("providers.id"))
    topsis_score = Column(Float)
    xgb_score = Column(Float)
    llm_score = Column(Float)
    final_score = Column(Float)
    cost_usd = Column(Float)
    value_score = Column(Float)
    explanation = Column(Text)
    rank_position = Column(Integer)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    query = relationship("Query", back_populates="rankings")
    provider = relationship("Provider")


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_id = Column(UUID(as_uuid=True), ForeignKey("queries.id"))
    provider_id = Column(UUID(as_uuid=True), ForeignKey("providers.id"))
    signal_type = Column(String(50))
    weight = Column(Float)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    query = relationship("Query", back_populates="feedback")
    user = relationship("User", back_populates="feedback")
    provider = relationship("Provider")


class SLAAlert(Base):
    __tablename__ = "sla_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("providers.id"))
    change_type = Column(String(50))
    old_value = Column(Text)
    new_value = Column(Text)
    affected_clause = Column(Text)
    severity = Column(String(20))
    detected_at = Column(TIMESTAMP, default=datetime.utcnow)
    notified_at = Column(TIMESTAMP)

    provider = relationship("Provider", back_populates="alerts")
    user_alerts = relationship("UserAlert", back_populates="alert")


class UserAlert(Base):
    __tablename__ = "user_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    alert_id = Column(UUID(as_uuid=True), ForeignKey("sla_alerts.id"))
    read_at = Column(TIMESTAMP)

    user = relationship("User", back_populates="user_alerts")
    alert = relationship("SLAAlert", back_populates="user_alerts")


class PricingCache(Base):
    __tablename__ = "pricing_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("providers.id"))
    service = Column(String(200))
    sku = Column(String(200), nullable=True)
    region = Column(String(100))
    price_usd = Column(Float)
    unit = Column(String(50), nullable=True)
    fetched_at = Column(TIMESTAMP, default=datetime.utcnow)

    provider = relationship("Provider", back_populates="pricing")