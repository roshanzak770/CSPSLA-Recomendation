"""
Web search agent for discovering SLA documents via DuckDuckGo (free, no API key).
Falls back to curated official SLA URLs when DDG is unavailable.
"""

import re
import time
import random
import logging
from threading import Lock

logger = logging.getLogger(__name__)

# In-memory cache: query → (timestamp, results)
# Avoids hammering DDG on every keystroke and survives transient rate-limits.
_DDG_CACHE: dict[str, tuple[float, list[dict]]] = {}
_DDG_CACHE_TTL_SEC = 900  # 15 minutes
_DDG_CACHE_LOCK = Lock()

# Canned queries per known provider for scheduled discovery
KNOWN_PROVIDERS: dict[str, list[str]] = {
    "AWS": [
        "AWS Amazon EC2 service level agreement SLA site:aws.amazon.com",
        "Amazon S3 SLA uptime guarantee site:aws.amazon.com",
        "Amazon RDS SLA availability site:aws.amazon.com",
    ],
    "Azure": [
        "Azure Virtual Machines SLA service level agreement site:microsoft.com",
        "Azure SQL Database SLA uptime site:microsoft.com",
        "Microsoft Azure storage SLA site:azure.microsoft.com",
    ],
    "GCP": [
        "Google Cloud Compute Engine SLA site:cloud.google.com",
        "Google Cloud SQL SLA availability site:cloud.google.com",
        "GCP Cloud Storage SLA uptime site:cloud.google.com",
    ],
    "Oracle": [
        "Oracle Cloud Infrastructure SLA service level agreement site:oracle.com",
        "Oracle Cloud uptime guarantee SLA site:oracle.com",
    ],
    "IBM": [
        "IBM Cloud SLA service level agreement site:ibm.com",
        "IBM Cloud uptime availability guarantee site:ibm.com",
    ],
}

