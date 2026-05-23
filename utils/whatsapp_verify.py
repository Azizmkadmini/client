"""
Vérification « ce numéro est-il sur WhatsApp ? » sans envoyer de message.

Meta ne fournit pas d’endpoint public gratuit pour savoir si un numéro arbitraire a un
compte WhatsApp (sans API Business / partenaire payant).

Modes :

- **off** : pas de colonne de vérif utile ; lien click-to-chat toujours généré si le numéro
  est au bon format (comportement historique).

- **gratuit** (alias **free**) : filtre **local** via la bibliothèque open-source ``phonenumbers``
  (pas d’appel réseau). On exclut les lignes fixes, SVA, numéros verts, etc. souvent inutilisables
  pour WhatsApp perso ; pour un **mobile plausible**, on ne peut pas confirmer l’inscription WA →
  ``whatsapp_verif`` = ``inconnu`` et le lien est conservé si ``whatsapp_verify_unknown_keep_link``
  est vrai. Ce n’est **pas** une garantie « sur WhatsApp », mais c’est gratuit et limite les erreurs.

- **webhook** : POST vers votre service (BSP, Twilio, etc.) qui renvoie un booléen fiable.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from config import settings
from scraper.extractors import normalize_whatsapp_number, whatsapp_wa_me_url
from scraper.models import EMPTY_VALUE, is_empty_value, normalize_cell

_LOG = logging.getLogger(__name__)

_JSON_KEYS = (
    "on_whatsapp",
    "whatsapp",
    "registered",
    "exists",
    "is_whatsapp",
    "onWhatsApp",
)


def is_whatsapp_number(phone: str) -> bool | None:
    """
    ``True`` : le webhook indique explicitement que le numéro est sur WhatsApp.
    ``False`` : webhook explicite négatif, ou mode **gratuit** : numéro invalide / type exclu
    (fixe, vert, surtaxé, …).
    ``None`` : mode off, webhook ambigu / indisponible, ou mode gratuit avec numéro mobile
    plausible (impossible de confirmer WhatsApp sans API payante).
    """
    digits = normalize_whatsapp_number((phone or "").strip())
    if digits == EMPTY_VALUE:
        return False
    mode = (getattr(settings, "whatsapp_verify_mode", "off") or "off").strip().lower()
    if mode == "off":
        return None
    if mode == "webhook":
        e164 = f"+{digits}"
        return _verify_via_webhook(e164)
    if mode in {"gratuit", "free"}:
        return _verify_gratuit_libphonenumber(digits)
    _LOG.warning("whatsapp_verify_mode inconnu: %s", mode)
    return None


def resolve_whatsapp_link_for_export(raw_whatsapp: str) -> tuple[str, str]:
    """
    Retourne ``(whatsapp_link, whatsapp_verif)`` pour une ligne CSV exportée.

    ``whatsapp_verif`` : ``vide`` | ``oui`` | ``non`` | ``inconnu`` (via ``normalize_cell``).
    Mode **gratuit** : ``inconnu`` = format mobile plausible mais inscription WhatsApp non vérifiable sans API payante.
    """
    wa_cell = normalize_cell(raw_whatsapp)
    if is_empty_value(wa_cell):
        return EMPTY_VALUE, EMPTY_VALUE

    link_template = normalize_cell(whatsapp_wa_me_url(raw_whatsapp))

    mode = (getattr(settings, "whatsapp_verify_mode", "off") or "off").strip().lower()
    if mode == "off":
        return link_template, EMPTY_VALUE

    presence = is_whatsapp_number(raw_whatsapp)
    if presence is True:
        return link_template, normalize_cell("oui")
    if presence is False:
        return EMPTY_VALUE, normalize_cell("non")

    keep = bool(getattr(settings, "whatsapp_verify_unknown_keep_link", True))
    if keep:
        return link_template, normalize_cell("inconnu")
    return EMPTY_VALUE, normalize_cell("inconnu")


def _verify_via_webhook(e164: str) -> bool | None:
    url = (getattr(settings, "whatsapp_verify_webhook_url", "") or "").strip()
    if not url:
        _LOG.debug("whatsapp_verify_mode=webhook mais whatsapp_verify_webhook_url vide")
        return None
    timeout = float(getattr(settings, "whatsapp_verify_webhook_timeout", 12.0))
    token = (getattr(settings, "whatsapp_verify_webhook_token", "") or "").strip()
    headers: dict[str, str] = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = {"phone": e164}
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=headers, content=json.dumps(payload))
    except (httpx.HTTPError, OSError) as exc:
        _LOG.info("whatsapp webhook erreur réseau: %s", exc)
        return None
    if response.status_code != 200:
        _LOG.info("whatsapp webhook HTTP %s", response.status_code)
        return None
    try:
        data = response.json()
    except json.JSONDecodeError:
        _LOG.info("whatsapp webhook réponse non-JSON")
        return None
    return _parse_webhook_bool(data)


def _verify_gratuit_libphonenumber(digits: str) -> bool | None:
    """
    Heuristique locale : pas d’appel réseau, pas de confirmation d’inscription WhatsApp.
    Retourne ``False`` si le type de ligne est très improbable pour un chat WhatsApp perso.
    """
    try:
        import phonenumbers
        from phonenumbers import NumberParseException, is_possible_number, is_valid_number, number_type
    except ImportError:
        _LOG.warning("phonenumbers manquant : installez le paquet pour le mode gratuit")
        return None
    try:
        parsed = phonenumbers.parse(f"+{digits}", None)
    except NumberParseException:
        return False
    if not is_possible_number(parsed) or not is_valid_number(parsed):
        return False
    nt = number_type(parsed)
    blocked = {
        phonenumbers.PhoneNumberType.FIXED_LINE,
        phonenumbers.PhoneNumberType.TOLL_FREE,
        phonenumbers.PhoneNumberType.PREMIUM_RATE,
        phonenumbers.PhoneNumberType.SHARED_COST,
        phonenumbers.PhoneNumberType.UAN,
        phonenumbers.PhoneNumberType.PAGER,
    }
    if nt in blocked:
        return False
    return None


def _parse_webhook_bool(data: Any) -> bool | None:
    if isinstance(data, bool):
        return data
    if not isinstance(data, dict):
        return None
    lower = {str(k).lower(): v for k, v in data.items()}
    for key in _JSON_KEYS:
        lk = key.lower()
        if lk not in lower:
            continue
        return _coerce_bool(lower[lk])
    return None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    if isinstance(value, str):
        s = value.strip().lower()
        if s in {"true", "1", "yes", "y", "oui", "on"}:
            return True
        if s in {"false", "0", "no", "n", "non", "off"}:
            return False
    return None
