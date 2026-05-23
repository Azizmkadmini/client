from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

from scraper.models import EMPTY_VALUE

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"\+?\d[\d\s().-]{7,}\d")
URL_PATTERN = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
PLAIN_WEBSITE_PATTERN = re.compile(
    r"(?<![@\w./])"
    r"(?:https?://)?"
    r"(?:www\.)?"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+"
    r"(?:/[^\s<>'\"]*)?",
    re.IGNORECASE,
)
WEBSITE_LABELS = {
    "site web",
    "website",
    "portfolio",
    "blog",
    "personal website",
    "site internet",
    "lien du site web",
    "bouton du site web",
    "consulter le site web",
    "consulter le site internet",
    "visit website",
    "view website",
    "company website",
    "lien externe",
    "external link",
}
BLOCKED_WEBSITE_HOSTS = (
    "linkedin.com",
    "licdn.com",
    "lnkd.in",
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "google.com",
    "gmail.com",
    "example.com",
    "schema.org",
    "w3.org",
    "cloudflare.com",
    "doubleclick.net",
    "googleapis.com",
    "gstatic.com",
    "sentry.io",
)
# Hôtes à rejeter pour une *adresse e-mail* (pas les mêmes règles que pour un site web :
# Gmail/Outlook/Youtube sont des e-mails de contact valides).
BLOCKED_EMAIL_HOST_SUBSTRINGS: tuple[str, ...] = (
    "linkedin.com",
    "licdn.com",
    "lnkd.in",
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "schema.org",
    "w3.org",
    "cloudflare.com",
    "cloudflare.net",
    "example.com",
    "example.org",
    "example.net",
    "test.com",
    "invalid",
    "sentry.io",
    "sentry-next.wixpress.com",  # Wix internal Sentry address (non-deliverable)
    "wixpress.com",
    "wix.com",
    "squarespace.com",
    "shopify.com",
    "hubspot.com",
    "mailchimp.com",
    "sendgrid.net",
    "amazonses.com",
    "googleapis.com",
    "gstatic.com",
    "doubleclick.net",
    "googletagmanager.com",
    "google-analytics.com",
)

# Préfixes locaux indiquant une adresse non-humaine (filtrés sur la partie avant @).
_BLOCKED_EMAIL_LOCAL_PREFIXES: tuple[str, ...] = (
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "mailer-daemon",
    "postmaster",
    "bounce",
    "notifications",
    "alert",
    "automated",
)
_EMAIL_HOST_FILE_EXT = re.compile(
    r"\.(png|jpe?g|gif|webp|svg|ico|js|css|woff2?|map|xml|json)$",
    re.IGNORECASE,
)
EMAIL_VALIDATION_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def normalize_email(value: str) -> str:
    candidate = (value or "").strip().lower()
    if not candidate or not EMAIL_VALIDATION_PATTERN.match(candidate):
        return EMPTY_VALUE
    local, host = candidate.split("@", 1)
    if any(token in host for token in BLOCKED_EMAIL_HOST_SUBSTRINGS):
        return EMPTY_VALUE
    if any(local == p or local.startswith(p + ".") or local.startswith(p + "-") or local.startswith(p + "_")
           for p in _BLOCKED_EMAIL_LOCAL_PREFIXES):
        return EMPTY_VALUE
    if _EMAIL_HOST_FILE_EXT.search(host):
        return EMPTY_VALUE
    if host.endswith(".local"):
        return EMPTY_VALUE
    return candidate


def normalize_phone(value: str) -> str:
    candidate = (value or "").strip()
    if not candidate:
        return EMPTY_VALUE
    digits = re.sub(r"\D", "", candidate)
    if len(digits) < 8 or len(digits) > 15:
        return EMPTY_VALUE
    if len(set(digits)) == 1:
        return EMPTY_VALUE
    if len(digits) == 8 and digits[:2] in {"19", "20"}:
        return EMPTY_VALUE
    if candidate.startswith("+"):
        return f"+{digits}"
    return f"+{digits}"


def _strip_whatsapp_noise(text: str) -> str:
    """Retire espaces insécables / marques de direction souvent collées aux numéros (LinkedIn, etc.)."""
    if not text:
        return ""
    noise = (
        "\u200b\u200c\u200d\ufeff"
        "\u00a0\u202f"
        "\u200e\u200f\u202a\u202b\u202c\u2066\u2067\u2068\u2069"
    )
    out = text
    for ch in noise:
        out = out.replace(ch, "")
    return out.strip()


