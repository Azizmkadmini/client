from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from filelock import FileLock, Timeout
from playwright.sync_api import Browser, BrowserContext, Error as PlaywrightError, Playwright

from config import settings

BrowserSource = Literal["chrome", "edge", "firefox", "brave"]

CHANNEL_DOMAINS: dict[str, list[str]] = {
    "instagram": ["instagram.com", ".instagram.com"],
    "linkedin": ["linkedin.com", ".linkedin.com"],
    "linkedin-scrape": ["linkedin.com", ".linkedin.com"],
    "linkedin-outreach": ["linkedin.com", ".linkedin.com"],
    "linkedin-publish": ["linkedin.com", ".linkedin.com"],
    "whatsapp": ["web.whatsapp.com"],
}


def session_path(channel: str) -> Path:
    from utils.session_channels import session_file_path

    return session_file_path(channel)


def connection_mode() -> str:
    return settings.browser_connection_mode.strip().lower()


def ensure_session_dir() -> Path:
    path = settings.path(settings.session_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _playwright_cookie(cookie: Any) -> dict[str, Any]:
    rest = getattr(cookie, "_rest", {}) or {}
    same_site_raw = str(rest.get("SameSite", "lax")).lower()
    same_site = {"strict": "Strict", "lax": "Lax", "none": "None"}.get(
        same_site_raw,
        "Lax",
    )
    expires = getattr(cookie, "expires", None)
    return {
        "name": cookie.name,
        "value": cookie.value,
        "domain": cookie.domain,
        "path": cookie.path or "/",
        "expires": int(expires) if expires else -1,
        "httpOnly": bool(rest.get("HttpOnly")),
        "secure": bool(getattr(cookie, "secure", False)),
        "sameSite": same_site,
    }


def _chromium_user_data_root(source: str) -> Path:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    roots = {
        "chrome": local_app_data / "Google" / "Chrome" / "User Data",
        "edge": local_app_data / "Microsoft" / "Edge" / "User Data",
        "brave": local_app_data / "BraveSoftware" / "Brave-Browser" / "User Data",
    }
    root = roots.get(source)
    if root is None or not root.exists():
        raise RuntimeError(f"Profil {source} introuvable sur ce PC.")
    return root


def _copy_locked_file(source: Path, destination: Path) -> None:
    last_error: Exception | None = None
    for _ in range(8):
        try:
            shutil.copy2(source, destination)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.35)
    raise RuntimeError(
        f"Impossible de copier {source.name}. Fermez le navigateur puis réessayez."
    ) from last_error


def _chromium_cookie_paths(source: str) -> tuple[Path, Path]:
    user_data = _chromium_user_data_root(source)
    profile_dir = user_data / settings.browser_profile
    cookie_source = profile_dir / "Network" / "Cookies"
    if not cookie_source.exists():
        cookie_source = profile_dir / "Cookies"
    key_source = user_data / "Local State"
    if not cookie_source.exists() or not key_source.exists():
        raise RuntimeError(
            f"Fichiers de session {source} introuvables pour le profil {settings.browser_profile}."
        )
    return cookie_source, key_source


def _snapshot_chromium_files(source: str) -> tuple[Path, Path, Path]:
    cookie_source, key_source = _chromium_cookie_paths(source)
    temp_dir = Path(tempfile.mkdtemp(prefix="outreach-cookies-"))
    cookie_copy = temp_dir / "Cookies"
    key_copy = temp_dir / "Local State"
    _copy_locked_file(cookie_source, cookie_copy)
    _copy_locked_file(key_source, key_copy)
    return temp_dir, cookie_copy, key_copy


