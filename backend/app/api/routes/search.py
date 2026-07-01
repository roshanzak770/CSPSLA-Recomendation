"""
POST /api/search/sla             — web search for SLA documents (no DB write)
POST /api/search/ingest-selected — batch-ingest user-selected URLs from search results
POST /api/search/auto-fetch      — auto-fetch + ingest top results for a query/provider
POST /api/search/parse-web       — fetch + parse a web page, summarise SLA content via LLM
"""

import logging
import urllib.request
from html.parser import HTMLParser

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import (
    SLASearchRequest, SLASearchResponse, SLASearchResult,
    IngestSelectedRequest, BatchIngestResponse, BatchIngestResult,
    AutoFetchRequest, AutoFetchResponse,
    ParseWebRequest, ParseWebResponse,
)
from app.db.session import get_db
from app.services.web_search_agent import (
    search_sla_documents, discover_provider_slas,
    _try_ddg_search, _detect_provider_from_query, OFFICIAL_SLA_URLS,
)
from app.api.routes.admin import _ingest_url_to_db, _get_model

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# HTML text extractor (reused for parse-web)
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "nav", "header", "footer", "noscript", "aside", "form"}

    def __init__(self):
        super().__init__()
        self._depth = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag, _):
        if tag in self.SKIP:
            self._depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._depth > 0:
            self._depth -= 1

    def handle_data(self, data):
        if not self._depth and data.strip():
            self.chunks.append(data.strip())


@router.post("/search/sla", response_model=SLASearchResponse)
async def search_sla_web(req: SLASearchRequest):
    """
    Search for SLA documents matching the query.
    Tries DuckDuckGo first; falls back to curated official links when DDG is blocked.
    """
    ddg_results = _try_ddg_search(req.query, req.max_results)
    info: str | None = None

    if ddg_results:
        results = ddg_results
    else:
        provider_key = _detect_provider_from_query(req.query)
        if provider_key:
            results = OFFICIAL_SLA_URLS.get(provider_key, [])[:req.max_results]
            info = "Live web search unavailable — showing curated official SLA links."
        else:
            results = []
            info = "No results found. Try a provider name like AWS, Azure, GCP, Oracle, or IBM."

    return SLASearchResponse(
        query=req.query,
        results=[SLASearchResult(**r) for r in results],
        total=len(results),
        info=info,
    )


@router.post("/search/ingest-selected", response_model=BatchIngestResponse)
async def ingest_selected_urls(req: IngestSelectedRequest, db: AsyncSession = Depends(get_db)):
    """
    Batch-ingest a user-selected subset of URLs from search results.
    Returns per-URL results — partial failures don't abort the whole batch.
    """
    model = _get_model()
    results: list[BatchIngestResult] = []

    for url in req.urls:
        try:
            data = await _ingest_url_to_db(url, req.provider, db, model, service_category=req.service_category)
            results.append(BatchIngestResult(url=url, chunks_created=data["chunks_created"]))
        except Exception as e:
            logger.warning("Failed to ingest %s: %s", url, e)
            results.append(BatchIngestResult(url=url, error=str(e)))

    return BatchIngestResponse(results=results)


@router.post("/search/auto-fetch", response_model=AutoFetchResponse)
async def auto_fetch_sla(req: AutoFetchRequest, db: AsyncSession = Depends(get_db)):
    """
    Auto-discover and ingest the top 3 SLA documents for a query or provider.
    Called when the user opts in after a no-result or empty-docs warning.
    """
    model = _get_model()

    # Build a list of (result_dict, provider_name) tuples to ingest
    to_ingest: list[tuple[dict, str]] = []

    if req.provider:
        results = discover_provider_slas(req.provider, max_results=5)
        top = sorted(results, key=lambda r: (r["is_pdf"], r["relevance_score"]), reverse=True)[:3]
        to_ingest = [(r, req.provider) for r in top]
    else:
        results = search_sla_documents(req.query, max_results=10)
        if results:
            top = sorted(results, key=lambda r: (r["is_pdf"], r["relevance_score"]), reverse=True)[:5]
            # Route each result to the provider whose official domain matches.
            # Drop results that don't match any known provider rather than
            # dumping them onto a fake "Unknown" bucket.
            domain_map = [
                ("aws.amazon.com",        "AWS"),
                ("amazon.com",            "AWS"),
                ("azure.microsoft.com",   "Azure"),
                ("microsoft.com",         "Azure"),
                ("cloud.google.com",      "GCP"),
                ("google.com",            "GCP"),
                ("oracle.com",            "Oracle"),
                ("ibm.com",               "IBM"),
            ]
            for r in top:
                url_lower = r["url"].lower()
                matched = next((name for dom, name in domain_map if dom in url_lower), None)
                if matched:
                    to_ingest.append((r, matched))
                else:
                    logger.info("Skipping non-provider URL in auto-fetch: %s", r["url"])
        else:
            # DDG blocked and no provider keyword detected — bootstrap from curated official URLs
            # (one best URL per provider so we seed the DB for all 5 providers at once)
            provider_map = {"aws": "AWS", "azure": "Azure", "gcp": "GCP", "oracle": "Oracle", "ibm": "IBM"}
            for key, name in provider_map.items():
                urls = OFFICIAL_SLA_URLS.get(key, [])
                if urls:
                    best = max(urls, key=lambda r: r["relevance_score"])
                    to_ingest.append((best, name))

    ingested = 0
    for r, prov_name in to_ingest:
        try:
            await _ingest_url_to_db(r["url"], prov_name, db, model)
            ingested += 1
        except Exception as e:
            logger.warning("Auto-fetch ingest failed for %s: %s", r["url"], e)

    provider_label = req.provider or "all major cloud providers"
    if ingested:
        msg = (
            f"Fetched and ingested {ingested} SLA document(s) from official sources for {provider_label}. "
            "Re-running your query now."
        )
    else:
        msg = (
            "Could not automatically fetch SLA documents. "
            "Try using the Discover tab to search and ingest manually."
        )

    return AutoFetchResponse(ingested=ingested, message=msg)