def normalize_whatsapp_number(value: str) -> str:
    """
    Chiffres internationaux seuls (sans + ni espaces), comme attendu par
    ``https://web.whatsapp.com/send?phone=`` et par le collage dans WhatsApp.

    Entre 9 et 15 chiffres (indicatif pays + numéro, sans 0 national initial seul).
    """
    candidate = _strip_whatsapp_noise((value or "").strip())
    if not candidate:
        return EMPTY_VALUE
    had_plus = candidate.startswith("+")
    had_intl_prefix = had_plus or candidate.lstrip().startswith("00")
    digits = re.sub(r"\D", "", candidate)
    while digits.startswith("00") and len(digits) > 9:
        digits = digits[2:]
    if len(digits) < 9 or len(digits) > 15:
        return EMPTY_VALUE
    if len(set(digits)) == 1:
        return EMPTY_VALUE
    if len(digits) == 8 and digits[:2] in {"19", "20"}:
        return EMPTY_VALUE
    if digits.startswith("0") and not had_intl_prefix:
        return EMPTY_VALUE
    return digits


def whatsapp_wa_me_url(value: str) -> str:
    """
    Lien « click to chat » officiel (sans ``+`` dans l'URL), mieux reconnu par l'app mobile
    que ``wa.me`` dans certains cas : ``https://api.whatsapp.com/send?phone=<digits>``.
    """
    raw = _strip_whatsapp_noise((value or "").strip())
    if not raw or raw == EMPTY_VALUE:
        return EMPTY_VALUE
    low = raw.lower()
    if "wa.me/" in low:
        wm = re.search(r"https?://wa\.me/(?:\+)?(\d{8,15})", raw, re.IGNORECASE)
        if wm:
            n = normalize_whatsapp_number(wm.group(1))
            return _whatsapp_send_url(n)
        w = parse_whatsapp_from_links(raw)
        return _whatsapp_send_url(w)
    if "web.whatsapp.com" in low or "api.whatsapp.com" in low:
        w = parse_whatsapp_from_links(raw)
        return _whatsapp_send_url(w)
    n = normalize_whatsapp_number(raw)
    return _whatsapp_send_url(n)


def _whatsapp_send_url(digits: str) -> str:
    if not digits or digits == EMPTY_VALUE:
        return EMPTY_VALUE
    return f"https://api.whatsapp.com/send?phone={digits}"


