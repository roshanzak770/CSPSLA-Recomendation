"""
Celery SLA tasks — weekly re-fetch and change detection + daily pricing refresh.
"""

from app.celery_app import celery_app


@celery_app.task(name="tasks.refresh_all_sla_documents")
def refresh_all_sla_documents():
    """
    Re-fetch SLA PDFs, diff against stored chunks, detect changes.
    Runs weekly via Celery Beat (Sunday 02:00).
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    import numpy as np
    from sentence_transformers import SentenceTransformer

    from app.core.config import settings
    from app.models.models import SLADocument, SLAChunk, SLAAlert, Provider
    from app.services.ingestion import extract_text_from_pdf, chunk_pages
    from app.services.llm_router import llm_router

    SIMILARITY_THRESHOLD = 0.95
    model = SentenceTransformer("intfloat/multilingual-e5-base")

    engine = create_engine(settings.database_url)
    changes_detected = 0

    with Session(engine) as session:
        documents = session.query(SLADocument).all()
        for doc in documents:
            if not doc.file_path or doc.file_path.startswith("manual_text://"):
                continue
            try:
                pages = extract_text_from_pdf(doc.file_path)
                new_chunks = chunk_pages(pages)
            except Exception:
                continue

            old_chunks = session.query(SLAChunk).filter_by(document_id=doc.id).all()
            old_texts = {c.chunk_index: c.chunk_text for c in old_chunks}

            for new_chunk in new_chunks:
                old_text = old_texts.get(new_chunk["chunk_index"])
                if not old_text:
                    continue

                old_emb = model.encode([f"passage: {old_text}"])[0]
                new_emb = model.encode([f"passage: {new_chunk['chunk_text']}"])[0]
                sim = float(np.dot(old_emb, new_emb) / (
                    np.linalg.norm(old_emb) * np.linalg.norm(new_emb) + 1e-10
                ))

                if sim < SIMILARITY_THRESHOLD:
                    # Classify change with LLM
                    try:
                        change_info = llm_router.describe_sla_change(
                            old_text, new_chunk["chunk_text"]
                        )
                    except Exception:
                        change_info = {
                            "change_type": "OTHER",
                            "severity": "LOW",
                            "description": "",
                        }

                    alert = SLAAlert(
                        provider_id=doc.provider_id,
                        change_type=change_info.get("change_type", "OTHER"),
                        old_value=old_text[:500],
                        new_value=new_chunk["chunk_text"][:500],
                        affected_clause=new_chunk["chunk_text"][:200],
                        severity=change_info.get("severity", "LOW"),
                    )
                    session.add(alert)
                    changes_detected += 1

        session.commit()

    # --- Threshold check against latest metrics ---
    _check_thresholds(engine)

    return {"status": "complete", "changes_detected": changes_detected}


def _check_thresholds(engine):
    """Check all active user-defined thresholds and send email alerts if breached."""
    from datetime import datetime, timezone
    from sqlalchemy.orm import Session
    from app.models.models import AlertThreshold, SLAMetrics, Provider
    from app.services.email_service import send_threshold_alert

    with Session(engine) as session:
        thresholds = session.query(AlertThreshold).filter_by(active=True).all()

        for t in thresholds:
            q = (
                session.query(SLAMetrics, Provider.name)
                .join(Provider, SLAMetrics.provider_id == Provider.id)
                .order_by(SLAMetrics.extracted_at.desc())
            )
            if t.provider_id:
                q = q.filter(SLAMetrics.provider_id == t.provider_id)

            seen: set = set()
            for metrics, pname in q.all():
                if metrics.provider_id in seen:
                    continue
                seen.add(metrics.provider_id)

                actual = getattr(metrics, t.metric, None)
                if actual is None:
                    continue

                breached = (
                    (t.operator == "below" and actual < t.threshold_value) or
                    (t.operator == "above" and actual > t.threshold_value)
                )
                if breached:
                    sent = send_threshold_alert(
                        to_email=t.email,
                        provider_name=pname,
                        metric=t.metric,
                        operator=t.operator,
                        threshold_value=t.threshold_value,
                        actual_value=actual,
                    )
                    if sent:
                        t.last_triggered_at = datetime.now(timezone.utc)

        session.commit()


@celery_app.task(name="tasks.discover_and_ingest_new_slas")
def discover_and_ingest_new_slas():
    """
    Discover new SLA documents from official CSP sources via DuckDuckGo and auto-ingest them.
    Runs weekly on Monday 03:00 UTC via Celery Beat.
    Skips URLs already in the database (checked by file_hash).
    """
    import hashlib
    import logging
    import time
    import urllib.request

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.models.models import Provider, SLADocument, SLAChunk, SLAMetrics, SLAAlert
    from app.services.web_search_agent import discover_all_known_providers
    from app.services.ingestion import chunk_pages, embed_and_store
    from app.services.llm_router import llm_router
    from sentence_transformers import SentenceTransformer

    logger = logging.getLogger(__name__)
    engine = create_engine(settings.database_url)
    model = SentenceTransformer("intfloat/multilingual-e5-base")

    stats = {"discovered": 0, "ingested": 0, "skipped": 0, "errors": 0}
    ingested_count = 0

    all_results = discover_all_known_providers(max_per_provider=5)

    with Session(engine) as session:
        for provider_name, results in all_results.items():
            stats["discovered"] += len(results)

            provider = session.query(Provider).filter(
                Provider.name.ilike(provider_name)
            ).first()
            if not provider:
                provider = Provider(name=provider_name)
                session.add(provider)
                session.flush()

            for result in results:
                if ingested_count >= settings.max_auto_ingest_per_run:
                    logger.info("Reached max_auto_ingest_per_run (%d), stopping.", settings.max_auto_ingest_per_run)
                    break

                url = result["url"]
                url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]

                # Skip if already ingested (match by file_hash)
                existing = session.query(SLADocument).filter(
                    SLADocument.file_hash == url_hash
                ).first()
                if existing:
                    stats["skipped"] += 1
                    continue

                try:
                    headers = {"User-Agent": "Mozilla/5.0 (compatible; SLAwise/1.0)"}
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        content_type = resp.headers.get("Content-Type", "")
                        raw = resp.read()
                except Exception as e:
                    logger.warning("Could not fetch %s: %s", url, e)
                    stats["errors"] += 1
                    continue

                # Extract text
                if "pdf" in content_type.lower() or url.lower().endswith(".pdf"):
                    import tempfile, os
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                        tmp.write(raw)
                        tmp_path = tmp.name
                    try:
                        from app.services.ingestion import extract_text_from_pdf
                        pages = extract_text_from_pdf(tmp_path)
                        full_text = " ".join(p["text"] for p in pages[:10])
                    except Exception as e:
                        logger.warning("PDF parse failed for %s: %s", url, e)
                        stats["errors"] += 1
                        os.unlink(tmp_path)
                        continue
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass
                else:
                    from html.parser import HTMLParser
                    class _TextEx(HTMLParser):
                        SKIP = {"script","style","nav","header","footer","noscript"}
                        def __init__(self):
                            super().__init__(); self.chunks=[]; self._d=0
                        def handle_starttag(self,t,_): self._d += t in self.SKIP
                        def handle_endtag(self,t):
                            if t in self.SKIP and self._d>0: self._d-=1
                        def handle_data(self,d):
                            if not self._d and d.strip(): self.chunks.append(d.strip())
                    ex = _TextEx()
                    ex.feed(raw.decode("utf-8", errors="replace"))
                    full_text = "\n".join(ex.chunks)
                    pages = [{"page_number": i+1, "text": full_text[i*2000:(i+1)*2000]}
                             for i in range(0, (len(full_text)+1999)//2000)]

                if len(full_text.strip()) < 100:
                    stats["skipped"] += 1
                    continue

                import uuid as _uuid
                doc_id = _uuid.uuid4()
                fake_path = f"auto_fetch://{provider_name}/{url_hash}"
                doc = SLADocument(id=doc_id, provider_id=provider.id,
                                  file_path=fake_path, file_hash=url_hash)
                session.add(doc)
                session.flush()

                chunks_list = chunk_pages(pages)
                try:
                    embed_and_store(
                        provider_name=provider_name,
                        document_id=str(doc_id),
                        source_file=url,
                        chunks=chunks_list,
                        model=model,
                    )
                except Exception as e:
                    logger.warning("Embed failed for %s: %s", url, e)
                    stats["errors"] += 1
                    continue

                for chunk in chunks_list:
                    session.add(SLAChunk(
                        document_id=doc_id,
                        chunk_text=chunk["chunk_text"],
                        embedding_id=f"{provider_name.lower()}_{doc_id}_{chunk['chunk_index']}",
                        page_number=chunk["page_number"],
                        chunk_index=chunk["chunk_index"],
                    ))

                try:
                    m = llm_router.extract_sla_metrics(full_text[:30000])
                    session.add(SLAMetrics(
                        provider_id=provider.id, document_id=doc_id,
                        uptime_sla_pct=m.get("uptime_sla_pct"),
                        rto_hours=m.get("rto_hours"),
                        rpo_hours=m.get("rpo_hours"),
                        support_response_min=m.get("support_response_min"),
                        penalty_credit_pct=m.get("penalty_credit_pct"),
                        regions=m.get("regions", []),
                        compliance=m.get("compliance", []),
                        source_clause=m.get("source_clause"),
                    ))
                except Exception:
                    pass

                session.add(SLAAlert(
                    provider_id=provider.id,
                    change_type="NEW_DOCUMENT",
                    new_value=url[:500],
                    affected_clause=result.get("title", "")[:200],
                    severity="INFO",
                ))

                stats["ingested"] += 1
                ingested_count += 1
                time.sleep(1)

        session.commit()

    logger.info("SLA discovery complete: %s", stats)
    return stats


@celery_app.task(name="tasks.refresh_pricing")
def refresh_pricing():
    """
    Refresh pricing cache from free public cloud pricing APIs.
    Runs daily at 02:00 UTC via Celery Beat.

    APIs used (all free, no paid keys required):
      - Azure Retail Prices API   — no auth needed
      - AWS Bulk Pricing JSON     — no auth, no AWS account needed
      - GCP Pricing Calculator    — no auth, no GCP account needed
      - IBM Global Catalog API    — no auth needed
      - Oracle Cloud              — curated static pricing (no API available)
    """
    import logging
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import settings
    from app.models.models import Provider, PricingCache
    from app.services.pricing import fetch_all_providers

    logger = logging.getLogger(__name__)
    engine = create_engine(settings.database_url)

    stats = {"providers_updated": 0, "items_cached": 0, "errors": []}

    with Session(engine) as session:
        # Fetch pricing from all providers in parallel-safe manner
        all_pricing = fetch_all_providers()

        for provider_name, items in all_pricing.items():
            provider = session.query(Provider).filter_by(name=provider_name).first()
            if not provider:
                # Try case-insensitive match
                provider = (
                    session.query(Provider)
                    .filter(Provider.name.ilike(f"%{provider_name}%"))
                    .first()
                )
            if not provider:
                logger.warning(
                    "Provider '%s' not in DB — skipping %d pricing items",
                    provider_name, len(items),
                )
                continue

            count = 0
            for item in items:
                price = item.get("price_usd", 0.0)
                # Skip items with no real price (index entries, etc.)
                if price == 0.0 and "detail_url" in item:
                    continue

                session.add(PricingCache(
                    provider_id=provider.id,
                    service=item.get("service", ""),
                    region=item.get("region", ""),
                    price_usd=price,
                ))
                count += 1

            stats["providers_updated"] += 1
            stats["items_cached"] += count
            logger.info(
                "Cached %d pricing items for %s", count, provider_name,
            )

        session.commit()

    logger.info(
        "Pricing refresh complete: %d providers, %d items",
        stats["providers_updated"], stats["items_cached"],
    )
    return stats