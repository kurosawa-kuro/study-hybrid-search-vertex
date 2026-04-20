"""Lexical search adapters."""

from __future__ import annotations

from typing import Any

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import id_token

from common import get_logger

from ..ports.lexical_search import LexicalSearchPort


class NoopLexicalSearch(LexicalSearchPort):
    def search(
        self,
        *,
        query: str,
        filters: dict[str, Any],
        top_k: int,
    ) -> list[tuple[str, int]]:
        return []


class MeilisearchLexical(LexicalSearchPort):
    """Calls Meilisearch ``/indexes/properties/search`` and returns rank list."""

    def __init__(
        self,
        *,
        base_url: str,
        index_name: str = "properties",
        timeout_seconds: float = 3.0,
        api_key: str = "",
        require_identity_token: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._index_name = index_name
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key
        self._require_identity_token = require_identity_token
        self._logger = get_logger("app")

    def search(
        self,
        *,
        query: str,
        filters: dict[str, Any],
        top_k: int,
    ) -> list[tuple[str, int]]:
        headers: dict[str, str] = {"content-type": "application/json"}
        if self._api_key:
            headers["x-meili-api-key"] = self._api_key
        if self._require_identity_token:
            try:
                token = id_token.fetch_id_token(Request(), self._base_url)
                headers["authorization"] = f"Bearer {token}"
            except Exception:
                self._logger.exception("Failed to mint ID token for meili-search")
                return []

        payload: dict[str, Any] = {
            "q": query,
            "limit": top_k,
        }
        filter_expr = _to_meili_filter(filters)
        if filter_expr:
            payload["filter"] = filter_expr

        url = f"{self._base_url}/indexes/{self._index_name}/search"
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            self._logger.exception("Meilisearch request failed")
            return []

        hits = data.get("hits") or []
        out: list[tuple[str, int]] = []
        for idx, hit in enumerate(hits, start=1):
            property_id = str(hit.get("property_id") or "").strip()
            if not property_id:
                continue
            out.append((property_id, idx))
        return out


def _to_meili_filter(filters: dict[str, Any]) -> str | None:
    clauses: list[str] = []
    max_rent = filters.get("max_rent")
    if max_rent is not None:
        clauses.append(f"rent <= {int(max_rent)}")

    layout = filters.get("layout")
    if layout:
        escaped = str(layout).replace('"', '\\"')
        clauses.append(f'layout = "{escaped}"')

    max_walk_min = filters.get("max_walk_min")
    if max_walk_min is not None:
        clauses.append(f"walk_min <= {int(max_walk_min)}")

    pet_ok = filters.get("pet_ok")
    if pet_ok is not None:
        clauses.append(f"pet_ok = {'true' if bool(pet_ok) else 'false'}")

    max_age = filters.get("max_age")
    if max_age is not None:
        clauses.append(f"age_years <= {int(max_age)}")

    if not clauses:
        return None
    return " AND ".join(clauses)
