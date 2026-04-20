"""Pydantic schemas for /search and /feedback endpoints.

Field naming mirrors the ranker feature vocabulary (snake_case, metric units
in column names where ambiguous) so there is zero translation between the
HTTP contract and ``FEATURE_COLS_RANKER`` / ``ranking_log.features``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    max_rent: int | None = Field(default=None, ge=0)
    layout: str | None = None
    max_walk_min: int | None = Field(default=None, ge=0)
    pet_ok: bool | None = None
    max_age: int | None = Field(default=None, ge=0)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=512)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    top_k: int = Field(default=20, ge=1, le=100)


class SearchResultItem(BaseModel):
    property_id: str
    final_rank: int
    lexical_rank: int
    semantic_rank: int
    me5_score: float
    score: float | None = None  # None while rerank is disabled (Phase 4 MVP)


class SearchResponse(BaseModel):
    request_id: str
    results: list[SearchResultItem]
    model_path: str | None = None


class FeedbackRequest(BaseModel):
    request_id: str
    property_id: str
    action: str = Field(..., pattern=r"^(click|favorite|inquiry)$")


class FeedbackResponse(BaseModel):
    accepted: bool
