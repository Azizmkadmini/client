from __future__ import annotations

import pytest

from content.generation import service as gen
from content.models import GenerateHookRequest, GeneratePostRequest


def test_generate_hooks_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gen, "_complete", lambda s, u: "Hook A\nHook B\nHook C")
    hooks = gen.generate_hooks(GenerateHookRequest(topic="SaaS B2B", count=3))
    assert len(hooks) == 3
    assert hooks[0].text == "Hook A"


def test_generate_post_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gen, "_complete", lambda s, u: "Corps du post test.")
    monkeypatch.setattr(gen, "generate_cta", lambda topic, language="fr": "Commentez ci-dessous.")
    draft = gen.generate_post(GeneratePostRequest(topic="automation", include_cta=True))
    assert "Corps" in draft.body
    assert draft.cta
