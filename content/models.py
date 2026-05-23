"""Modèles domaine Content OS (Pydantic)."""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ContentFormat(str, Enum):
    TEXT = "text"
    STORYTELLING = "storytelling"
    EXPERTISE = "expertise"
    CONVERSION = "conversion"
    FRAMEWORK = "framework"
    OPINION = "opinion"
    CAROUSEL = "carousel"
    QUOTE_CARD = "quote_card"


class ContentStatus(str, Enum):
    DRAFT = "draft"
    REVIEW = "review"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    ARCHIVED = "archived"


class GenerateHookRequest(BaseModel):
    topic: str
    audience: str = "founders and operators"
    tone: str = "direct, expert, no fluff"
    language: str = "fr"
    count: int = Field(default=5, ge=1, le=10)
    category: str | None = None


class HookVariant(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    text: str
    score: float | None = None


class GeneratePostRequest(BaseModel):
    topic: str
    format: ContentFormat = ContentFormat.EXPERTISE
    hook: str | None = None
    include_cta: bool = True
    language: str = "fr"
    max_chars: int = Field(default=2800, ge=500, le=3000)
    brand_voice: str | None = None


class PostDraft(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    hook: str | None = None
    body: str
    cta: str | None = None
    format: ContentFormat = ContentFormat.TEXT
    metadata: dict[str, Any] = Field(default_factory=dict)
