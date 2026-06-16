"""
POST   /api/admin/ingest            — ingest a single SLA PDF
POST   /api/admin/upload            — upload + ingest PDF from browser
POST   /api/admin/ingest-url        — fetch a URL (PDF or HTML) and ingest it
POST   /api/admin/ingest-text       — ingest raw SLA text pasted by the user
DELETE /api/admin/provider/{id}     — delete provider and all its data
POST   /api/admin/refresh-sla       — trigger weekly re-fetch via Celery
GET    /api/admin/feedback/stats    — feedback counts and XGBoost training status
POST   /api/admin/retrain-now       — manually trigger XGBoost retraining
"""

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Security, UploadFile
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from app.core.config import settings
from app.core.schemas import IngestRequest, IngestUrlRequest, IngestResponse, IngestTextRequest, FeedbackStatsResponse
from app.db.session import get_db
from app.models.models import Provider, SLADocument, SLAChunk, SLAMetrics, Ranking, Feedback, SLAAlert
from app.services.ingestion import ingest_pdf, _get_embedding_model, chunk_pages, embed_and_store
from app.services.llm_router import llm_router

SLA_DOCS_DIR = Path("/app/sla_docs")

router = APIRouter()
_embedding_model = None  # Module-level cache

_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def require_admin(key: str = Security(_key_header)):
    if not key or key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing admin key")


def _get_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = _get_embedding_model()
    return _embedding_model


