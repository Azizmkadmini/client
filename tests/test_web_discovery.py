"""Tests recherche web (Google / discovery)."""

from __future__ import annotations

import pytest

from config import settings
from scraper.web import discovery
from scraper.web.search_engine import _clean_result_url, _dedupe_urls, web_search_urls


def test_clean_google_redirect_url() -> None:
    raw = "/url?q=https%3A%2F%2Fwww.linkedin.com%2Fin%2Fjohn-doe%2F&sa=U"
    assert "linkedin.com/in/john-doe" in _clean_result_url(raw)


def test_discover_linkedin_urls_via_google(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_search(query: str, *, max_results: int) -> list[str]:
        return [
            "https://www.linkedin.com/in/john-doe/",
            "https://www.linkedin.com/in/jane-smith/",
        ]

    monkeypatch.setattr(discovery, "web_search_urls", fake_search)
    urls = discovery.discover_linkedin_urls("marketing", limit=5)
    assert len(urls) == 2
    assert all("/in/" in u for u in urls)


def test_discover_instagram_handles_filters_reserved(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_search(query: str, *, max_results: int) -> list[str]:
        return [
            "https://www.instagram.com/mybrand/",
            "https://www.instagram.com/explore/tags/foo/",
        ]

    monkeypatch.setattr(discovery, "web_search_urls", fake_search)
    handles = discovery.discover_instagram_handles("event", limit=10)
    assert handles == ["mybrand"]


def test_google_cse_parses_items(monkeypatch: pytest.MonkeyPatch) -> None:
    from scraper.web import search_engine

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "items": [
                    {"link": "https://example.com/contact"},
                    {"link": "https://www.linkedin.com/in/ceo/"},
                ]
            }

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def get(self, url: str, params: dict | None = None) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(settings, "scraper_web_google_api_key", "key")
    monkeypatch.setattr(settings, "scraper_web_google_cx", "cx")
    monkeypatch.setattr(search_engine, "_http_client", lambda: FakeClient())
    monkeypatch.setattr(search_engine, "pause_between_web_requests", lambda: None)
    urls = search_engine._search_google_cse("test", max_results=5)
    assert "example.com" in urls[0]
    assert "linkedin.com/in/ceo" in urls[1]


def test_web_stability_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    from scraper.web.stability import max_discovery_results_per_query, max_queries_per_run

    monkeypatch.setattr(settings, "scraper_web_max_results_per_query", 99)
    assert max_discovery_results_per_query() == 40
    monkeypatch.setattr(settings, "scraper_web_max_queries_per_run", 50)
    assert max_queries_per_run() == 12


def test_dedupe_urls() -> None:
    raw = [
        "https://Example.com/page",
        "https://example.com/page",
        "https://www.google.com/search?q=x",
    ]
    out = _dedupe_urls(raw, max_results=10)
    assert len(out) == 1
    assert out[0] == "https://example.com/page"
