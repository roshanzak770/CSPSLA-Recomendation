"""
POST /api/ask — RAG Q&A over ingested SLA documents
"""

from fastapi import APIRouter
from app.core.schemas import AskRequest, AskResponse
from app.services.ingestion import search_sla
from app.services.llm_router import llm_router

router = APIRouter()


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

    try:
        response = llm_router.reasoner.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a cloud SLA expert. Answer questions in plain English using "
                        "only the provided SLA excerpts. Write 3-5 bullet points maximum. "
                        "Cite page numbers like (Azure, p.11). Never copy legal text verbatim. "
                        "Stop immediately after answering — do not add examples or new questions."
                    ),
                },
                {"role": "user", "content": f"SLA Excerpts:\n{context}\n\nQuestion: {req.question}"},
            ],
            max_tokens=350,
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

    sources = [
        {"provider": c["provider"], "page": c["page_number"], "score": round(c["score"], 3), "text": c["text"]}
        for c in chunks[:3]
    ]

    return AskResponse(answer=answer, sources=sources)