async def _ingest_url_to_db(url: str, provider: str, db: AsyncSession, model) -> dict:
    """
    Shared async helper: fetch URL, detect PDF vs HTML, chunk, embed, persist to DB.
    Returns {"chunks_created": int, "embedding_time_sec": float}.
    Raises HTTPException on failure.
    """
    import hashlib
    import time
    import urllib.request
    import urllib.error

    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; CloudSLA-Recommender/1.0)"}
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
    except urllib.error.URLError as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {e.reason}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {str(e)}")

    SLA_DOCS_DIR.mkdir(parents=True, exist_ok=True)

    prov_result = await db.execute(select(Provider).where(Provider.name.ilike(provider)))
    prov = prov_result.scalar_one_or_none()
    if not prov:
        prov = Provider(name=provider)
        db.add(prov)
        await db.flush()

    if "pdf" in content_type.lower() or url.lower().endswith(".pdf"):
        safe_name = f"{provider.lower().replace(' ', '_')}_{uuid.uuid4().hex[:8]}.pdf"
        dest = SLA_DOCS_DIR / safe_name
        dest.write_bytes(raw)

        doc_id = uuid.uuid4()
        doc = SLADocument(id=doc_id, provider_id=prov.id, file_path=str(dest))
        db.add(doc)
        await db.flush()

        result = ingest_pdf(provider_name=provider, document_id=str(doc_id), pdf_path=str(dest), model=model)
        doc.file_hash = result["file_hash"]

        from app.services.ingestion import extract_text_from_pdf
        pages = extract_text_from_pdf(str(dest))
        chunks_list = chunk_pages(pages)
        for chunk in chunks_list:
            db.add(SLAChunk(
                document_id=doc_id,
                chunk_text=chunk["chunk_text"],
                embedding_id=f"{provider.lower()}_{doc_id}_{chunk['chunk_index']}",
                page_number=chunk["page_number"],
                chunk_index=chunk["chunk_index"],
            ))

        full_text = " ".join(p["text"] for p in pages[:10])
        try:
            metrics_dict = llm_router.extract_sla_metrics(full_text[:3000])
            db.add(SLAMetrics(
                provider_id=prov.id, document_id=doc_id,
                uptime_sla_pct=metrics_dict.get("uptime_sla_pct"),
                rto_hours=metrics_dict.get("rto_hours"),
                rpo_hours=metrics_dict.get("rpo_hours"),
                support_response_min=metrics_dict.get("support_response_min"),
                penalty_credit_pct=metrics_dict.get("penalty_credit_pct"),
                regions=metrics_dict.get("regions", []),
                compliance=metrics_dict.get("compliance", []),
                source_clause=metrics_dict.get("source_clause"),
            ))
        except Exception:
            pass

        await db.commit()
        return {"chunks_created": result["chunks_created"], "embedding_time_sec": result["embedding_time_sec"]}

    # HTML path
    from html.parser import HTMLParser

    class _TextExtractor(HTMLParser):
        SKIP_TAGS = {"script", "style", "nav", "header", "footer", "noscript"}
        def __init__(self):
            super().__init__()
            self.chunks = []
            self._skip_depth = 0
        def handle_starttag(self, tag, _attrs):
            if tag in self.SKIP_TAGS:
                self._skip_depth += 1
        def handle_endtag(self, tag):
            if tag in self.SKIP_TAGS and self._skip_depth > 0:
                self._skip_depth -= 1
        def handle_data(self, data):
            if self._skip_depth == 0 and data.strip():
                self.chunks.append(data.strip())

    html_text = raw.decode("utf-8", errors="replace")
    extractor = _TextExtractor()
    extractor.feed(html_text)
    full_text = "\n".join(extractor.chunks)

    if len(full_text.strip()) < 100:
        raise HTTPException(status_code=422, detail="Could not extract meaningful text from the URL.")

    page_size = 2000
    raw_pages = [
        {"page_number": i + 1, "text": full_text[i * page_size:(i + 1) * page_size]}
        for i in range(0, (len(full_text) + page_size - 1) // page_size)
    ]

    doc_id = uuid.uuid4()
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    fake_path = str(SLA_DOCS_DIR / f"{provider.lower().replace(' ', '_')}_{url_hash}.html")
    doc = SLADocument(id=doc_id, provider_id=prov.id, file_path=fake_path, file_hash=url_hash)
    db.add(doc)
    await db.flush()

    chunks_list = chunk_pages(raw_pages)
    start = time.time()
    try:
        chunk_ids = embed_and_store(
            provider_name=provider,
            document_id=str(doc_id),
            source_file=url,
            chunks=chunks_list,
            model=model,
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Embedding failed — ChromaDB may be unavailable: {e}",
        )
    elapsed = time.time() - start

    for chunk in chunks_list:
        db.add(SLAChunk(
            document_id=doc_id,
            chunk_text=chunk["chunk_text"],
            embedding_id=f"{provider.lower()}_{doc_id}_{chunk['chunk_index']}",
            page_number=chunk["page_number"],
            chunk_index=chunk["chunk_index"],
        ))

    try:
        metrics_dict = llm_router.extract_sla_metrics(full_text[:3000])
        db.add(SLAMetrics(
            provider_id=prov.id, document_id=doc_id,
            uptime_sla_pct=metrics_dict.get("uptime_sla_pct"),
            rto_hours=metrics_dict.get("rto_hours"),
            rpo_hours=metrics_dict.get("rpo_hours"),
            support_response_min=metrics_dict.get("support_response_min"),
            penalty_credit_pct=metrics_dict.get("penalty_credit_pct"),
            regions=metrics_dict.get("regions", []),
            compliance=metrics_dict.get("compliance", []),
            source_clause=metrics_dict.get("source_clause"),
        ))
    except Exception:
        pass

    await db.commit()
    return {"chunks_created": len(chunk_ids), "embedding_time_sec": round(elapsed, 2)}


@router.post("/admin/ingest", response_model=IngestResponse)
async def ingest_sla(req: IngestRequest, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin)):
    if not Path(req.pdf_path).exists():
        raise HTTPException(status_code=400, detail=f"PDF not found: {req.pdf_path}")

    # Get or create provider
    prov_result = await db.execute(
        select(Provider).where(Provider.name.ilike(req.provider))
    )
    provider = prov_result.scalar_one_or_none()
    if not provider:
        provider = Provider(name=req.provider)
        db.add(provider)
        await db.flush()

    # Create SLA document record
    doc_id = uuid.uuid4()
    doc = SLADocument(
        id=doc_id,
        provider_id=provider.id,
        file_path=req.pdf_path,
    )
    db.add(doc)
    await db.flush()

    # Run ingestion pipeline
    model = _get_model()
    result = ingest_pdf(
        provider_name=req.provider,
        document_id=str(doc_id),
        pdf_path=req.pdf_path,
        model=model,
    )

    # Update document with hash
    doc.file_hash = result["file_hash"]

    # Store chunk records in PostgreSQL
    from app.services.ingestion import extract_text_from_pdf, chunk_pages
    pages = extract_text_from_pdf(req.pdf_path)
    chunks = chunk_pages(pages)
    for chunk in chunks:
        chunk_id = f"{req.provider.lower()}_{doc_id}_{chunk['chunk_index']}"
        db.add(SLAChunk(
            document_id=doc_id,
            chunk_text=chunk["chunk_text"],
            embedding_id=chunk_id,
            page_number=chunk["page_number"],
            chunk_index=chunk["chunk_index"],
        ))

    # Extract SLA metrics via LLM from the full text
    full_text = " ".join(p["text"] for p in pages[:10])  # first 10 pages
    try:
        metrics_dict = llm_router.extract_sla_metrics(full_text[:3000])
        db.add(SLAMetrics(
            provider_id=provider.id,
            document_id=doc_id,
            uptime_sla_pct=metrics_dict.get("uptime_sla_pct"),
            rto_hours=metrics_dict.get("rto_hours"),
            rpo_hours=metrics_dict.get("rpo_hours"),
            support_response_min=metrics_dict.get("support_response_min"),
            penalty_credit_pct=metrics_dict.get("penalty_credit_pct"),
            regions=metrics_dict.get("regions", []),
            compliance=metrics_dict.get("compliance", []),
            source_clause=metrics_dict.get("source_clause"),
        ))
    except Exception:
        pass  # Metrics can be added manually via another endpoint

    await db.commit()

    return IngestResponse(
        chunks_created=result["chunks_created"],
        embedding_time_sec=result["embedding_time_sec"],
    )


