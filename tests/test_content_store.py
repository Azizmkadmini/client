from __future__ import annotations

import pytest

from config import settings
from content.store import ContentStore


@pytest.fixture
def store(tmp_path, monkeypatch: pytest.MonkeyPatch) -> ContentStore:
    db_path = tmp_path / "content_test.db"
    monkeypatch.setattr(settings, "app_db_path", str(db_path))
    monkeypatch.setattr(settings, "default_tenant_id", "test-tenant-001")
    monkeypatch.setattr(settings, "content_max_posts_per_day", 10)
    return ContentStore()


def test_draft_and_schedule(store: ContentStore) -> None:
    d = store.create_draft(body="Hello world", hook="Hook test")
    assert d["status"] == "draft"
    post = store.create_post_from_draft(d["id"])
    scheduled = store.schedule_post(post["id"], "2099-06-01T10:00:00+00:00")
    assert scheduled["status"] == "scheduled"
    cal = store.list_calendar()
    assert len(cal) >= 1