def _discover_cdp_urls(source: str) -> list[str]:
    urls: list[str] = []
    configured = settings.browser_cdp_url.strip().rstrip("/")
    if configured:
        urls.append(configured)
    for port in (9222, 9223, 9333):
        urls.append(f"http://127.0.0.1:{port}")
    if source in {"chrome", "edge", "brave"}:
        try:
            devtools = _chromium_user_data_root(source) / "DevToolsActivePort"
            if devtools.exists():
                lines = devtools.read_text(encoding="utf-8").splitlines()
                if lines and lines[0].strip().isdigit():
                    urls.append(f"http://127.0.0.1:{int(lines[0].strip())}")
        except OSError:
            pass
    unique: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        unique.append(url)
    return unique


def _cdp_url_alive(url: str) -> bool:
    import urllib.error
    import urllib.request

    try:
        urllib.request.urlopen(f"{url.rstrip('/')}/json/version", timeout=1.5).read()
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def import_session_from_cdp(
    channel: str,
    *,
    browser_source: str | None = None,
    cdp_url: str | None = None,
) -> Path:
    from playwright.sync_api import sync_playwright

    landing = {
        "linkedin": "https://www.linkedin.com/feed/",
        "instagram": "https://www.instagram.com/",
        "whatsapp": "https://web.whatsapp.com/",
    }
    source = (browser_source or settings.browser_from or "chrome").lower()
    urls = [cdp_url.rstrip("/")] if cdp_url else _discover_cdp_urls(source)
    errors: list[str] = []
    for url in urls:
        if not _cdp_url_alive(url):
            continue
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(url)
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(landing[channel], wait_until="domcontentloaded", timeout=90000)
                ensure_session_dir()
                target = session_path(channel)
                context.storage_state(path=str(target))
                browser.close()
                return target
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {exc}")
    detail = " ".join(errors) if errors else "Aucun navigateur débogable détecté sur ce PC."
    raise RuntimeError(
        "Connexion CDP impossible. Lancez Chrome avec "
        "--remote-debugging-port=9222, puis réessayez. "
        f"Détail: {detail}"
    )


def _cookie_matches_channel(cookie_domain: str, channel: str) -> bool:
    domain = cookie_domain.lstrip(".").lower()
    for target in CHANNEL_DOMAINS.get(channel, []):
        normalized = target.lstrip(".").lower()
        if domain == normalized or domain.endswith(f".{normalized}"):
            return True
    return False


def _load_chromium_cookies(
    source: str,
    channel: str,
    *,
    cookie_file: Path | None = None,
    key_file: Path | None = None,
) -> list[dict[str, Any]]:
    import browser_cookie3

    loader = getattr(browser_cookie3, source)
    cookies: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    kwargs: dict[str, str] = {}
    if cookie_file is not None:
        kwargs["cookie_file"] = str(cookie_file)
    if key_file is not None:
        kwargs["key_file"] = str(key_file)

    try:
        jar = loader(domain_name="", **kwargs)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Lecture des cookies {source} impossible.") from exc

    for cookie in jar:
        if not _cookie_matches_channel(cookie.domain, channel):
            continue
        key = (cookie.name, cookie.domain, cookie.path or "/")
        if key in seen:
            continue
        seen.add(key)
        cookies.append(_playwright_cookie(cookie))
    return cookies


def _save_session(channel: str, cookies: list[dict[str, Any]]) -> Path:
    from utils.session_channels import login_storage_targets

    if not cookies:
        raise RuntimeError(
            f"Aucun cookie {channel} trouvé. Ouvrez le site dans ce navigateur et connectez-vous."
        )
    ensure_session_dir()
    payload = json.dumps({"cookies": cookies, "origins": []}, indent=2)
    targets = [session_path(name) for name in login_storage_targets(channel)]
    for target in targets:
        target.write_text(payload, encoding="utf-8")
    return targets[0]