@router.post("/search/parse-web", response_model=ParseWebResponse)
async def parse_web_sla(req: ParseWebRequest, db: AsyncSession = Depends(get_db)):
    """
    Fetch an HTML/PDF URL, extract SLA text, ingest into ChromaDB + DB,
    and return an LLM-generated summary. Used when a provider (e.g. GCP)
    does not offer a downloadable PDF but has an HTML SLA page.
    """
    from app.services.llm_router import llm_router

    # 1 — Fetch the page
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; CloudSLA-Recommender/1.0)"}
        request = urllib.request.Request(req.url, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
    except Exception as e:
        return ParseWebResponse(
            summary="",
            ingested=False,
            error=f"Could not fetch the page: {e}",
        )

    # 2 — Extract text
    is_pdf = "pdf" in content_type.lower() or req.url.lower().endswith(".pdf")
    if is_pdf:
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name
        try:
            from app.services.ingestion import extract_text_from_pdf
            pages = extract_text_from_pdf(tmp_path)
            full_text = " ".join(p["text"] for p in pages[:15])
        except Exception as e:
            return ParseWebResponse(summary="", ingested=False, error=f"PDF parse error: {e}")
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
    else:
        ex = _TextExtractor()
        ex.feed(raw.decode("utf-8", errors="replace"))
        full_text = "\n".join(ex.chunks)

    if len(full_text.strip()) < 100:
        return ParseWebResponse(
            summary="",
            ingested=False,
            error="Page content too short or could not be parsed.",
        )

    # 3 — Ingest into DB + ChromaDB
    chunks_created = 0
    ingested = False
    try:
        model = _get_model()
        result = await _ingest_url_to_db(req.url, req.provider, db, model)
        chunks_created = result.get("chunks_created", 0)
        ingested = True
    except Exception as e:
        logger.warning("Ingest failed for %s: %s", req.url, e)

    # 4 — Extract structured metrics via LLM
    metrics: dict | None = None
    try:
        metrics = llm_router.extract_sla_metrics(full_text[:30000])
    except Exception:
        pass

    # 5 — Generate human-readable summary via LLM
    try:
        provider_ctx = {"name": req.provider, "url": req.url, **(metrics or {})}
        summary = llm_router.generate_explanation(
            query=f"Summarise the SLA terms for {req.provider}",
            provider=provider_ctx,
            all_providers=[provider_ctx],
            lang="English",
        )
        # Prepend a structured metrics block if extraction succeeded
        if metrics:
            lines = [f"**{req.provider} SLA Summary** (parsed from {req.url})\n"]
            if metrics.get("uptime_sla_pct"):
                lines.append(f"• Uptime SLA: {metrics['uptime_sla_pct']}%")
            if metrics.get("rto_hours"):
                lines.append(f"• RTO: {metrics['rto_hours']} hrs")
            if metrics.get("rpo_hours"):
                lines.append(f"• RPO: {metrics['rpo_hours']} hrs")
            if metrics.get("support_response_min"):
                lines.append(f"• Support Response: {metrics['support_response_min']} min")
            if metrics.get("penalty_credit_pct"):
                lines.append(f"• Penalty Credit: {metrics['penalty_credit_pct']}%")
            if metrics.get("compliance"):
                lines.append(f"• Compliance: {', '.join(metrics['compliance'])}")
            if metrics.get("regions"):
                lines.append(f"• Regions: {', '.join(metrics['regions'][:5])}")
            lines.append(f"\n{summary}")
            summary = "\n".join(lines)
    except Exception as e:
        summary = (
            f"Page fetched and ingested ({chunks_created} chunks). "
            f"LLM summary unavailable: {e}"
        )

    return ParseWebResponse(
        summary=summary,
        metrics=metrics,
        ingested=ingested,
        chunks_created=chunks_created,
    )
