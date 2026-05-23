from __future__ import annotations

import hashlib
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
LINKEDIN_PATTERN = re.compile(r"linkedin\.com", re.IGNORECASE)
INSTAGRAM_PATTERN = re.compile(r"instagram\.com", re.IGNORECASE)
WHATSAPP_PATTERN = re.compile(r"(wa\.me|whatsapp\.com)", re.IGNORECASE)


class LeadTag(str, Enum):
    COLD = "cold"
    WARM = "warm"
    HOT = "hot"


class RawLead(BaseModel):
    name: str = ""
    company: str = ""
    email: str = ""
    linkedin: str = ""
    instagram: str = ""
    phone: str = ""
    tag: str = ""
    source: str = ""
    source_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_record(cls, record: dict[str, Any], source: str) -> RawLead:
        lowered = {str(key).strip().lower(): value for key, value in record.items()}
        link = _first_non_empty(
            lowered,
            "link",
            "profile",
            "profile_url",
            "url",
        )
        linkedin = _first_non_empty(lowered, "linkedin", "linkedin_url", "linkedin_profile")
        instagram = _first_non_empty(lowered, "instagram", "instagram_url", "instagram_profile")
        phone = _first_non_empty(lowered, "phone", "whatsapp_link", "whatsapp", "whatsapp_phone", "mobile")
        if link:
            if LINKEDIN_PATTERN.search(link) and not linkedin:
                linkedin = link
            elif INSTAGRAM_PATTERN.search(link) and not instagram:
                instagram = link
            elif WHATSAPP_PATTERN.search(link) and not phone:
                phone = link
        return cls(
            name=str(_first_non_empty(lowered, "name", "nom", "full_name", "contact_name") or "").strip(),
            company=str(_first_non_empty(lowered, "company", "entreprise", "organization", "org") or "").strip(),
            email=str(_first_non_empty(lowered, "email", "email_address") or "").strip(),
            linkedin=str(linkedin or "").strip(),
            instagram=str(instagram or "").strip(),
            phone=str(phone or "").strip(),
            tag=str(_first_non_empty(lowered, "tag", "lead_tag") or "").strip().lower(),
            source=source,
            source_id=str(_first_non_empty(lowered, "id", "lead_id", "source_id") or "").strip(),
            metadata={key: value for key, value in record.items()},
        )


class BotLead(BaseModel):
    name: str
    company: str = ""
    email: str = ""
    linkedin: str = ""
    instagram: str = ""
    phone: str = ""
    notes: str = ""
    tag: LeadTag = LeadTag.COLD

    @field_validator("tag", mode="before")
    @classmethod
    def normalize_tag(cls, value: Any) -> LeadTag:
        if isinstance(value, LeadTag):
            return value
        normalized = str(value or LeadTag.COLD.value).strip().lower()
        try:
            return LeadTag(normalized)
        except ValueError:
            return LeadTag.COLD

    def fingerprint(self) -> str:
        parts = [
            self.phone.casefold(),
            self.email.casefold(),
            self.linkedin.casefold(),
            self.instagram.casefold(),
            self.name.casefold(),
            self.company.casefold(),
        ]
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
        return digest

    def to_bot_payload(self) -> dict[str, str]:
        return {
            "name": self.name,
            "company": self.company,
            "email": self.email,
            "linkedin": self.linkedin,
            "instagram": self.instagram,
            "phone": self.phone,
            "notes": self.notes,
            "tag": self.tag.value,
        }


def _first_non_empty(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "vide":
            return text
    return ""


def is_valid_email(value: str) -> bool:
    if not value:
        return True
    return bool(EMAIL_PATTERN.match(value.strip()))


def is_profile_complete(lead: RawLead) -> bool:
    if not lead.name.strip():
        return False
    return bool(
        lead.email.strip()
        or lead.linkedin.strip()
        or lead.instagram.strip()
        or lead.phone.strip()
    )