@router.post("/admin/upload", response_model=IngestResponse)
async def upload_sla_pdf(
    provider: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Upload a PDF directly from the browser, save it, then run ingestion."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    SLA_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"{provider.lower().replace(' ', '_')}_{uuid.uuid4().hex[:8]}.pdf"
    dest = SLA_DOCS_DIR / safe_name

    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # Get or create provider
    prov_result = await db.execute(select(Provider).where(Provider.name.ilike(provider)))
    prov = prov_result.scalar_one_or_none()
    if not prov:
        prov = Provider(name=provider)
        db.add(prov)
        await db.flush()

    doc_id = uuid.uuid4()
    doc = SLADocument(id=doc_id, provider_id=prov.id, file_path=str(dest))
    db.add(doc)
    await db.flush()

    model = _get_model()
    result = ingest_pdf(provider_name=provider, document_id=str(doc_id), pdf_path=str(dest), model=model)
    doc.file_hash = result["file_hash"]

    from app.services.ingestion import extract_text_from_pdf, chunk_pages
    pages = extract_text_from_pdf(str(dest))
    chunks = chunk_pages(pages)
    for chunk in chunks:
        db.add(SLAChunk(
            document_id=doc_id,
            chunk_text=chunk["chunk_text"],
            embedding_id=f"{provider.lower()}_{doc_id}_{chunk['chunk_index']}",
            page_number=chunk["page_number"],
            chunk_index=chunk["chunk_index"],
        ))

    full_text = " ".join(p["text"] for p in pages[:10])
    try:
        metrics_dict = llm_router.extract_sla_metrics(full_text[:3000])
        db.add(SLAMetrics(
            provider_id=prov.id,
            document_id=doc_id,
            uptime_sla_pct=metrics_dict.get("uptime_sla_pct"),
            rto_hours=metrics_dict.get("rto_hours"),
            rpo_hours=metrics_dict.get("rpo_hours"),
            support_response_min=metrics_dict.get("support_response_min"),
            penalty_credit_pct=metrics_dict.get("penalty_credit_pct"),
            regions=metrics_dict.get("regions", []),
            compliance=metrics_dict.get("compliance", []),
            source_clause=metrics_dict.get("source_clause"),
        ))
    except Exception:
        pass

    await db.commit()
    return IngestResponse(chunks_created=result["chunks_created"], embedding_time_sec=result["embedding_time_sec"])


@router.delete("/admin/provider/{provider_id}")
async def delete_provider(provider_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin)):
    """Delete a provider and all associated documents, chunks, metrics, and ChromaDB embeddings."""
    prov = await db.get(Provider, provider_id)
    if not prov:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Collect all document IDs for this provider
    docs_result = await db.execute(select(SLADocument).where(SLADocument.provider_id == provider_id))
    docs = docs_result.scalars().all()
    doc_ids = [doc.id for doc in docs]

    # Delete PDF files from disk
    for doc in docs:
        try:
            Path(doc.file_path).unlink(missing_ok=True)
        except Exception:
            pass

    # Remove embeddings from ChromaDB
    if doc_ids:
        try:
            import chromadb
            from app.core.config import settings
            client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
            collection = client.get_or_create_collection("sla_documents")
            for doc_id in doc_ids:
                collection.delete(where={"document_id": str(doc_id)})
        except Exception:
            pass

    # Delete all related DB rows in dependency order
    if doc_ids:
        await db.execute(delete(SLAChunk).where(SLAChunk.document_id.in_(doc_ids)))
        await db.execute(delete(SLAMetrics).where(SLAMetrics.document_id.in_(doc_ids)))
        await db.execute(delete(SLADocument).where(SLADocument.provider_id == provider_id))

    await db.execute(delete(SLAAlert).where(SLAAlert.provider_id == provider_id))
    await db.execute(delete(Feedback).where(Feedback.provider_id == provider_id))
    await db.execute(delete(Ranking).where(Ranking.provider_id == provider_id))
    await db.execute(delete(SLAMetrics).where(SLAMetrics.provider_id == provider_id))
    await db.execute(delete(Provider).where(Provider.id == provider_id))

    await db.commit()
    return {"deleted": prov.name, "documents_removed": len(doc_ids)}