def import_system_browser_cookies(
    channel: str,
    *,
    browser_source: str | None = None,
) -> Path:
    source = (browser_source or settings.browser_from or "chrome").lower()
    if source not in {"chrome", "edge", "firefox", "brave"}:
        raise ValueError(f"Navigateur non supporté: {source}")

    errors: list[str] = []
    if source in {"chrome", "edge", "brave"}:
        temp_dir: Path | None = None
        try:
            temp_dir, cookie_file, key_file = _snapshot_chromium_files(source)
            cookies = _load_chromium_cookies(
                source,
                channel,
                cookie_file=cookie_file,
                key_file=key_file,
            )
            return _save_session(channel, cookies)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
        finally:
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)

        try:
            cookie_file, key_file = _chromium_cookie_paths(source)
            cookies = _load_chromium_cookies(
                source,
                channel,
                cookie_file=cookie_file,
                key_file=key_file,
            )
            return _save_session(channel, cookies)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    try:
        cookies = _load_chromium_cookies(source, channel)
        return _save_session(channel, cookies)
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))

    try:
        return import_session_from_cdp(channel, browser_source=source)
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))

    detail = " ".join(errors) if errors else "Import impossible."
    if source in {"chrome", "edge", "brave"} and _browser_process_running(source):
        detail = (
            f"{source.capitalize()} est encore ouvert : le fichier des cookies est verrouillé sous Windows. "
            f"{detail}"
        )
    raise RuntimeError(
        f"Impossible d'importer la session {channel} depuis {source}. "
        "1) Fermez toutes les fenêtres de ce navigateur (vérifiez l’icône dans la barre des tâches), "
        f"puis relancez la même commande. 2) Plus simple : `python outreach.py login {channel}` "
        "(connexion dans une fenêtre Playwright dédiée, sans toucher à vos cookies Chrome). "
        "3) CDP : démarrez Chrome avec `--remote-debugging-port=9222`, puis "
        f"`python outreach.py login {channel} --cdp`. "
        f"Détail : {detail}"
    )


def _instagram_recaptcha_or_blank_url(url: str) -> bool:
    u = (url or "").lower()
    return "auth_platform/recaptcha" in u or ("instagram.com" in u and "recaptcha" in u)


_INSTAGRAM_RECAPTCHA_PLAYWRIGHT_HINT = """
---
Instagram affiche une étape reCAPTCHA. Si la page reste **blanche**, c’est fréquent : le widget refuse
souvent de se charger dans une fenêtre pilotée par Playwright.

Le plus fiable : ouvrez **Google Chrome** vous-même, connectez-vous à Instagram, fermez Chrome
entièrement, puis importez les cookies :
  python outreach.py login instagram --from-browser chrome

Autre possibilité : démarrez Chrome avec --remote-debugging-port=9222 puis :
  python outreach.py login instagram --cdp
---
"""


def _linkedin_resolved_url(page) -> str:
    """``page.url`` peut être en retard ; ``location.href`` reflète souvent la navigation courante."""
    try:
        js = page.evaluate("() => location.href")
        if isinstance(js, str) and js.strip():
            return js.strip()
    except Exception:
        pass
    return (page.url or "").strip()


def _linkedin_path_is_blocked(path: str) -> bool:
    pl = (path or "/").lower()
    return (
        pl.startswith("/login")
        or pl.startswith("/uas/login")
        or pl.startswith("/checkpoint")
        or "authwall" in pl
    )


def _linkedin_url_looks_logged_in(url: str) -> bool:
    """
    Détection basée sur le chemin (pas sur la sous-chaîne « login » : ex. /in/jean-login-marketing/ est valide).
    """
    raw = (url or "").strip()
    if not raw:
        return False
    try:
        parsed = urlparse(raw)
    except Exception:
        return False
    host = (parsed.netloc or "").lower()
    if "linkedin.com" not in host:
        return False
    path = parsed.path or "/"
    if _linkedin_path_is_blocked(path):
        return False
    # Page d'accueil marketing (/) : ambigu — traitée via _linkedin_dom_logged_in_hint + attente
    if path.rstrip("/") in ("", "/"):
        return False
    return True


