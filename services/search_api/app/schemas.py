from typing import Any

from pydantic import BaseModel, Field


class IndexDocumentRequest(BaseModel):
    document_id: str = Field(min_length=1)
    title: str = Field(default="")
    text: str = Field(min_length=1)
    source_path: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)


class SearchHit(BaseModel):
    document_id: str
    score: float
    title: str
    text_snippet: str
    source_path: str
    metadata: dict[str, Any]


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