def _deobfuscate_contact_email_text(blob: str) -> str:
    """LinkedIn / sites : user [at] domain [dot] com → user@domain.com"""
    s = (blob or "").replace("\u200b", "").replace("\u200c", "").replace("\ufeff", "")
    if not s:
        return s
    low = s.lower()
    if "[at]" not in low and "(at)" not in low and "[dot]" not in low and "(dot)" not in low:
        return s
    s = re.sub(r"\s*\[\s*at\s*\]\s*", "@", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*\(\s*at\s*\)\s*", "@", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*\[\s*dot\s*\]\s*", ".", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*\(\s*dot\s*\)\s*", ".", s, flags=re.IGNORECASE)
    return s


def parse_email(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return EMPTY_VALUE
    blob = _deobfuscate_contact_email_text(raw)
    for match in EMAIL_PATTERN.finditer(blob):
        token = match.group(0).rstrip(".,);]>\"'»]")
        value = normalize_email(token)
        if value != EMPTY_VALUE:
            return value
    return EMPTY_VALUE


def parse_whatsapp_from_links(text: str) -> str:
    """Numéro depuis liens cliquables WhatsApp (wa.me, api/web.whatsapp.com/send?phone=…)."""
    blob = (text or "").strip()
    if not blob:
        return EMPTY_VALUE
    for m in re.finditer(r"https?://[^\s\"'<>()]+", blob, re.IGNORECASE):
        url = unwrap_linkedin_redirect(m.group(0).rstrip(").,;]"))
        low = url.lower()
        if "chat.whatsapp.com" in low:
            continue
        if "wa.me" not in low and "whatsapp.com" not in low:
            continue
        if "whatsapp.com" in low and "send" not in low and "phone=" not in low and "wa.me" not in low:
            continue
        try:
            parsed = urlparse(url)
        except ValueError:
            parsed = None
        if parsed and parsed.query:
            qs = parse_qs(parsed.query, keep_blank_values=True)
            for key in ("phone", "PHONE"):
                vals = qs.get(key)
                if not vals:
                    continue
                raw_phone = unquote(str(vals[0]).strip())
                w = normalize_whatsapp_number(raw_phone)
                if w != EMPTY_VALUE:
                    return w
        wm = re.search(r"wa\.me/(?:\+)?(\d{8,15})(?:[^\d]|$)", url, re.IGNORECASE)
        if wm:
            w = normalize_whatsapp_number(wm.group(1))
            if w != EMPTY_VALUE:
                return w
    return EMPTY_VALUE


def parse_whatsapp(text: str) -> str:
    w = parse_whatsapp_from_links(text)
    if w != EMPTY_VALUE:
        return w
    match = PHONE_PATTERN.search(_strip_whatsapp_noise(text or ""))
    if not match:
        return EMPTY_VALUE
    return normalize_whatsapp_number(match.group(0))


def parse_domain(text: str) -> str:
    website = parse_website(text)
    if website != EMPTY_VALUE:
        host = urlparse(website).netloc.lower().replace("www.", "")
        return host or EMPTY_VALUE
    return EMPTY_VALUE


def unwrap_linkedin_redirect(url: str) -> str:
    candidate = (url or "").strip()
    if not candidate:
        return ""
    parsed = urlparse(candidate)
    host = parsed.netloc.lower()
    path_low = parsed.path.lower()
    if "linkedin.com" in host and ("redirect" in path_low or "/redir/" in path_low):
        query = parse_qs(parsed.query)
        for key in ("url", "dest", "target"):
            values = query.get(key)
            if values and values[0]:
                return unquote(values[0])
    return candidate


def _is_blocked_website_host(host: str) -> bool:
    normalized = host.lower().replace("www.", "")
    return any(blocked in normalized for blocked in BLOCKED_WEBSITE_HOSTS)


def normalize_website_url(raw: str) -> str:
    candidate = unwrap_linkedin_redirect((raw or "").strip().rstrip(".,);]"))
    if not candidate:
        return EMPTY_VALUE
    if "@" in candidate and not candidate.startswith(("http://", "https://")):
        return EMPTY_VALUE
    if not candidate.startswith(("http://", "https://")):
        candidate = f"https://{candidate.lstrip('/')}"
    parsed = urlparse(candidate)
    host = parsed.netloc.lower()
    if not host or _is_blocked_website_host(host):
        return EMPTY_VALUE
    if "." not in host.split("@")[-1] and host not in ("localhost",):
        return EMPTY_VALUE
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def website_from_href(href: str) -> str:
    return normalize_website_url(href)


def _website_from_labeled_text(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    for index, line in enumerate(lines):
        label = line.lower().rstrip(":")
        if label not in WEBSITE_LABELS:
            continue
        for candidate in lines[index + 1 : index + 4]:
            website = normalize_website_url(candidate)
            if website != EMPTY_VALUE:
                return website
    return EMPTY_VALUE


def parse_website(text: str) -> str:
    labeled = _website_from_labeled_text(text)
    if labeled != EMPTY_VALUE:
        return labeled
    for line in (text or "").splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        for candidate in URL_PATTERN.findall(cleaned):
            website = normalize_website_url(candidate)
            if website != EMPTY_VALUE:
                return website
        website = normalize_website_url(cleaned)
        if website != EMPTY_VALUE:
            return website
    return EMPTY_VALUE


def guess_company(bio: str) -> str:
    for line in (bio or "").splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        if "@" in cleaned or "http" in cleaned.lower():
            continue
        if len(cleaned) > 3:
            return cleaned
    return EMPTY_VALUE


def guess_role(bio: str) -> str:
    keywords = (
        "founder",
        "ceo",
        "director",
        "manager",
        "consultant",
        "coach",
        "developer",
        "designer",
        "marketing",
        "freelance",
    )
    lowered = (bio or "").lower()
    for keyword in keywords:
        if keyword in lowered:
            return keyword.title()
    return EMPTY_VALUE


LINKEDIN_CONNECTION_SUFFIX = re.compile(r"\s*•\s*.+$")
LOCATION_HINT = re.compile(
    r"(gouvernorat|,|france|tunis|uae|émirates|emirates|dubai|doubaï|paris|monastir)",
    re.IGNORECASE,
)
COMPANY_AT_PATTERN = re.compile(r"\b(?:@|at|chez)\s+([^|•\n]+)", re.IGNORECASE)
LINKEDIN_UI_NOISE = re.compile(
    r"^(?:suivre|se connecter|connect(?:er)?|follow|message|plus|voir le profil)$|"
    r"abonn[eé]s?|followers?|"
    r"^•\s*\d+(?:er|e|nd|rd|th|st|\+)?(?:\+)?$|"   # • 1st  • 2nd  • 3rd+
    r"^linkedin\s+member$|"                           # profils anonymes LinkedIn
    r"^\d+(?:[\s,.]\d+)*\s+abonn",
    re.IGNORECASE,
)
LINKEDIN_SCOPE_LABELS = {
    "personnes",
    "posts",
    "emplois",
    "entreprises",
    "groupes",
    "produits",
    "événements",
    "ecoles",
    "écoles",
    "services",
    "cours",
}


def clean_linkedin_name(name: str) -> str:
    cleaned = LINKEDIN_CONNECTION_SUFFIX.sub("", (name or "").strip()).strip()
    return cleaned or EMPTY_VALUE


def normalize_linkedin_profile_url(href: str) -> str:
    if not href:
        return ""
    profile_path = href.split("?")[0].strip()
    if not profile_path.startswith("http"):
        profile_path = f"https://www.linkedin.com{profile_path}"
    return profile_path.rstrip("/")


def _looks_like_location(text: str) -> bool:
    candidate = (text or "").strip()
    if not candidate or _is_linkedin_noise_line(candidate):
        return False
    if any(token in candidate for token in ("|", "@")):
        return False
    lowered = candidate.lower()
    if any(
        keyword in lowered
        for keyword in (
            "engineer",
            "developer",
            "manager",
            "consultant",
            "founder",
            "practitioner",
            "scientist",
            "commercial",
            "passionné",
        )
    ):
        return False
    if "," in candidate and len(candidate) <= 120:
        return True
    return bool(LOCATION_HINT.search(candidate))


def _extract_company_from_headline(text: str) -> str:
    for segment in (text or "").split("|"):
        match = re.search(r"@\s*(.+)$", segment.strip())
        if match:
            return match.group(1).strip()
    match = COMPANY_AT_PATTERN.search(text or "")
    if match:
        return match.group(1).strip()
    return EMPTY_VALUE


def extract_company_from_headline(text: str) -> str:
    company = _extract_company_from_headline(text)
    return company if company else EMPTY_VALUE


def _is_linkedin_noise_line(line: str) -> bool:
    candidate = (line or "").strip()
    if not candidate:
        return True
    if LINKEDIN_UI_NOISE.search(candidate):
        return True
    if candidate.lower() in LINKEDIN_SCOPE_LABELS:
        return True
    return False


def _looks_like_headline(text: str) -> bool:
    candidate = (text or "").strip()
    if not candidate or _is_linkedin_noise_line(candidate):
        return False
    if _looks_like_location(candidate):
        return False
    if any(token in candidate for token in ("|", "@", " chez ", " at ")):
        return True
    keywords = (
        "engineer",
        "developer",
        "manager",
        "consultant",
        "founder",
        "director",
        "practitioner",
        "scientist",
        "commercial",
        "kinésithérapeute",
        "kinésith",
        "passionné",
    )
    lowered = candidate.lower()
    return any(keyword in lowered for keyword in keywords)


def parse_linkedin_card(visible_text: str) -> dict[str, str]:
    lines = [
        line.strip()
        for line in (visible_text or "").splitlines()
        if line.strip() and not _is_linkedin_noise_line(line.strip())
    ]
    if not lines:
        return {
            "nom": EMPTY_VALUE,
            "poste": EMPTY_VALUE,
            "pays": EMPTY_VALUE,
            "entreprise": EMPTY_VALUE,
        }

    nom = clean_linkedin_name(lines[0])
    poste = EMPTY_VALUE
    pays = EMPTY_VALUE
    entreprise = EMPTY_VALUE

    for line in lines[1:]:
        if _looks_like_location(line):
            if pays == EMPTY_VALUE:
                pays = line
            continue
        if poste == EMPTY_VALUE and _looks_like_headline(line):
            poste = line
            company = _extract_company_from_headline(line)
            if company:
                entreprise = company
            continue
        if poste == EMPTY_VALUE:
            poste = line
            company = _extract_company_from_headline(line)
            if company:
                entreprise = company
            continue
        if pays == EMPTY_VALUE and _looks_like_location(line):
            pays = line
            continue
        if entreprise == EMPTY_VALUE and not _looks_like_location(line):
            entreprise = line

    return {
        "nom": nom,
        "poste": poste,
        "pays": pays,
        "entreprise": entreprise,
    }


def parse_linkedin_company_card(visible_text: str) -> dict[str, str]:
    lines = [
        line.strip()
        for line in (visible_text or "").splitlines()
        if line.strip() and not _is_linkedin_noise_line(line.strip())
    ]
    if not lines:
        return {
            "nom": EMPTY_VALUE,
            "poste": EMPTY_VALUE,
            "pays": EMPTY_VALUE,
            "entreprise": EMPTY_VALUE,
        }

    nom = lines[0]
    poste = EMPTY_VALUE
    pays = EMPTY_VALUE
    for line in lines[1:]:
        if _looks_like_location(line):
            if pays == EMPTY_VALUE:
                pays = line
            continue
        if poste == EMPTY_VALUE:
            poste = line
            continue
        if pays == EMPTY_VALUE and _looks_like_location(line):
            pays = line

    return {
        "nom": nom,
        "poste": poste,
        "pays": pays,
        "entreprise": nom,
    }