def _linkedin_dom_logged_in_hint(page) -> bool:
    """Heuristique DOM si l'URL est encore ambiguë (/ ou SPA)."""
    try:
        return bool(
            page.evaluate(
                """() => {
                    const p = (location.pathname || '').toLowerCase();
                    if (p.startsWith('/login') || p.startsWith('/checkpoint') || p.startsWith('/uas/login'))
                        return false;
                    const href = (location.href || '').toLowerCase();
                    if (href.includes('authwall')) return false;
                    return !!document.querySelector(
                        'a[href="/feed/"], a[href*="/feed/?"], a[href*="linkedin.com/feed"]'
                    );
                }"""
            )
        )
    except Exception:
        return False


def _linkedin_session_cookie_present(page) -> bool:
    """Cookie de session LinkedIn (plus fiable que le texte « login » dans l’URL du profil)."""
    try:
        return any(
            (c.get("name") or "") == "li_at"
            and "linkedin" in (c.get("domain") or "").lower()
            for c in page.context.cookies()
        )
    except Exception:
        return False


def _linkedin_page_looks_logged_in(page) -> bool:
    url = _linkedin_resolved_url(page)
    try:
        path = (urlparse(url).path or "/").lower()
    except Exception:
        path = "/"

    if _linkedin_path_is_blocked(path):
        return False

    if _linkedin_url_looks_logged_in(url):
        return True

    if path.rstrip("/") in ("", "/"):
        return _linkedin_dom_logged_in_hint(page) or _linkedin_session_cookie_present(page)

    return _linkedin_session_cookie_present(page)


def _wait_linkedin_login_detected(page, *, timeout_s: float = 180.0) -> str:
    deadline = time.monotonic() + timeout_s
    last = ""
    while time.monotonic() < deadline:
        last = _linkedin_resolved_url(page)
        if _linkedin_page_looks_logged_in(page):
            return last
        page.wait_for_timeout(450)
    return last


def _linkedin_url_is_feed(url: str) -> bool:
    u = (url or "").lower()
    return "linkedin.com" in u and "/feed" in u


def _ensure_linkedin_on_feed(page, feed_url: str) -> None:
    """
    Après connexion manuelle, LinkedIn est souvent déjà sur /feed/ ; un second goto peut déclencher
    « Navigation interrupted by another navigation ». On évite le goto inutile et on tolère les courses.
    """
    if _linkedin_url_is_feed(page.url):
        return
    if _linkedin_url_is_feed(_linkedin_resolved_url(page)):
        return
    try:
        page.goto(feed_url, wait_until="commit", timeout=90000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=45000)
        except PlaywrightError:
            if (
                _linkedin_url_is_feed(page.url)
                or _linkedin_url_is_feed(_linkedin_resolved_url(page))
                or _linkedin_page_looks_logged_in(page)
            ):
                return
            raise
    except PlaywrightError as exc:
        msg = str(exc).lower().replace(" ", "")
        if "targetclosed" in msg or "hasbeenclosed" in msg:
            raise RuntimeError(
                "La fenêtre du navigateur a été fermée avant la sauvegarde de la session. "
                "Relancez `python outreach.py login linkedin` et gardez la fenêtre ouverte jusqu'à la fin."
            ) from exc
        if "interrupted" in msg:
            page.wait_for_timeout(1200)
            ru = _linkedin_resolved_url(page)
            if (
                _linkedin_url_is_feed(page.url)
                or _linkedin_url_is_feed(ru)
                or _linkedin_page_looks_logged_in(page)
            ):
                return
        raise
    if not _linkedin_page_looks_logged_in(page):
        raise RuntimeError(
            "Impossible de confirmer la connexion LinkedIn après navigation. "
            "Réessayez `python outreach.py login linkedin`."
        )


