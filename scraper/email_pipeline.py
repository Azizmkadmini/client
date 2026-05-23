"""
Email pipeline — extension du pipeline enrichissement → outreach email.

Flow :
  ScraperRecord (ACCEPTED, has email)
    → score_lead()           : score 0–10 sur les signaux d'enrichissement
    → classify_lead()        : LeadTag (hot / warm / cold) selon le score
    → record_to_bot_lead()   : ScraperRecord → BotLead (pour fingerprint)
    → _is_duplicate()        : fingerprint déjà dans LeadStore ou ProfileCache ?
    → inject_into_store()    : création directe du Lead dans LeadStore (bypass CSV)
    → ProfileCache.mark_outreach_queued()

Contraintes :
  - Zéro Playwright, zéro HTTP — uniquement les champs déjà enrichis.
  - Idempotent : double appel = zéro doublon (fingerprint + outreach_status).
  - Découplé : ne connaît pas collectors.py.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)


# ── Catégories de leads ────────────────────────────────────────────────────────

class LeadCategory(str, Enum):
    AGENCY     = "agency"      # agences marketing / com / pub
    ECOMMERCE  = "ecommerce"   # boutiques en ligne
    SAAS       = "saas"        # produits software / tech
    FREELANCE  = "freelance"   # consultants / indépendants
    SERVICE    = "service"     # prestataires B2B génériques
    UNKNOWN    = "unknown"

# Mots-clés par catégorie (appliqués sur poste + entreprise + about)
_CATEGORY_SIGNALS: list[tuple[LeadCategory, list[str]]] = [
    (LeadCategory.AGENCY,    [
        "agence", "agency", "marketing", "publicité", "pub", "communication",
        "branding", "digital agency", "média", "content", "creative",
    ]),
    (LeadCategory.ECOMMERCE, [
        "e-commerce", "ecommerce", "boutique", "shop", "store", "vente en ligne",
        "dropshipping", "marketplace",
    ]),
    (LeadCategory.SAAS, [
        "saas", "software", "logiciel", "app", "platform", "tech", "startup",
        "développeur", "developer", "engineering", "product",
    ]),
    (LeadCategory.FREELANCE, [
        "freelance", "consultant", "indépendant", "auto-entrepreneur",
        "free-lance", "consulting",
    ]),
    (LeadCategory.SERVICE, [
        "conseil", "service", "prestataire", "cabinet", "bureau",
        "formation", "coaching", "audit",
    ]),
]

# Mots-clés pour décideurs (majorent le score)
_DECISION_MAKER_TITLES = [
    "ceo", "cto", "cmo", "cfo", "fondateur", "founder", "directeur", "director",
    "président", "president", "gérant", "manager", "head of", "responsable",
    "associé", "partner", "owner", "propriétaire", "dg", "daf",
]

# Domaines génériques qui indiquent une adresse personnelle (minore le score)
_GENERIC_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.fr", "hotmail.com", "hotmail.fr",
    "outlook.com", "outlook.fr", "live.com", "live.fr", "icloud.com",
    "protonmail.com", "proton.me", "laposte.net", "free.fr", "orange.fr",
    "wanadoo.fr", "sfr.fr",
}


# ── Scoring ────────────────────────────────────────────────────────────────────

def score_lead(record) -> float:
    """
    Score 0–10 basé uniquement sur les champs déjà enrichis.
    Aucun appel HTTP / Playwright.
    """
    from scraper.models import is_empty_value

    score: float = 0.0

    # Email professionnel (signal fort)
    email = str(record.email or "").strip().lower()
    if email and not is_empty_value(email):
        score += 3.0
        email_domain = email.split("@")[-1] if "@" in email else ""
        if email_domain in _GENERIC_EMAIL_DOMAINS:
            score -= 1.0   # email perso, moins de valeur

    # WhatsApp aussi présent (multi-canal)
    wa = str(record.whatsapp or "").strip()
    if wa and not is_empty_value(wa):
        score += 0.5

    # Décideur identifiable par le poste
    poste = str(record.poste or "").lower()
    if any(kw in poste for kw in _DECISION_MAKER_TITLES):
        score += 2.0

    # Entreprise connue
    if record.entreprise and not is_empty_value(record.entreprise):
        score += 0.5

    # Site web / domaine identifiable
    if (record.site_web or record.domaine) and not is_empty_value(
        record.site_web or record.domaine
    ):
        score += 0.5

    # Profil bio / about disponible
    if record.about and not is_empty_value(record.about):
        score += 0.5

    # Pays identifié
    if record.pays and not is_empty_value(record.pays):
        score += 0.5

    return round(min(score, 10.0), 2)


# ── Classification ─────────────────────────────────────────────────────────────

def classify_lead(record) -> LeadCategory:
    """Classification par mots-clés sur les champs enrichis (zéro scraping)."""
    text = " ".join([
        str(record.poste       or ""),
        str(record.entreprise  or ""),
        str(record.about       or ""),
        str(record.domaine     or ""),
    ]).lower()

    for category, keywords in _CATEGORY_SIGNALS:
        if any(kw in text for kw in keywords):
            return category
    return LeadCategory.UNKNOWN


def classify_tag(score: float) -> "LeadTag":
    """Convertit un score numérique en LeadTag (hot / warm / cold)."""
    from leads.models import LeadTag
    if score >= 7.0:
        return LeadTag.HOT
    if score >= 4.0:
        return LeadTag.WARM
    return LeadTag.COLD


# ── Conversion ScraperRecord → BotLead ────────────────────────────────────────

def record_to_bot_lead(record, category: LeadCategory, score: float) -> "BotLead":
    """
    Convertit un ScraperRecord enrichi en BotLead.
    Le champ `notes` encode les signaux d'enrichissement pour le générateur IA.
    """
    from connector.models import BotLead
    from scraper.models import is_empty_value

    tag = classify_tag(score)
    notes_parts = []
    if record.poste and not is_empty_value(record.poste):
        notes_parts.append(f"Poste : {record.poste}")
    if record.entreprise and not is_empty_value(record.entreprise):
        notes_parts.append(f"Entreprise : {record.entreprise}")
    if record.pays and not is_empty_value(record.pays):
        notes_parts.append(f"Pays : {record.pays}")
    if record.about and not is_empty_value(record.about):
        about_short = str(record.about)[:200]
        notes_parts.append(f"Bio : {about_short}")
    notes_parts.append(f"Catégorie : {category.value}")
    notes_parts.append(f"Score : {score}")

    email_val = "" if is_empty_value(record.email) else str(record.email)
    wa_val    = "" if is_empty_value(record.whatsapp) else str(record.whatsapp)
    link_val  = str(record.link or "")

    linkedin = link_val if "linkedin.com" in link_val.lower() else ""

    return BotLead(
        name=str(record.nom or "").strip() or "Contact",
        company=str(record.entreprise or "").strip() if not is_empty_value(record.entreprise) else "",
        email=email_val,
        linkedin=linkedin,
        phone=wa_val,
        notes=" | ".join(notes_parts),
        tag=tag,
    )


# ── Injection dans LeadStore ───────────────────────────────────────────────────

def inject_into_store(bot_lead, *, check_duplicate: bool = True) -> bool:
    """
    Injecte directement un BotLead dans LeadStore (bypass CSV / queue file).
    Retourne True si injecté, False si doublon détecté.
    Idempotent via fingerprint SHA-256.
    """
    from leads.models import Channel, FollowUpStage, Lead, LeadStatus
    from leads.store import LeadStore
    from compliance.registry import ComplianceRegistry

    fingerprint = bot_lead.fingerprint()
    store = LeadStore()
    compliance = ComplianceRegistry()

    # Vérification opt-out
    identifiers = [bot_lead.email, bot_lead.linkedin, bot_lead.phone, bot_lead.name]
    if any(compliance.is_opted_out(v) for v in identifiers if v):
        log.debug("email_pipeline: opt-out détecté pour %s", bot_lead.name)
        return False

    # Déduplication par fingerprint
    if check_duplicate and store.find_by_fingerprint(fingerprint):
        log.debug("email_pipeline: doublon ignoré (fingerprint=%s)", fingerprint[:12])
        return False

    # Choix du canal : email en priorité si adresse présente.
    # link = URL LinkedIn (pas l'email) pour que ProfileCache.sync_contacted_from_store()
    # puisse retrouver l'entrée après l'envoi et marquer outreach_status='sent'.
    if bot_lead.email:
        channel = Channel.EMAIL
        link    = bot_lead.linkedin or bot_lead.email
    elif bot_lead.linkedin:
        channel = Channel.LINKEDIN
        link    = bot_lead.linkedin
    elif bot_lead.phone:
        channel = Channel.WHATSAPP
        link    = bot_lead.phone
    else:
        channel = Channel.LINKEDIN
        link    = ""

    from leads.models import LeadTag as LT
    tag_map = {"hot": LT.HOT, "warm": LT.WARM, "cold": LT.COLD}
    tag = tag_map.get(bot_lead.tag.value, LT.COLD)

    lead = Lead(
        id=str(uuid.uuid4()),
        name=bot_lead.name,
        company=bot_lead.company,
        link=link,
        email=bot_lead.email,
        phone=bot_lead.phone,
        tag=tag,
        status=LeadStatus.QUEUED,
        channel=channel,
        follow_up_stage=FollowUpStage.INTRO,
        fingerprint=fingerprint,
        notes=(bot_lead.notes or "").strip(),
    )
    store.upsert_lead(lead)
    log.info(
        "email_pipeline: lead injecté — %s <%s> (score=%.1f, channel=%s)",
        lead.name, lead.email or lead.link, score_lead_from_notes(bot_lead.notes), channel.value,
    )
    return True


def score_lead_from_notes(notes: str) -> float:
    """Extrait le score depuis le champ notes (format 'Score : X.X')."""
    m = re.search(r"Score\s*:\s*([0-9.]+)", notes or "")
    return float(m.group(1)) if m else 0.0


# ── EmailPipeline ──────────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    processed: int = 0
    injected:  int = 0
    skipped:   int = 0    # doublon ou score < threshold
    errors:    int = 0


class EmailPipeline:
    """
    Orchestre la chaîne : ScraperRecord → classification → score → injection LeadStore.
    Ne fait aucun appel réseau ou Playwright.
    """

    def __init__(
        self,
        score_threshold: float = 3.0,
        enabled: bool = True,
    ) -> None:
        self._threshold = score_threshold
        self._enabled   = enabled
        self._stats     = PipelineResult()

    def process_accepted_lead(self, record) -> bool:
        """
        Point d'entrée principal : appelé depuis collectors.py après accepted.append().
        Retourne True si le lead a été injecté dans la file email.
        """
        if not self._enabled:
            return False

        from scraper.models import is_empty_value

        # Pré-condition : email obligatoire
        if is_empty_value(record.email):
            return False

        self._stats.processed += 1

        try:
            score    = score_lead(record)
            category = classify_lead(record)

            # Gate : score minimum
            if score < self._threshold:
                log.debug(
                    "email_pipeline: score trop bas (%.1f < %.1f) pour %s",
                    score, self._threshold, record.nom,
                )
                self._stats.skipped += 1
                return False

            # Gate : déjà en file ou déjà contacté
            from scraper.profile_cache import get_profile_cache
            cache = get_profile_cache()
            url   = str(record.link or "")
            if cache.is_outreach_queued(url):
                log.debug("email_pipeline: déjà en file — %s", url)
                self._stats.skipped += 1
                return False

            bot_lead = record_to_bot_lead(record, category, score)
            injected = inject_into_store(bot_lead)

            if injected:
                cache.mark_outreach_queued(url, score=score)
                self._stats.injected += 1
                return True
            else:
                self._stats.skipped += 1
                return False

        except Exception as exc:
            log.warning("email_pipeline.process_accepted_lead: %s", exc)
            self._stats.errors += 1
            return False

    def process_pending_from_cache(self, limit: int = 100) -> PipelineResult:
        """
        Batch-processing : injecte les leads ACCEPTED du cache qui n'ont pas encore
        été mis en file. Utile pour rattraper des leads collectés lors d'un run précédent
        où le pipeline email n'était pas activé.
        """
        if not self._enabled:
            return self._stats

        from scraper.profile_cache import get_profile_cache
        cache   = get_profile_cache()
        pending = cache.get_pending_outreach(limit=limit)
        log.info("email_pipeline: %d leads en attente de mise en file.", len(pending))

        for record in pending:
            self.process_accepted_lead(record)

        return self._stats

    def stats(self) -> PipelineResult:
        return self._stats


# ── Singleton ──────────────────────────────────────────────────────────────────

_pipeline_instance: EmailPipeline | None = None
_pipeline_lock = __import__("threading").Lock()


def get_email_pipeline() -> EmailPipeline:
    """Singleton partagé dans un run scraper."""
    global _pipeline_instance
    if _pipeline_instance is not None:
        return _pipeline_instance
    with _pipeline_lock:
        if _pipeline_instance is not None:
            return _pipeline_instance
        from config import settings
        enabled   = bool(getattr(settings, "scraper_email_pipeline_enabled", False))
        threshold = float(getattr(settings, "scraper_email_pipeline_score_threshold", 3.0))
        _pipeline_instance = EmailPipeline(score_threshold=threshold, enabled=enabled)
    return _pipeline_instance


def reset_email_pipeline(
    enabled: bool | None = None,
    threshold: float | None = None,
) -> EmailPipeline:
    """Réinitialise le singleton (CLI / tests)."""
    global _pipeline_instance
    with _pipeline_lock:
        from config import settings
        _enabled   = enabled   if enabled   is not None else bool(getattr(settings, "scraper_email_pipeline_enabled", False))
        _threshold = threshold if threshold is not None else float(getattr(settings, "scraper_email_pipeline_score_threshold", 3.0))
        _pipeline_instance = EmailPipeline(score_threshold=_threshold, enabled=_enabled)
    return _pipeline_instance
