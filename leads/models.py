from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class LeadTag(str, Enum):
    WARM = "warm"
    COLD = "cold"
    HOT = "hot"


class LeadStatus(str, Enum):
    NEW = "new"
    QUEUED = "queued"
    CONTACTED = "contacted"
    REPLIED = "replied"
    FAILED = "failed"
    COMPLETED = "completed"


class Channel(str, Enum):
    LINKEDIN = "linkedin"
    INSTAGRAM = "instagram"
    WHATSAPP = "whatsapp"
    EMAIL = "email"


class FollowUpStage(int, Enum):
    INTRO = 1
    FOLLOW_UP = 2
    FINAL = 3


class Lead(BaseModel):
    id: str
    name: str
    company: str = ""
    link: str = ""
    email: str = ""
    phone: str = ""
    tag: LeadTag = LeadTag.COLD
    status: LeadStatus = LeadStatus.NEW
    channel: Channel = Channel.LINKEDIN
    follow_up_stage: FollowUpStage = FollowUpStage.INTRO
    last_contacted_at: Optional[datetime] = None
    next_follow_up_at: Optional[datetime] = None
    notes: str = ""
    fingerprint: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def display_context(self) -> dict[str, str]:
        return {
            "name": self.name,
            "company": self.company or "their company",
            "link": self.link,
            "email": self.email,
            "tag": self.tag.value,
            "notes": self.notes,
        }
