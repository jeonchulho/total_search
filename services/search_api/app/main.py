import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from starlette.concurrency import run_in_threadpool

from .milvus_store import MilvusStore
from .schemas import IndexDocumentRequest, SearchHit, SearchRequest, SearchResponse
from .security import require_api_key
from .settings import settings
from .vectorizer import (
    chunk_text,
    embed_text_by_provider,
    embed_texts_by_provider,
    ensure_embedding_enabled,
    get_embedding_metrics,
    validate_vector_dimension,
)

store = MilvusStore()
embedding_semaphore = asyncio.Semaphore(max(1, settings.embedding_max_concurrency))


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.connect()
    yield


app = FastAPI(title="Total Search API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics/embedding", dependencies=[Depends(require_api_key)])
async def embedding_metrics() -> dict[str, object]:
    return get_embedding_metrics()


@app.post("/index", dependencies=[Depends(require_api_key)])
async def index_document(payload: IndexDocumentRequest) -> dict[str, str | int]:
    chunks = chunk_text(payload.text)
    try:
        ensure_embedding_enabled(settings.embedding_enabled)
        async with embedding_semaphore:
            vectors = await run_in_threadpool(embed_texts_by_provider, chunks, settings.vector_dim)
        for vector in vectors:
            validate_vector_dimension(vector, settings.vector_dim)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    count = store.upsert_chunks(
        document_id=payload.document_id,
        title=payload.title,
        source_path=payload.source_path,
        metadata=payload.metadata,
        chunks=chunks,
        vectors=vectors,
    )
    return {"document_id": payload.document_id, "indexed_chunks": count}


@app.post("/search", response_model=SearchResponse, dependencies=[Depends(require_api_key)])
async def search(payload: SearchRequest) -> SearchResponse:
    try:
        ensure_embedding_enabled(settings.embedding_enabled)
        async with embedding_semaphore:
            qvec = await run_in_threadpool(embed_text_by_provider, payload.query, settings.vector_dim)
        validate_vector_dimension(qvec, settings.vector_dim)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    raw_hits = store.search(qvec, top_k=payload.top_k)
    hits = [SearchHit(**item) for item in raw_hits]
    return SearchResponse(query=payload.query, hits=hits)
