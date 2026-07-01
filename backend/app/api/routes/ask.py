"""
POST /api/ask — RAG Q&A over ingested SLA documents
"""

from fastapi import APIRouter
from app.core.schemas import AskRequest, AskResponse
from app.services.ingestion import search_sla
from app.services.llm_router import llm_router
from app.services.service_catalog import services_for, SERVICE_CATEGORIES

router = APIRouter()

# Curated official SLA pages — used as a fallback when the chunk's
# source_file is a local PDF path (not a public URL) so the Chat tab
# always has something clickable. Mirrors _OFFICIAL_SLA_URL in query.py.
_OFFICIAL_SLA_URL: dict[str, str] = {
    "AWS":    "https://aws.amazon.com/legal/service-level-agreements/",
    "Azure":  "https://azure.microsoft.com/en-us/support/legal/sla/summary/",
    "GCP":    "https://cloud.google.com/terms/sla",
    "Oracle": "https://www.oracle.com/cloud/sla/",
    "IBM":    "https://www.ibm.com/support/customer/csol/terms/?id=i126-6605&lc=en",
}


def _source_link(provider: str | None, source_file: str | None) -> str | None:
    """Resolve a clickable URL for a Chat source.

    Priority:
      1. If source_file is already an http(s) URL → return it as-is.
      2. Otherwise fall back to the vendor's official SLA hub URL.
      3. None if neither is available (UI degrades to a non-link label).
    """
    if source_file and source_file.startswith(("http://", "https://")):
        return source_file
    if provider:
        return _OFFICIAL_SLA_URL.get(provider.strip())
    return None


def _catalog_context(provider: str | None, category: str | None) -> str:
    """Build a short text block summarising the curated services this
    provider offers in the requested category. Injected into the LLM prompt
    so the answer can cite authoritative SLA numbers even when no PDF
    chunks match the user's query. Returns "" when no curated entry exists.
    """
    if not provider or not category:
        return ""
    svcs = services_for(category, provider)
    if not svcs:
        return ""
    lines = [f"Curated {category} services from {provider} (per vendor's public SLA pages):"]
    for s in svcs:
        bits = [s["name"]]
        if s.get("uptime_sla_pct") is not None:
            bits.append(f"uptime {s['uptime_sla_pct']}%")
        if s.get("rto_hours") is not None:
            bits.append(f"RTO {s['rto_hours']}h")
        if s.get("rpo_hours") is not None:
            bits.append(f"RPO {s['rpo_hours']}h")
        if s.get("penalty_credit_pct") is not None:
            bits.append(f"credit {s['penalty_credit_pct']}%")
        lines.append("  - " + " · ".join(bits))
    return "\n".join(lines)


@router.post("/ask", response_model=AskResponse)
def ask_sla(req: AskRequest):
    provider_filter = [req.provider] if req.provider else None
    category = (req.service_category or None)
    if category:
        category = category.strip().lower() or None
        # Reject unknown categories silently — frontend dropdown should
        # only offer known ones, but be defensive against bad clients.
        if category not in SERVICE_CATEGORIES:
            category = None

    # ─── Cascade search ──────────────────────────────────────────────────
    # 1) Try the most specific filter: provider + category.
    # 2) Fall back to provider-only with a heads-up note.
    # 3) Fall back to unfiltered (rare) with an even broader note.
    info: str | None = None
    chunks: list[dict] = []
    if category and req.provider:
        chunks = search_sla(req.question, provider_filter=provider_filter,
                            top_k=5, service_category=category)
        if not chunks:
            info = (
                f"No {category}-specific SLA excerpts have been ingested for "
                f"{req.provider} yet — showing the general {req.provider} SLA "
                f"content instead. Tag a document with the '{category}' "
                f"category in Add SLA Docs to make this filter exact."
            )
    if not chunks:
        chunks = search_sla(req.question, provider_filter=provider_filter, top_k=5)
    if not chunks and req.provider:
        info = (
            f"No ingested SLA content matched {req.provider}. Falling back to "
            "any matching provider — ingest a document for this provider for "
            "a precise answer."
        )
        chunks = search_sla(req.question, top_k=5)

    # Curated catalog facts — surfaced to the LLM as an authoritative
    # supplement so the Chat answer is useful even when ingestion is empty
    # for this provider/category combination.
    catalog_text = _catalog_context(req.provider, category)

    if not chunks and not catalog_text:
        return AskResponse(
            answer="No relevant SLA content found. Please ingest an SLA document first, or pick a different provider/category combination.",
            sources=[],
            info=info,
        )

    top_chunks = chunks[:3]
    excerpt_block = "\n\n".join(
        f"Source {i+1} ({c['provider']}, p.{c['page_number']}): {c['text']}"
        for i, c in enumerate(top_chunks)
    ) or "(no ingested SLA excerpts available — answer from the curated catalog alone)"

    lang = req.lang or "English"
    scope_line = ""
    if req.provider and category:
        scope_line = f"User has scoped this question to {req.provider} → {category}. Prioritise that scope.\n"
    elif req.provider:
        scope_line = f"User has scoped this question to {req.provider}. Prioritise that provider.\n"

    try:
        response = llm_router.reasoner.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a cloud SLA expert. Answer the user's question thoroughly using "
                        "the provided SLA excerpts and the curated catalog facts. Structure your "
                        "answer with clear bullet points or short paragraphs — use as many as the "
                        "question requires, do not artificially limit yourself. If the excerpts "
                        "contain multiple relevant clauses, surface all of them. Cite page numbers "
                        "like (Azure, p.11) inline when the source is a PDF excerpt. Curated catalog "
                        "values can be cited as (vendor catalog). Never copy legal text verbatim — "
                        "paraphrase. Stop after you have fully answered — do not invent examples or "
                        "new questions. "
                        f"IMPORTANT: You MUST respond entirely in {lang}. "
                        f"Even if the question is in a different language, answer in {lang}."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        scope_line
                        + (f"{catalog_text}\n\n" if catalog_text else "")
                        + f"SLA Excerpts:\n{excerpt_block}\n\n"
                        + f"Question: {req.question}"
                    ),
                },
            ],
            max_tokens=900,
            temperature=0.2,
            stop=["Question:", "\nQuestion", "SLA Excerpts:"],
        )
        answer = response.choices[0].message.content.strip()
    except Exception:
        lines = []
        for c in chunks[:3]:
            text = " ".join(c['text'].split())[:300]
            lines.append(f"**{c['provider']}** (p.{c['page_number']}):\n{text}")
        answer = (
            "The LLM is currently unavailable, but here's what the SLA documents say:\n\n"
            + "\n\n".join(lines)
            + "\n\n*Full AI summary will appear once the language model is reachable.*"
        )

    sources = []
    for c in chunks[:3]:
        provider = c.get("provider")
        page = c.get("page_number")
        source_file = c.get("source_file")
        url = _source_link(provider, source_file)
        if source_file and source_file.startswith(("http://", "https://")):
            title = source_file
        else:
            title = f"{provider} — page {page}" if provider and page else (provider or "Source")
        sources.append({
            "provider":         provider,
            "page":             page,
            "score":            round(c["score"], 3),
            "text":             c["text"],
            "url":              url,
            "title":            title,
            "service_category": c.get("service_category"),
        })

    return AskResponse(answer=answer, sources=sources, info=info)
