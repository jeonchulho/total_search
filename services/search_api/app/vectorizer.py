import hashlib
import threading
import time
from typing import Any

import httpx
import numpy as np

from .settings import settings

_metrics_lock = threading.Lock()
_embedding_metrics: dict[str, Any] = {
    "total_calls": 0,
    "total_texts": 0,
    "total_duration_ms": 0.0,
    "providers": {},
}


def _normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


def embed_text(text: str, dim: int) -> list[float]:
    """Deterministic lightweight embedding for MVP/demo use."""
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    repeats = (dim * 4 // len(seed)) + 1
    raw = (seed * repeats)[: dim * 4]
    arr = np.frombuffer(raw, dtype=np.uint32).astype(np.float32)
    arr = (arr % 1000) / 1000.0
    arr = (arr * 2.0) - 1.0
    return _normalize(arr).tolist()


def _embed_text_openai(text: str) -> list[float]:
    return _embed_texts_openai([text])[0]


def _embed_texts_openai(texts: list[str]) -> list[list[float]]:
    if not settings.embedding_api_key:
        raise ValueError("EMBEDDING_API_KEY is required when EMBEDDING_PROVIDER=openai")

    endpoint = settings.embedding_api_base.rstrip("/") + "/embeddings"
    payload: dict[str, Any] = {
        "model": settings.embedding_model,
        "input": texts,
    }
    headers = {
        "Authorization": f"Bearer {settings.embedding_api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=settings.embedding_timeout_sec) as client:
        response = client.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()

    data = body.get("data")
    if not data:
        raise ValueError("Invalid embedding response: missing data")
    ordered = sorted(data, key=lambda item: item.get("index", 0))
    embeddings: list[list[float]] = []
    for item in ordered:
        embedding = item.get("embedding")
        if not embedding:
            raise ValueError("Invalid embedding response: missing embedding")
        embeddings.append(embedding)
    return embeddings


def _embed_text_sentence_transformers(text: str) -> list[float]:
    return _embed_texts_sentence_transformers([text])[0]


def _embed_texts_sentence_transformers(texts: list[str]) -> list[list[float]]:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise ValueError(
            "sentence-transformers is not installed. Install it and set EMBEDDING_PROVIDER=sentence_transformers"
        ) from exc

    # Keep model cached on function for repeated calls.
    model = getattr(_embed_text_sentence_transformers, "_model", None)
    if model is None:
        model = SentenceTransformer(settings.embedding_model)
        setattr(_embed_text_sentence_transformers, "_model", model)

    vectors = model.encode(texts, normalize_embeddings=True)
    return vectors.tolist()


def _get_bge_runtime() -> tuple[Any, Any, str, Any]:
    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
    except ImportError as exc:
        raise ValueError(
            "BGE provider requires torch and transformers. Install dependencies and set EMBEDDING_PROVIDER=bge_m3"
        ) from exc

    runtime = getattr(_get_bge_runtime, "_runtime", None)
    model_name = settings.embedding_bge_model or "BAAI/bge-m3"
    device = settings.embedding_device

    if runtime is None or runtime[2] != model_name or runtime[3] != device:
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModel.from_pretrained(model_name)
        model.to(device)
        model.eval()
        runtime = (tokenizer, model, model_name, device, torch)
        setattr(_get_bge_runtime, "_runtime", runtime)

    tokenizer, model, _, model_device, torch_mod = runtime
    return tokenizer, model, model_device, torch_mod


def _mean_pool(last_hidden_state: Any, attention_mask: Any, torch_mod: Any) -> Any:
    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    token_embeddings = last_hidden_state * mask
    summed = token_embeddings.sum(dim=1)
    counts = torch_mod.clamp(mask.sum(dim=1), min=1e-9)
    return summed / counts


def _embed_text_bge_m3(text: str) -> list[float]:
    return _embed_texts_bge_m3([text])[0]


def _embed_texts_bge_m3(texts: list[str]) -> list[list[float]]:
    tokenizer, model, device, torch_mod = _get_bge_runtime()

    vectors: list[list[float]] = []
    batch_size = _effective_batch_size(provider="bge_m3", texts=texts)
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        inputs = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=settings.embedding_max_length,
            return_tensors="pt",
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch_mod.no_grad():
            outputs = model(**inputs)
            sentence_embedding = _mean_pool(outputs.last_hidden_state, inputs["attention_mask"], torch_mod)
            sentence_embedding = torch_mod.nn.functional.normalize(sentence_embedding, p=2, dim=1)

        vectors.extend(sentence_embedding.cpu().tolist())

    return vectors


def _effective_batch_size(provider: str, texts: list[str]) -> int:
    requested = max(1, settings.embedding_batch_size)
    if not texts:
        return requested

    if provider != "bge_m3" or not settings.embedding_auto_batch:
        return min(requested, len(texts))

    avg_chars = sum(len(t) for t in texts) / len(texts)
    if settings.embedding_device.lower() != "cpu":
        auto_cap = 32
    elif avg_chars > 1200:
        auto_cap = 4
    elif avg_chars > 600:
        auto_cap = 8
    elif avg_chars > 300:
        auto_cap = 12
    else:
        auto_cap = 16

    return max(1, min(requested, auto_cap, len(texts)))


def _record_embedding_metrics(provider: str, text_count: int, duration_ms: float) -> None:
    with _metrics_lock:
        _embedding_metrics["total_calls"] += 1
        _embedding_metrics["total_texts"] += text_count
        _embedding_metrics["total_duration_ms"] += duration_ms

        providers = _embedding_metrics["providers"]
        row = providers.get(provider)
        if row is None:
            row = {"calls": 0, "texts": 0, "duration_ms": 0.0}
            providers[provider] = row
        row["calls"] += 1
        row["texts"] += text_count
        row["duration_ms"] += duration_ms


def get_embedding_metrics() -> dict[str, Any]:
    with _metrics_lock:
        total_calls = _embedding_metrics["total_calls"]
        total_texts = _embedding_metrics["total_texts"]
        total_duration_ms = _embedding_metrics["total_duration_ms"]

        providers_out: dict[str, Any] = {}
        for provider, row in _embedding_metrics["providers"].items():
            calls = row["calls"]
            texts = row["texts"]
            duration = row["duration_ms"]
            providers_out[provider] = {
                "calls": calls,
                "texts": texts,
                "duration_ms": round(duration, 3),
                "avg_call_ms": round(duration / calls, 3) if calls else 0.0,
                "avg_text_ms": round(duration / texts, 3) if texts else 0.0,
            }

        return {
            "total_calls": total_calls,
            "total_texts": total_texts,
            "total_duration_ms": round(total_duration_ms, 3),
            "avg_call_ms": round(total_duration_ms / total_calls, 3) if total_calls else 0.0,
            "avg_text_ms": round(total_duration_ms / total_texts, 3) if total_texts else 0.0,
            "providers": providers_out,
        }


def embed_text_by_provider(text: str, dim: int) -> list[float]:
    return embed_texts_by_provider([text], dim)[0]


def embed_texts_by_provider(texts: list[str], dim: int) -> list[list[float]]:
    if not texts:
        return []

    provider = settings.embedding_provider.lower().strip()
    started = time.perf_counter()
    if provider == "hash":
        vectors = [embed_text(text, dim) for text in texts]
    elif provider == "openai":
        vectors = _embed_texts_openai(texts)
    elif provider == "sentence_transformers":
        vectors = _embed_texts_sentence_transformers(texts)
    elif provider == "bge_m3":
        vectors = _embed_texts_bge_m3(texts)
    else:
        raise ValueError(
            "Unsupported EMBEDDING_PROVIDER. Use one of: hash, openai, sentence_transformers, bge_m3"
        )

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    _record_embedding_metrics(provider=provider, text_count=len(texts), duration_ms=elapsed_ms)
    return vectors


def validate_vector_dimension(vector: list[float], expected_dim: int) -> None:
    actual_dim = len(vector)
    if actual_dim != expected_dim:
        raise ValueError(
            f"Embedding dimension mismatch: expected={expected_dim}, actual={actual_dim}. "
            "Check VECTOR_DIM and EMBEDDING_PROVIDER/EMBEDDING_MODEL."
        )


def ensure_embedding_enabled(enabled: bool) -> None:
    if not enabled:
        raise ValueError("Embedding is disabled. Set EMBEDDING_ENABLED=true to use /index and /search.")


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks
