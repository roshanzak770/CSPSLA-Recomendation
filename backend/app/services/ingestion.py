"""
SLA Document Ingestion Pipeline.

PDF → text extraction → chunking → embedding → ChromaDB storage
"""

import hashlib
import time
from pathlib import Path
from typing import List

import chromadb
import fitz  # PyMuPDF
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

from app.core.config import settings

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
EMBEDDING_MODEL = "intfloat/multilingual-e5-base"

_model_cache = None
_chroma_client_cache = None


class EmptyDocumentError(ValueError):
    """Raised when a PDF (or other source) yields no extractable text.

    Most commonly: scanned/image-only PDFs with no OCR text layer. The
    upload route should catch this and translate to a clear HTTP 422
    rather than letting it bubble into a 500.
    """


def _get_chroma_client() -> chromadb.HttpClient:
    global _chroma_client_cache
    if _chroma_client_cache is None:
        _chroma_client_cache = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    return _chroma_client_cache


def _get_embedding_model() -> SentenceTransformer:
    global _model_cache
    if _model_cache is None:
        _model_cache = SentenceTransformer(EMBEDDING_MODEL)
    return _model_cache


def extract_text_from_pdf(pdf_path: str) -> List[dict]:
    """
    Extract text from each page of a PDF.
    Returns list of {"page_number": int, "text": str}.
    """
    pages = []
    doc = fitz.open(pdf_path)
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        if text:
            pages.append({"page_number": page_num, "text": text})
    doc.close()
    return pages


def chunk_pages(pages: List[dict]) -> List[dict]:
    """
    Split page texts into overlapping chunks.
    Returns list of {"chunk_text": str, "page_number": int, "chunk_index": int}.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " "],
    )
    chunks = []
    chunk_index = 0
    for page in pages:
        splits = splitter.split_text(page["text"])
        for split in splits:
            chunks.append({
                "chunk_text": split,
                "page_number": page["page_number"],
                "chunk_index": chunk_index,
            })
            chunk_index += 1
    return chunks


def embed_and_store(
    provider_name: str,
    document_id: str,
    source_file: str,
    chunks: List[dict],
    model: SentenceTransformer,
) -> List[str]:
    """
    Embed chunks and upsert into ChromaDB.
    Returns list of ChromaDB chunk IDs.
    """
    # Defensive: SentenceTransformer.encode([]) crashes with IndexError on
    # `all_embeddings[0].dtype` inside the library. Caller must surface a
    # meaningful error (e.g. scanned PDF → no extractable text); we just
    # return an empty list here so the failure is loud at the API layer.
    if not chunks:
        return []

    client = _get_chroma_client()
    collection = client.get_or_create_collection(
        name="sla_documents",
        metadata={"hnsw:space": "cosine"},
    )

    texts = [c["chunk_text"] for c in chunks]
    # multilingual-e5 expects "passage: " prefix for indexing
    prefixed = [f"passage: {t}" for t in texts]
    embeddings = model.encode(prefixed, batch_size=32, show_progress_bar=False).tolist()

    ids = [
        f"{provider_name.lower()}_{document_id}_{c['chunk_index']}"
        for c in chunks
    ]
    metadatas = [
        {
            "provider": provider_name,
            "document_id": document_id,
            "source_file": source_file,
            "page_number": c["page_number"],
            "chunk_index": c["chunk_index"],
        }
        for c in chunks
    ]

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )
    return ids


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def ingest_pdf(
    provider_name: str,
    document_id: str,
    pdf_path: str,
    model: SentenceTransformer | None = None,
) -> dict:
    """
    Full ingestion pipeline for one SLA PDF.
    Returns {"chunks_created": int, "embedding_time_sec": float, "file_hash": str}.
    """
    if model is None:
        model = _get_embedding_model()

    pages = extract_text_from_pdf(pdf_path)
    chunks = chunk_pages(pages)

    # Reject scanned/image-only PDFs (no extractable text layer) before
    # we attempt to embed an empty list — SentenceTransformer crashes on
    # that, and the caller would only see a generic 500.
    if not chunks:
        raise EmptyDocumentError(
            "PDF contains no extractable text. This usually means it is a "
            "scanned image (no OCR text layer). Try saving it as a "
            "searchable PDF, or paste the text manually."
        )

    start = time.time()
    chunk_ids = embed_and_store(
        provider_name=provider_name,
        document_id=document_id,
        source_file=Path(pdf_path).name,
        chunks=chunks,
        model=model,
    )
    elapsed = time.time() - start

    return {
        "chunks_created": len(chunk_ids),
        "embedding_time_sec": round(elapsed, 2),
        "file_hash": sha256_file(pdf_path),
    }


def search_sla(
    query: str,
    provider_filter: List[str] | None = None,
    top_k: int = 5,
    model: SentenceTransformer | None = None,
) -> List[dict]:
    """
    Semantic search over SLA chunks.
    Returns list of {"text": str, "provider": str, "page_number": int, "score": float}.
    """
    if model is None:
        model = _get_embedding_model()

    client = _get_chroma_client()
    collection = client.get_or_create_collection(name="sla_documents")

    total = collection.count()
    if total == 0:
        return []

    # multilingual-e5 expects "query: " prefix for queries
    embedding = model.encode([f"query: {query}"], show_progress_bar=False).tolist()

    where = {"provider": {"$in": provider_filter}} if provider_filter else None

    results = collection.query(
        query_embeddings=embedding,
        n_results=min(top_k, total),
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    output = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        output.append({
            "text": doc,
            "provider": meta.get("provider"),
            "page_number": meta.get("page_number"),
            "source_file": meta.get("source_file"),   # original URL or filename
            "score": float(1 - dist),  # cosine similarity from distance
        })
    return output