# Curated official SLA URLs — guaranteed to exist even when DDG is blocked
OFFICIAL_SLA_URLS: dict[str, list[dict]] = {
    "aws": [
        {"title": "AWS Service Level Agreements (SLA) Index", "url": "https://aws.amazon.com/legal/service-level-agreements/", "snippet": "Official index of all Amazon Web Services SLA documents covering compute, storage, database, and more.", "is_pdf": False, "relevance_score": 5},
        {"title": "Amazon EC2 SLA", "url": "https://aws.amazon.com/compute/sla/", "snippet": "Amazon EC2 provides a Monthly Uptime Percentage of at least 99.99% for each AWS Region.", "is_pdf": False, "relevance_score": 5},
        {"title": "Amazon S3 SLA", "url": "https://aws.amazon.com/s3/sla/", "snippet": "Amazon S3 service level agreement with monthly uptime commitment and service credits.", "is_pdf": False, "relevance_score": 5},
        {"title": "Amazon RDS SLA", "url": "https://aws.amazon.com/rds/sla/", "snippet": "Amazon RDS multi-AZ SLA with 99.95% monthly uptime commitment.", "is_pdf": False, "relevance_score": 4},
        {"title": "AWS Lambda SLA", "url": "https://aws.amazon.com/lambda/sla/", "snippet": "AWS Lambda service level agreement with monthly uptime and service credit terms.", "is_pdf": False, "relevance_score": 4},
        {"title": "Amazon CloudFront SLA", "url": "https://aws.amazon.com/cloudfront/sla/", "snippet": "Amazon CloudFront CDN service level agreement and uptime commitments.", "is_pdf": False, "relevance_score": 4},
    ],
    "azure": [
        {"title": "Azure SLA Summary", "url": "https://azure.microsoft.com/en-us/support/legal/sla/summary/", "snippet": "Summary of all Microsoft Azure service level agreements for all products.", "is_pdf": False, "relevance_score": 5},
        {"title": "SLA for Azure Virtual Machines", "url": "https://azure.microsoft.com/en-us/support/legal/sla/virtual-machines/", "snippet": "Azure Virtual Machines SLA with 99.9%–99.99% uptime commitments depending on configuration.", "is_pdf": False, "relevance_score": 5},
        {"title": "SLA for Azure SQL Database", "url": "https://azure.microsoft.com/en-us/support/legal/sla/azure-sql-database/", "snippet": "Azure SQL Database SLA with 99.99% uptime guarantee.", "is_pdf": False, "relevance_score": 4},
        {"title": "SLA for Azure Blob Storage", "url": "https://azure.microsoft.com/en-us/support/legal/sla/storage/", "snippet": "Azure Blob Storage SLA providing 99.9% read/write availability.", "is_pdf": False, "relevance_score": 4},
        {"title": "Microsoft Online Services SLA (PDF)", "url": "https://www.microsoft.com/licensing/docs/view/Service-Level-Agreements-SLA-for-Online-Services", "snippet": "Consolidated Microsoft Online Services SLA document covering Azure, M365, and more.", "is_pdf": False, "relevance_score": 4},
    ],
    "gcp": [
        {"title": "Google Cloud SLA Overview", "url": "https://cloud.google.com/terms/sla", "snippet": "Overview of all Google Cloud service level agreements with links to individual service SLAs.", "is_pdf": False, "relevance_score": 5},
        {"title": "Google Compute Engine SLA", "url": "https://cloud.google.com/compute/sla", "snippet": "GCP Compute Engine SLA with 99.99% monthly uptime for regional instance groups.", "is_pdf": False, "relevance_score": 5},
        {"title": "Google Cloud Storage SLA", "url": "https://cloud.google.com/storage/sla", "snippet": "Cloud Storage SLA with 99.95%–99.99% uptime depending on storage class.", "is_pdf": False, "relevance_score": 4},
        {"title": "Google Cloud SQL SLA", "url": "https://cloud.google.com/sql/sla", "snippet": "Cloud SQL SLA with 99.95% uptime commitment for HA instances.", "is_pdf": False, "relevance_score": 4},
        {"title": "Google Kubernetes Engine SLA", "url": "https://cloud.google.com/kubernetes-engine/sla", "snippet": "GKE SLA with 99.95% uptime guarantee for regional clusters.", "is_pdf": False, "relevance_score": 4},
    ],
    "oracle": [
        {"title": "Oracle Cloud SLA", "url": "https://www.oracle.com/cloud/sla/", "snippet": "Oracle Cloud Infrastructure service level agreements with uptime and support commitments.", "is_pdf": False, "relevance_score": 5},
        {"title": "Oracle Cloud IaaS SLA", "url": "https://www.oracle.com/assets/paas-iaas-universal-credits-3940775.pdf", "snippet": "Oracle Cloud Infrastructure IaaS SLA PDF covering compute, storage, and network services.", "is_pdf": True, "relevance_score": 5},
        {"title": "Oracle Cloud Services Uptime Policy", "url": "https://www.oracle.com/cloud/iaas/sla-licensing-info/", "snippet": "Oracle Cloud Infrastructure SLA and licensing information.", "is_pdf": False, "relevance_score": 4},
    ],
    "ibm": [
        {"title": "IBM Cloud SLA", "url": "https://www.ibm.com/support/customer/csol/terms/?id=i126-6605&lc=en", "snippet": "IBM Cloud service level agreement terms covering uptime, availability, and remedies.", "is_pdf": False, "relevance_score": 5},
        {"title": "IBM SaaS Attachments / SLA Terms", "url": "https://www.ibm.com/support/customer/csol/terms/", "snippet": "IBM Cloud terms of service and SLA attachments for all cloud products.", "is_pdf": False, "relevance_score": 4},
        {"title": "IBM Cloud Platform SLA", "url": "https://www.ibm.com/support/pages/ibm-cloud-platform-service-level-agreement", "snippet": "IBM Cloud Platform SLA details including uptime commitments and credit terms.", "is_pdf": False, "relevance_score": 4},
    ],
}

# URL patterns that suggest an SLA document
_SLA_URL_PATTERNS = [
    r"sla", r"service.level", r"service_level", r"uptime", r"availability",
    r"legal", r"agreement", r"terms", r"policy",
]
_SLA_TITLE_PATTERNS = [
    r"sla", r"service level", r"uptime", r"availability guarantee",
    r"service agreement",
]


def _score_result(title: str, url: str) -> int:
    """Heuristic relevance score for a DDG result."""
    score = 0
    url_lower = url.lower()
    title_lower = title.lower()
    if url_lower.endswith(".pdf"):
        score += 3
    for pat in _SLA_URL_PATTERNS:
        if re.search(pat, url_lower):
            score += 2
            break
    for pat in _SLA_TITLE_PATTERNS:
        if re.search(pat, title_lower):
            score += 1
            break
    official_domains = [
        "aws.amazon.com", "microsoft.com", "azure.microsoft.com",
        "cloud.google.com", "oracle.com", "ibm.com",
    ]
    if any(d in url_lower for d in official_domains):
        score += 2
    return score


def _detect_provider_from_query(query: str) -> str | None:
    """Map a search query string to a known provider key (lowercase)."""
    q = query.lower()
    if any(k in q for k in ["aws", "amazon"]):
        return "aws"
    if any(k in q for k in ["azure", "microsoft"]):
        return "azure"
    if any(k in q for k in ["gcp", "google cloud", "gcloud", "google"]):
        return "gcp"
    if "oracle" in q:
        return "oracle"
    if "ibm" in q:
        return "ibm"
    return None


