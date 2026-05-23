from __future__ import annotations

from dataclasses import dataclass, field

from connector.models import BotLead, LeadTag, RawLead, is_profile_complete, is_valid_email


@dataclass
class CleanResult:
    accepted: list[RawLead] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)


class LeadCleaner:
    def clean(self, leads: list[RawLead]) -> CleanResult:
        result = CleanResult()
        seen: set[str] = set()
        for lead in self._normalize_batch(leads):
            fingerprint = self._raw_fingerprint(lead)
            if fingerprint in seen:
                result.rejected.append(
                    {
                        "lead": lead.model_dump(),
                        "reason": "duplicate",
                    }
                )
                continue
            seen.add(fingerprint)

            if not is_profile_complete(lead):
                result.rejected.append(
                    {
                        "lead": lead.model_dump(),
                        "reason": "incomplete_profile",
                    }
                )
                continue

            if lead.email and not is_valid_email(lead.email):
                result.rejected.append(
                    {
                        "lead": lead.model_dump(),
                        "reason": "invalid_email",
                    }
                )
                continue

            result.accepted.append(lead)
        return result

    def _normalize_batch(self, leads: list[RawLead]) -> list[RawLead]:
        normalized: list[RawLead] = []
        for lead in leads:
            normalized.append(
                RawLead(
                    name=lead.name.strip(),
                    company=lead.company.strip(),
                    email=lead.email.strip().lower(),
                    linkedin=lead.linkedin.strip(),
                    instagram=lead.instagram.strip(),
                    phone=lead.phone.strip(),
                    tag=lead.tag.strip().lower(),
                    source=lead.source,
                    source_id=lead.source_id,
                    metadata=lead.metadata,
                )
            )
        return normalized

    def _raw_fingerprint(self, lead: RawLead) -> str:
        if lead.email:
            return f"email:{lead.email.casefold()}"
        if lead.linkedin:
            return f"linkedin:{lead.linkedin.casefold()}"
        if lead.instagram:
            return f"instagram:{lead.instagram.casefold()}"
        if lead.phone:
            return f"phone:{lead.phone.casefold()}"
        return f"name:{lead.name.casefold()}|company:{lead.company.casefold()}"


def _notes_from_scraper_metadata(metadata: dict) -> str:
    """Contexte profil pour personnaliser les e-mails (poste, bio, pays…)."""
    if not metadata:
        return ""
    parts: list[str] = []
    for key in ("poste", "about", "pays", "entreprise", "domaine", "app"):
        raw = metadata.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text and text.lower() != "vide":
            parts.append(f"{key}: {text}")
    return " | ".join(parts[:6])


class LeadEnricher:
    def enrich(self, leads: list[RawLead]) -> list[BotLead]:
        enriched: list[BotLead] = []
        for lead in leads:
            tag = self._resolve_tag(lead)
            enriched.append(
                BotLead(
                    name=lead.name,
                    company=lead.company,
                    email=lead.email,
                    linkedin=lead.linkedin,
                    instagram=lead.instagram,
                    phone=lead.phone,
                    notes=_notes_from_scraper_metadata(lead.metadata),
                    tag=tag,
                )
            )
        return enriched

    def _resolve_tag(self, lead: RawLead) -> LeadTag:
        if lead.tag in {item.value for item in LeadTag}:
            return LeadTag(lead.tag)

        score = 0
        if lead.email:
            score += 1
        if lead.linkedin:
            score += 1
        if lead.instagram:
            score += 1
        if lead.phone:
            score += 1
        if lead.company:
            score += 1

        if score >= 4:
            return LeadTag.HOT
        if score >= 2:
            return LeadTag.WARM
        return LeadTag.COLD