def chromium_outreach_launch_options(*, headless: bool, proxy_url: str | None = None) -> dict[str, Any]:
    """Options Chromium communes (moins de signaux « navigateur automatisé » que le défaut Playwright)."""
    opts: dict[str, Any] = {
        "headless": headless,
        "channel": _playwright_channel(),
        "ignore_default_args": ["--enable-automation"],
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if proxy_url:
        opts["proxy"] = {"server": proxy_url}
    return opts


def _browser_process_running(source: str) -> bool:
    import subprocess

    process_names = {
        "chrome": "chrome.exe",
        "edge": "msedge.exe",
        "brave": "brave.exe",
    }
    image_name = process_names.get(source)
    if not image_name:
        return False
    completed = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {image_name}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return image_name.lower() in completed.stdout.lower()


def login_in_app_browser(channel: str, *, headless: bool = False) -> Path:
    """
    Connexion interactive sans profil persistant partagé : évite le verrouillage du dossier
    ``sessions/browser-profile`` et les conflits lorsque Chrome / Edge est déjà ouvert sur le PC.
    """
    from playwright.sync_api import sync_playwright

    from utils.session_channels import (
        login_storage_targets,
        normalize_login_channel,
    )

    storage_channel, url_key = normalize_login_channel(channel)
    landing = {
        "linkedin": "https://www.linkedin.com/login",
        "instagram": "https://www.instagram.com/accounts/login/",
        "whatsapp": "https://web.whatsapp.com/",
    }
    feed_urls = {
        "linkedin": "https://www.linkedin.com/feed/",
        "instagram": "https://www.instagram.com/",
        "whatsapp": "https://web.whatsapp.com/",
    }
    ensure_session_dir()
    targets = [session_path(name) for name in login_storage_targets(channel)]
    target = targets[0]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**chromium_outreach_launch_options(headless=headless))
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="fr-FR",
        )
        page = context.new_page()
        try:
            page.goto(landing[url_key], wait_until="domcontentloaded", timeout=90000)
            if url_key == "instagram":
                page.wait_for_timeout(1800)
                if _instagram_recaptcha_or_blank_url(page.url):
                    print(_INSTAGRAM_RECAPTCHA_PLAYWRIGHT_HINT)
            print(
                "Connectez-vous dans la fenêtre Chromium qui s’est ouverte.\n"
                "Quand vous voyez le fil d’actualité (ou une page LinkedIn connectée), "
                "revenez ici et appuyez sur Entrée — la fenêtre doit rester ouverte."
            )
            input()
            if url_key == "linkedin":
                page.wait_for_timeout(600)
                last_url = _wait_linkedin_login_detected(page, timeout_s=180.0)
                if not _linkedin_page_looks_logged_in(page):
                    raise RuntimeError(
                        "Connexion LinkedIn non détectée après 3 minutes. "
                        f"URL vue par le script : {last_url!r}. "
                        "Restez sur une page connectée (ex. fil d’actualité), ne fermez pas la fenêtre, "
                        "puis relancez `python outreach.py login linkedin`. "
                        "Si vous utilisez la double authentification, terminez-la avant d’appuyer sur Entrée."
                    )
                _ensure_linkedin_on_feed(page, feed_urls["linkedin"])
            else:
                page.goto(feed_urls[url_key], wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(2500)
            if url_key == "linkedin":
                cur = _linkedin_resolved_url(page)
                if _linkedin_path_is_blocked(urlparse(cur).path or "/"):
                    raise RuntimeError(
                        "Connexion LinkedIn incomplète (page connexion ou vérification). "
                        f"Réessayez `python outreach.py login {storage_channel}`."
                    )
            if url_key == "instagram":
                low = page.url.lower()
                if "/accounts/login" in low or "/accounts/emailsignup" in low:
                    raise RuntimeError(
                        "Connexion Instagram incomplète (encore sur la page de connexion ou d'inscription). "
                        "Terminez la connexion (cookies / 2FA), puis relancez "
                        "`python outreach.py login instagram`."
                    )
                if "challenge" in low or "suspended" in low:
                    raise RuntimeError(
                        "Instagram demande une vérification (challenge) ou le compte semble suspendu. "
                        "Réglez cela dans le navigateur, puis relancez `python outreach.py login instagram`."
                    )
            state_path = str(target)
            for dest in targets:
                context.storage_state(path=str(dest))
            if len(targets) > 1:
                print(
                    f"Session enregistrée dans {len(targets)} fichiers "
                    f"({', '.join(p.name for p in targets)}). "
                    "Recommandé : comptes séparés scrape / outreach via "
                    "`login linkedin-scrape` et `login linkedin-outreach`."
                )
            return target
        finally:
            context.close()
            browser.close()


def session_available(channel: str) -> bool:
    if connection_mode() == "cdp":
        return True
    if browser_profile_ready():
        return True
    from utils.session_channels import first_existing_session

    if channel in ("linkedin", "linkedin-scrape", "linkedin-outreach"):
        role = "scrape" if channel != "linkedin-outreach" else "outreach"
        return first_existing_session(channel, role=role) is not None
    return session_path(channel).exists()


def require_session_file(channel: str) -> Path | None:
    if connection_mode() == "cdp":
        return None
    if browser_profile_ready():
        from utils.session_channels import first_existing_session

        if channel in ("linkedin", "linkedin-scrape", "linkedin-outreach"):
            role = "scrape" if channel != "linkedin-outreach" else "outreach"
            found = first_existing_session(channel, role=role)
            return found
        path = session_path(channel)
        return path if path.exists() else None
    from utils.session_channels import (
        LINKEDIN_LEGACY,
        LINKEDIN_OUTREACH,
        LINKEDIN_SCRAPE,
        first_existing_session,
    )

    if channel in (LINKEDIN_LEGACY, LINKEDIN_SCRAPE, LINKEDIN_OUTREACH):
        role = "scrape" if channel != LINKEDIN_OUTREACH else "outreach"
        path = first_existing_session(channel, role=role)
        if path is None:
            login_hint = (
                "linkedin-scrape" if role == "scrape" else "linkedin-outreach"
            )
            raise RuntimeError(
                f"Aucune session LinkedIn ({role}). Lancez :\n"
                f"  python outreach.py login {login_hint}\n"
                "Ou (legacy) :\n"
                "  python outreach.py login linkedin"
            )
        return path
    path = session_path(channel)
    if not path.exists():
        raise RuntimeError(
            f"Aucune session {channel}. Lancez `python outreach.py login {channel}`."
        )
    return path


def browser_profile_dir() -> Path:
    return settings.path("sessions/browser-profile")


def browser_profile_ready() -> bool:
    profile = browser_profile_dir()
    return profile.exists() and (profile / "Default").is_dir()


def _playwright_channel() -> str:
    channel = settings.browser_channel.strip().lower()
    if channel in {"", "chromium", "default"}:
        return "chrome"
    return channel


def chromium_launch_channel_name() -> str:
    """Canal passé à ``playwright.chromium.launch(channel=…)`` (Chrome, Edge, etc.)."""
    return _playwright_channel()


def profile_lock_path() -> Path:
    return browser_profile_dir().parent / "browser-profile.lock"


def acquire_profile_lock(timeout: float = 120) -> FileLock:
    lock = FileLock(str(profile_lock_path()))
    try:
        lock.acquire(timeout=timeout)
    except Timeout as exc:
        raise RuntimeError(
            "Le profil Chrome est déjà utilisé. Fermez les autres scrapers ou "
            "relancez après la fin de la collecte en cours."
        ) from exc
    return lock


def release_profile_lock(lock: FileLock | None) -> None:
    if lock is not None and lock.is_locked:
        lock.release()


def _persistent_launch_kwargs(*, headless: bool) -> dict[str, Any]:
    return {
        "user_data_dir": str(browser_profile_dir()),
        "headless": headless,
        "channel": _playwright_channel(),
        "ignore_default_args": ["--enable-automation"],
        "args": ["--disable-blink-features=AutomationControlled"],
        "viewport": {"width": 1440, "height": 900},
    }


def _open_storage_context(
    playwright: Playwright,
    channel: str,
    *,
    headless: bool,
    proxy_url: str | None = None,
    storage_override: Path | str | None = None,
) -> tuple[Browser, BrowserContext, bool]:
    from utils.session_channels import resolve_storage_path

    browser = launch_browser(playwright, headless=headless, proxy_url=proxy_url)
    storage = Path(storage_override) if storage_override else resolve_storage_path(channel)
    if storage.exists():
        context = browser.new_context(storage_state=str(storage))
    else:
        context = browser.new_context()
    return browser, context, True


def _open_persistent_context(
    playwright: Playwright,
    *,
    headless: bool,
) -> tuple[None, BrowserContext, bool]:
    lock = acquire_profile_lock()
    try:
        context = playwright.chromium.launch_persistent_context(
            **_persistent_launch_kwargs(headless=headless),
        )
    except Exception as exc:
        release_profile_lock(lock)
        raise RuntimeError(
            "Impossible d'ouvrir le profil navigateur persistant (sessions/browser-profile). "
            "Fermez les autres fenêtres Playwright / Chrome utilisant ce profil, puis réessayez. "
            "Pour enregistrer une session sans ce profil : `python outreach.py login linkedin` "
            "ou `python outreach.py login instagram`."
        ) from exc
    context._outreach_profile_lock = lock  # type: ignore[attr-defined]
    return None, context, True


def launch_browser(playwright: Playwright, *, headless: bool, proxy_url: str | None = None) -> Browser:
    if connection_mode() == "cdp":
        return playwright.chromium.connect_over_cdp(settings.browser_cdp_url)
    return playwright.chromium.launch(**chromium_outreach_launch_options(headless=headless, proxy_url=proxy_url))


def open_channel_context(
    playwright: Playwright,
    channel: str,
    *,
    headless: bool,
    proxy_url: str | None = None,
    storage_override: Path | str | None = None,
) -> tuple[Browser | None, BrowserContext, bool]:
    if connection_mode() == "cdp":
        browser = launch_browser(playwright, headless=headless)
        owns_browser = False
        if browser.contexts:
            return browser, browser.contexts[0], owns_browser
        return browser, browser.new_context(), owns_browser

    from utils.session_channels import resolve_storage_path

    storage = Path(storage_override) if storage_override else resolve_storage_path(channel)
    if storage.exists():
        browser, context, owns_browser = _open_storage_context(
            playwright,
            channel,
            headless=headless,
            proxy_url=proxy_url,
            storage_override=storage,
        )
        return browser, context, owns_browser

    if browser_profile_ready() and not storage_override:
        try:
            return _open_persistent_context(playwright, headless=headless)
        except RuntimeError:
            if storage.exists():
                browser, context, owns_browser = _open_storage_context(
                    playwright,
                    channel,
                    headless=headless,
                    proxy_url=proxy_url,
                    storage_override=storage,
                )
                return browser, context, owns_browser
            raise

    return _open_storage_context(
        playwright, channel, headless=headless, proxy_url=proxy_url, storage_override=storage_override
    )


def persist_context_state(channel: str, context: BrowserContext) -> None:
    if connection_mode() == "cdp":
        return
    ensure_session_dir()
    context.storage_state(path=str(session_path(channel)))


def close_session(
    browser: Browser | None,
    context: BrowserContext,
    *,
    owns_browser: bool,
) -> None:
    lock = getattr(context, "_outreach_profile_lock", None)
    try:
        context.close()
    finally:
        release_profile_lock(lock)
    close_browser(browser, owns_browser=owns_browser)


def close_browser(browser: Browser | None, *, owns_browser: bool) -> None:
    if connection_mode() == "cdp" and browser is not None:
        browser.close()
        return
    if browser is not None and owns_browser:
        browser.close()