def _ddg_text_search(query: str, max_results: int) -> list[dict]:
    """Single DDG call. Imports the new `ddgs` package, falling back to the
    legacy `duckduckgo_search` name if only the old version is installed."""
    DDGS = None
    try:
        from ddgs import DDGS  # new package name (2025+)
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # legacy fallback
        except ImportError:
            logger.warning("Neither 'ddgs' nor 'duckduckgo_search' installed — DDG search unavailable.")
            return []

    ddgs = DDGS()
    return list(ddgs.text(query, max_results=max_results))


def _try_ddg_search(query: str, max_results: int) -> list[dict]:
    """Attempt a DuckDuckGo search with caching + retry-on-ratelimit.
    Returns [] only after every retry has failed."""
    cache_key = f"{query.strip().lower()}|{max_results}"

    # 1 — Cache hit?
    with _DDG_CACHE_LOCK:
        entry = _DDG_CACHE.get(cache_key)
        if entry and (time.time() - entry[0]) < _DDG_CACHE_TTL_SEC:
            logger.info("DDG cache hit for '%s'", query)
            return entry[1]

    # 2 — Live search with up-to-3 attempts and exponential-with-jitter backoff
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            raw_results = _ddg_text_search(query, max_results)
            break
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            is_rate_limited = "ratelimit" in msg or "202" in msg or "429" in msg
            if attempt < 2 and is_rate_limited:
                sleep_s = (1.5 ** attempt) + random.uniform(0.2, 0.8)
                logger.info("DDG rate-limited (attempt %d) — backing off %.1fs", attempt + 1, sleep_s)
                time.sleep(sleep_s)
                continue
            logger.warning("DDG search failed for query '%s': %s", query, e)
            return []
    else:
        logger.warning("DDG search exhausted retries for '%s': %s", query, last_err)
        return []

    # 3 — Normalise + score
    results = []
    for r in raw_results:
        url = r.get("href") or r.get("url") or ""
        title = r.get("title", "")
        snippet = r.get("body") or r.get("description") or ""
        score = _score_result(title, url)
        results.append({
            "title": title,
            "url": url,
            "snippet": snippet,
            "is_pdf": url.lower().endswith(".pdf"),
            "relevance_score": score,
        })

    results.sort(key=lambda x: x["relevance_score"], reverse=True)

    # 4 — Cache successful result (only non-empty, to allow quick recovery)
    if results:
        with _DDG_CACHE_LOCK:
            _DDG_CACHE[cache_key] = (time.time(), results)

    return results


def search_sla_documents(query: str, max_results: int = 10) -> list[dict]:
    """
    Search for SLA documents matching the query.
    Tries DuckDuckGo first; falls back to curated official SLA links when DDG
    is unavailable (rate-limited, blocked in Docker, or not installed).
    Each result: {title, url, snippet, is_pdf, relevance_score}
    """
    results = _try_ddg_search(query, max_results)

    if not results:
        provider_key = _detect_provider_from_query(query)
        if provider_key:
            results = OFFICIAL_SLA_URLS.get(provider_key, [])[:max_results]
            logger.info("DDG unavailable — returning %d curated results for '%s'", len(results), provider_key)

    return results


def discover_provider_slas(provider_name: str, extra_query: str = "", max_results: int = 8) -> list[dict]:
    """
    Run canned queries for a known provider (or build one from provider_name).
    Deduplicates by URL. Returns scored + sorted results.
    """
    queries = KNOWN_PROVIDERS.get(provider_name, [
        f"{provider_name} cloud SLA service level agreement",
        f"{provider_name} cloud uptime guarantee",
    ])
    if extra_query:
        queries = [extra_query] + queries

    seen_urls: set[str] = set()
    all_results: list[dict] = []

    for q in queries[:3]:  # cap at 3 queries per provider to avoid rate limits
        for r in search_sla_documents(q, max_results=5):
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                all_results.append(r)
        time.sleep(1)  # polite delay between queries

    all_results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return all_results[:max_results]


def discover_all_known_providers(max_per_provider: int = 5) -> dict[str, list[dict]]:
    """
    Run discovery for every known provider.
    Returns {provider_name: [results]}.
    Used by the scheduled Celery task.
    """
    output: dict[str, list[dict]] = {}
    for provider_name in KNOWN_PROVIDERS:
        logger.info("Discovering SLA docs for %s…", provider_name)
        try:
            results = discover_provider_slas(provider_name, max_results=max_per_provider)
            output[provider_name] = results
        except Exception as e:
            logger.warning("Discovery failed for %s: %s", provider_name, e)
            output[provider_name] = []
        time.sleep(2)  # polite delay between providers
    return output
