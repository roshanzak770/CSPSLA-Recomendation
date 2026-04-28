"""
POST   /api/admin/ingest            — ingest a single SLA PDF
POST   /api/admin/upload            — upload + ingest PDF from browser
POST   /api/admin/ingest-url        — fetch a URL (PDF or HTML) and ingest it
DELETE /api/admin/provider/{id}     — delete provider and all its data
POST   /api/admin/refresh-sla       — trigger weekly re-fetch via Celery
"""

import io
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.core.schemas import IngestRequest, IngestUrlRequest, IngestResponse
from app.db.session import get_db
from app.models.models import Provider, SLADocument, SLAChunk, SLAMetrics, Ranking, Feedback, SLAAlert
from app.services.ingestion import ingest_pdf, _get_embedding_model, chunk_pages, embed_and_store
from app.services.llm_router import llm_router

SLA_DOCS_DIR = Path("/app/sla_docs")

router = APIRouter()
_embedding_model = None  # Module-level cache


def _get_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = _get_embedding_model()
    return _embedding_model


@router.post("/admin/ingest", response_model=IngestResponse)
async def ingest_sla(req: IngestRequest, db: AsyncSession = Depends(get_db)):
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
async def delete_provider(provider_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
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
async def ingest_sla_url(req: IngestUrlRequest, db: AsyncSession = Depends(get_db)):
    """Fetch a URL (PDF or HTML SLA page), extract text, and run the ingestion pipeline."""
    import hashlib
    import time
    import urllib.request
    import urllib.error

    # Download the URL
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; CloudSLA-Recommender/1.0)"}
        request = urllib.request.Request(req.url, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
    except urllib.error.URLError as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {e.reason}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {str(e)}")

    SLA_DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # If content is a PDF, save and ingest normally
    if "pdf" in content_type.lower() or req.url.lower().endswith(".pdf"):
        safe_name = f"{req.provider.lower().replace(' ', '_')}_{uuid.uuid4().hex[:8]}.pdf"
        dest = SLA_DOCS_DIR / safe_name
        dest.write_bytes(raw)

        prov_result = await db.execute(select(Provider).where(Provider.name.ilike(req.provider)))
        prov = prov_result.scalar_one_or_none()
        if not prov:
            prov = Provider(name=req.provider)
            db.add(prov)
            await db.flush()

        doc_id = uuid.uuid4()
        doc = SLADocument(id=doc_id, provider_id=prov.id, file_path=str(dest))
        db.add(doc)
        await db.flush()

        model = _get_model()
        result = ingest_pdf(provider_name=req.provider, document_id=str(doc_id), pdf_path=str(dest), model=model)
        doc.file_hash = result["file_hash"]

        from app.services.ingestion import extract_text_from_pdf
        pages = extract_text_from_pdf(str(dest))
        chunks_list = chunk_pages(pages)
        for chunk in chunks_list:
            db.add(SLAChunk(
                document_id=doc_id,
                chunk_text=chunk["chunk_text"],
                embedding_id=f"{req.provider.lower()}_{doc_id}_{chunk['chunk_index']}",
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
        return IngestResponse(chunks_created=result["chunks_created"], embedding_time_sec=result["embedding_time_sec"])

    # Otherwise treat as HTML — extract visible text with html.parser
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

    # Build pseudo-pages of ~2000 chars for chunk_pages compatibility
    page_size = 2000
    raw_pages = [
        {"page_number": i + 1, "text": full_text[i * page_size:(i + 1) * page_size]}
        for i in range(0, (len(full_text) + page_size - 1) // page_size)
    ]

    prov_result = await db.execute(select(Provider).where(Provider.name.ilike(req.provider)))
    prov = prov_result.scalar_one_or_none()
    if not prov:
        prov = Provider(name=req.provider)
        db.add(prov)
        await db.flush()

    doc_id = uuid.uuid4()
    url_hash = hashlib.sha256(req.url.encode()).hexdigest()[:16]
    fake_path = str(SLA_DOCS_DIR / f"{req.provider.lower().replace(' ', '_')}_{url_hash}.html")
    doc = SLADocument(id=doc_id, provider_id=prov.id, file_path=fake_path, file_hash=url_hash)
    db.add(doc)
    await db.flush()

    chunks_list = chunk_pages(raw_pages)
    model = _get_model()

    start = time.time()
    chunk_ids = embed_and_store(
        provider_name=req.provider,
        document_id=str(doc_id),
        source_file=req.url,
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
    return IngestResponse(chunks_created=len(chunk_ids), embedding_time_sec=round(elapsed, 2))


@router.post("/admin/refresh-sla")
async def refresh_sla():
    from app.tasks.sla_tasks import refresh_all_sla_documents
    task = refresh_all_sla_documents.delay()
    return {"task_id": task.id}
