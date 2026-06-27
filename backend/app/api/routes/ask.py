"""
POST /api/ask — RAG Q&A over ingested SLA documents
"""

from fastapi import APIRouter
from app.core.schemas import AskRequest, AskResponse
from app.services.ingestion import search_sla
from app.services.llm_router import llm_router

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


@router.post("/ask", response_model=AskResponse)
def ask_sla(req: AskRequest):
    provider_filter = [req.provider] if req.provider else None
    chunks = search_sla(req.question, provider_filter=provider_filter, top_k=5)

    if not chunks:
        return AskResponse(
            answer="No relevant SLA content found. Please ingest an SLA document first.",
            sources=[],
        )

    top_chunks = chunks[:3]
    context = "\n\n".join(
        f"Source {i+1} ({c['provider']}, p.{c['page_number']}): {c['text']}"
        for i, c in enumerate(top_chunks)
    )

    lang = req.lang or "English"
    try:
        response = llm_router.reasoner.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a cloud SLA expert. Answer the user's question thoroughly using "
                        "the provided SLA excerpts. Structure your answer with clear bullet points "
                        "or short paragraphs — use as many as the question requires, do not artificially "
                        "limit yourself. If the excerpts contain multiple relevant clauses, surface all "
                        "of them. Cite page numbers like (Azure, p.11) inline. Never copy legal text "
                        "verbatim — paraphrase. Stop after you have fully answered — do not invent "
                        "examples or new questions. "
                        f"IMPORTANT: You MUST respond entirely in {lang}. "
                        f"Even if the question is in a different language, answer in {lang}."
                    ),
                },
                {"role": "user", "content": f"SLA Excerpts:\n{context}\n\nQuestion: {req.question}"},
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
        # Human-readable title shown in the Chat source pill. Prefer the
        # source URL (lets the user see where it came from); fall back to
        # "<Provider> (page N)" for PDFs that don't have a public URL.
        if source_file and source_file.startswith(("http://", "https://")):
            title = source_file
        else:
            title = f"{provider} — page {page}" if provider and page else (provider or "Source")
        sources.append({
            "provider": provider,
            "page":     page,
            "score":    round(c["score"], 3),
            "text":     c["text"],
            "url":      url,          # clickable link (None if no URL resolved)
            "title":    title,        # display label for the pill
        })

    return AskResponse(answer=answer, sources=sources)
