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
            if not doc.file_path:
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

    return {"status": "complete", "changes_detected": changes_detected}


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