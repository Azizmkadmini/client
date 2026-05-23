"""
Heuristiques de récupération de contacts (fusion de sources, e-mails probables, MX).

Ne fait pas de vérification SMTP « mailbox existe » (souvent bloquée / non fiable).
Recherche Google/Bing : voir ``scraper.web.search_engine`` et ``python -m scraper.cli web-run``.
"""

from __future__ import annotations

import logging
import re
import threading
import unicodedata
from collections.abc import Iterable
from ipaddress import AddressValueError, IPv4Address, IPv6Address

import dns.resolver
from dns.exception import DNSException

from scraper.extractors import normalize_email
from scraper.models import EMPTY_VALUE

# Cache DNS MX/A par domaine — évite N appels DNS pour le même domaine dans un run
# (ex. 6 candidats prenom.nom@agence.fr → 1 seul lookup DNS au lieu de 6).
# Thread-safe via verrou léger ; TTL non géré (run court, pas de service long).
_mx_cache: dict[str, bool | None] = {}
_mx_cache_lock = threading.Lock()

_PLACEHOLDER_LOCAL = re.compile(
    r"^(noreply|no-reply|no_reply|donotreply|do-not-reply|mailer-daemon|postmaster|"
    r"webmaster|hostmaster|abuse|bounce|test|example|username|yourname|you@|name@|user@|"
    r"privacy|dpo|compliance|newsletter|updates?|notifications?)(\+|\.)?",
    re.IGNORECASE,
)


def is_placeholder_like_email(email: str) -> bool:
    if not email or email == EMPTY_VALUE:
        return True
    local = email.split("@", 1)[0].lower()
    return bool(_PLACEHOLDER_LOCAL.match(local))


def merge_contact_layers(*layers: dict[str, str]) -> dict[str, str]:
    """Fusionne les dictionnaires retournés par ``extract_contacts_from_sources`` (ordre = priorité)."""
    keys = ("email", "whatsapp", "site_web", "domaine", "entreprise")
    out: dict[str, str] = {k: EMPTY_VALUE for k in keys}
    texts: list[str] = []
    for d in layers:
        if not d:
            continue
        for k in keys:
            v = (d.get(k) or "").strip()
            current = (out.get(k) or "").strip()
            if v and v != EMPTY_VALUE and (not current or current == EMPTY_VALUE):
                out[k] = v
        tx = (d.get("text") or "").strip()
        if tx:
            texts.append(tx)
    out["text"] = "\n".join(texts)[-80_000:]
    return out


def contact_trace(lg: logging.Logger, profile_url: str, event: str, **details: object) -> None:
    parts = " ".join(f"{k}={v!r}" for k, v in details.items())
    if parts:
        lg.info("contact_recovery %s %s %s", event, profile_url, parts)
    else:
        lg.info("contact_recovery %s %s", event, profile_url)