@router.post("/admin/ingest-url", response_model=IngestResponse)
async def ingest_sla_url(req: IngestUrlRequest, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin)):
    """Fetch a URL (PDF or HTML SLA page), extract text, and run the ingestion pipeline."""
    model = _get_model()
    result = await _ingest_url_to_db(req.url, req.provider, db, model)
    return IngestResponse(**result)


@router.post("/admin/ingest-text", response_model=IngestResponse)
async def ingest_sla_text(req: IngestTextRequest, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin)):
    """Accept raw SLA text pasted by the user and run the ingestion pipeline."""
    import hashlib
    import time
    import re

    text = req.text.strip()
    if len(text) < 200:
        raise HTTPException(status_code=422, detail="Text too short — minimum 200 characters required.")

    prov_result = await db.execute(select(Provider).where(Provider.name.ilike(req.provider)))
    prov = prov_result.scalar_one_or_none()
    if not prov:
        prov = Provider(name=req.provider)
        db.add(prov)
        await db.flush()

    doc_id = uuid.uuid4()
    title_slug = re.sub(r"[^a-z0-9]+", "_", req.title.lower())[:40]
    fake_path = f"manual_text://{req.provider}/{title_slug}_{doc_id.hex[:8]}"
    file_hash = hashlib.sha256(text.encode()).hexdigest()

    doc = SLADocument(id=doc_id, provider_id=prov.id, file_path=fake_path, file_hash=file_hash)
    db.add(doc)
    await db.flush()

    page_size = 2000
    raw_pages = [
        {"page_number": i + 1, "text": text[i * page_size:(i + 1) * page_size]}
        for i in range(0, (len(text) + page_size - 1) // page_size)
    ]

    model = _get_model()
    chunks_list = chunk_pages(raw_pages)
    start = time.time()
    chunk_ids = embed_and_store(
        provider_name=req.provider,
        document_id=str(doc_id),
        source_file=fake_path,
        chunks=chunks_list,
        model=model,
    )
    elapsed = time.time() - start

    for chunk in chunks_list:
        db.add(SLAChunk(
            document_id=doc_id,
            chunk_text=chunk["chunk_text"],
            embedding_id=f"{req.provider.lower()}_{doc_id}_{chunk['chunk_index']}",
            page_number=chunk["page_number"],
            chunk_index=chunk["chunk_index"],
        ))

    try:
        metrics_dict = llm_router.extract_sla_metrics(text[:3000])
        db.add(SLAMetrics(
            provider_id=prov.id, document_id=doc_id,
            uptime_sla_pct=metrics_dict.get("uptime_sla_pct"),
            rto_hours=metrics_dict.get("rto_hours"),
            rpo_hours=metrics_dict.get("rpo_hours"),
            support_response_min=metrics_dict.get("support_response_min"),
            penalty_credit_pct=metrics_dict.get("penalty_credit_pct"),
            regions=metrics_dict.get("regions", []),
            compliance=metrics_dict.get("compliance", []),
            source_clause=metrics_dict.get("source_clause"),
        ))
    except Exception:
        pass

    await db.commit()
    return IngestResponse(chunks_created=len(chunk_ids), embedding_time_sec=round(elapsed, 2))


@router.post("/admin/refresh-sla")
async def refresh_sla(_: None = Depends(require_admin)):
    from app.tasks.sla_tasks import refresh_all_sla_documents
    task = refresh_all_sla_documents.delay()
    return {"task_id": task.id}


@router.get("/admin/feedback/stats", response_model=FeedbackStatsResponse)
async def feedback_stats(db: AsyncSession = Depends(get_db), _: None = Depends(require_admin)):
    from pathlib import Path
    from app.services.ranker import MODEL_PATH
    from app.models.models import Feedback

    RETRAIN_THRESHOLD = 10
    AUTO_RETRAIN_EVERY = 100

    total_result = await db.execute(select(func.count(Feedback.id)))
    total = total_result.scalar_one()

    signal_rows = await db.execute(
        select(Feedback.signal_type, func.count(Feedback.id).label("cnt"))
        .group_by(Feedback.signal_type)
    )
    by_signal = {row.signal_type: row.cnt for row in signal_rows.all()}

    pairs_result = await db.execute(
        select(func.count()).select_from(
            select(Feedback.query_id, Feedback.provider_id).distinct().subquery()
        )
    )
    unique_pairs = pairs_result.scalar_one()

    return FeedbackStatsResponse(
        total_feedbacks=total,
        by_signal=by_signal,
        unique_training_pairs=unique_pairs,
        retrain_threshold=RETRAIN_THRESHOLD,
        can_retrain=unique_pairs >= RETRAIN_THRESHOLD,
        feedbacks_until_auto_retrain=(AUTO_RETRAIN_EVERY - total % AUTO_RETRAIN_EVERY) % AUTO_RETRAIN_EVERY,
        auto_retrain_every=AUTO_RETRAIN_EVERY,
        xgboost_model_exists=Path(MODEL_PATH).exists(),
    )


@router.post("/admin/retrain-now")
async def retrain_now(_: None = Depends(require_admin)):
    from app.tasks.ml_tasks import retrain_xgboost
    task = retrain_xgboost.delay()
    return {"task_id": task.id, "status": "queued"}
