from __future__ import annotations

import asyncio
import httpx
import pytest

from app.errors import DependencyError
from app.config import settings
from app.services import google_places as google_places_service


class _FailingAsyncClient:
    def __init__(self, *args, **kwargs):
        del args, kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    async def post(self, url, headers=None, json=None):
        del headers, json
        request = httpx.Request("POST", url)
        response = httpx.Response(403, request=request, text='{"error":"bad key"}')
        raise httpx.HTTPStatusError("forbidden", request=request, response=response)

    async def get(self, url, headers=None, params=None):
        del headers, params
        request = httpx.Request("GET", url)
        response = httpx.Response(403, request=request, text='{"error":"bad key"}')
        raise httpx.HTTPStatusError("forbidden", request=request, response=response)


def test_text_search_wraps_http_errors(monkeypatch):
    monkeypatch.setattr(settings, "google_maps_api_key", "test-key")
    monkeypatch.setattr(google_places_service.httpx, "AsyncClient", _FailingAsyncClient)
    with pytest.raises(DependencyError) as exc:
        asyncio.run(google_places_service.search_places_text("ocean"))
    assert exc.value.code == "GOOGLE_PLACES_TEXT_SEARCH_FAILED"


def test_route_matrix_wraps_http_errors(monkeypatch):
    monkeypatch.setattr(settings, "google_maps_api_key", "test-key")
    monkeypatch.setattr(google_places_service.httpx, "AsyncClient", _FailingAsyncClient)
    with pytest.raises(DependencyError) as exc:
        asyncio.run(
            google_places_service.compute_route_matrix_minutes(
                [(35.0, 139.0)],
                [(35.1, 139.1)],
                departure_time_iso="2099-01-01T10:00:00+00:00",
            )
        )
    assert exc.value.code == "GOOGLE_ROUTE_MATRIX_FAILED"