def split_display_name_for_guess(nom: str) -> tuple[str, str]:
    parts = [p for p in re.split(r"\s+", (nom or "").strip()) if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


def _slug_local(part: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (part or "").lower())


def guess_email_local_parts(first: str, last: str) -> list[str]:
    f = _slug_local(first)
    last_slug = _slug_local(last)
    if not f:
        return []
    out: list[str] = []
    if last_slug:
        for cand in (
            f"{f}.{last_slug}",
            f"{f}{last_slug}",
            f"{last_slug}.{f}",
            f"{f[0]}{last_slug}" if f else "",
            f"{f}_{last_slug}",
        ):
            if len(cand) >= 3:
                out.append(cand)
    out.append(f)
    seen: set[str] = set()
    ordered: list[str] = []
    for x in out:
        if x and x not in seen:
            seen.add(x)
            ordered.append(x)
    return ordered


def _domain_shape_ok_for_mx(domain: str) -> bool:
    """
    Filtre les « domaines » qui viennent du texte LinkedIn (taglines, slogans) et feraient planter
    dnspython (« … does not appear to be an IPv4 or IPv6 address »).
    """
    raw = (domain or "").strip()
    if not raw:
        return False
    d = unicodedata.normalize("NFKC", raw).strip().lower().removeprefix("www.")
    if not d or len(d) > 253 or "." not in d:
        return False
    # Espaces / ponctuation (y compris séparateurs Unicode)
    if re.search(r"[\s,;:/\\\\@!?()\[\]{}\"«»]", d):
        return False
    # Pas d’IP littérale comme « domaine » pour la guess MX
    try:
        IPv4Address(d)
        return False
    except AddressValueError:
        pass
    try:
        IPv6Address(d)
        return False
    except AddressValueError:
        pass
    labels = d.split(".")
    if len(labels) < 2:
        return False
    label_re = re.compile(r"^[a-z0-9\u00c0-\u024f-]+$", re.IGNORECASE)
    for lab in labels:
        if not lab or len(lab) > 63:
            return False
        if lab.startswith("-") or lab.endswith("-"):
            return False
        if not label_re.fullmatch(lab):
            return False
    # Rejette les TLD académiques / diplômes mal interprétés (m.sc, b.sc, ph.d, m.eng…)
    _FAKE_ACADEMIC_DOMAINS = {
        "m.sc", "b.sc", "ph.d", "m.eng", "b.eng", "m.ba", "b.ba",
        "m.ed", "b.ed", "m.a", "b.a", "m.s", "b.s", "m.d",
    }
    if d in _FAKE_ACADEMIC_DOMAINS:
        return False
    # Rejette les TLD d'un seul caractère (pas de TLD valide à 1 lettre)
    if len(labels[-1]) < 2:
        return False
    return True


def guess_emails_from_name_and_domain(first: str, last: str, domain: str) -> list[str]:
    if not _domain_shape_ok_for_mx(domain):
        return []
    dom = unicodedata.normalize("NFKC", (domain or "").strip()).strip().lower().removeprefix("www.")
    locals_ = guess_email_local_parts(first, last)
    return list(dict.fromkeys(f"{loc}@{dom}" for loc in locals_ if loc))


def mx_domain_has_records(domain: str) -> bool | None:
    """
    True si le domaine a au moins un MX ou une A (serveur mail plausible).
    None en cas d'erreur réseau / résolution ambiguë.
    Résultat mis en cache pour tout le run — évite N lookups pour le même domaine.
    """
    if not _domain_shape_ok_for_mx(domain):
        return False
    dom = unicodedata.normalize("NFKC", (domain or "").strip()).strip().lower().removeprefix("www.")

    with _mx_cache_lock:
        if dom in _mx_cache:
            return _mx_cache[dom]

    result: bool | None = None
    try:
        if len(dns.resolver.resolve(dom, "MX")) > 0:
            result = True
    except dns.resolver.NXDOMAIN:
        result = False
    except dns.resolver.NoAnswer:
        pass
    except (DNSException, ValueError, TypeError, UnicodeError):
        result = None

    if result is not True:
        try:
            if len(dns.resolver.resolve(dom, "A")) > 0:
                result = True
        except dns.resolver.NXDOMAIN:
            result = False
        except dns.resolver.NoAnswer:
            if result is None:
                result = False
        except (DNSException, ValueError, TypeError, UnicodeError):
            pass

    with _mx_cache_lock:
        _mx_cache[dom] = result
    return result


def clear_mx_cache() -> None:
    """Vide le cache DNS (utile entre deux runs distincts)."""
    with _mx_cache_lock:
        _mx_cache.clear()


def pick_guessed_email(candidates: Iterable[str], *, require_mx: bool) -> str:
    """Choisit la première combinaison normalisée + non placeholder ; MX optionnel sur le domaine."""
    for raw in candidates:
        e = normalize_email(raw.strip())
        if e == EMPTY_VALUE or is_placeholder_like_email(e):
            continue
        host = e.split("@", 1)[1]
        if require_mx:
            mx = mx_domain_has_records(host)
            if mx is False:
                continue
        return e
    return EMPTY_VALUE
