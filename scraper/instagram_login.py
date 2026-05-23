"""Connexion Instagram par identifiant / mot de passe (.env) pour le scraper."""

from __future__ import annotations

import re
import time

from config import settings


def _instagram_automation_blocked_message(url: str) -> str | None:
    """
    Mur que la connexion par mot de passe ne peut pas franchir (reCAPTCHA, 2FA, etc.).
    Retourne un message utilisateur, ou None si l'URL ne l'indique pas.
    """
    blank = (
        " Si la page reCAPTCHA reste blanche dans cette fenêtre, c’est normal : chargez Instagram "
        "dans **Chrome** (application Windows), connectez-vous, fermez Chrome, puis "
        "`python outreach.py login instagram --from-browser chrome`. "
        "Sinon : `chrome.exe --remote-debugging-port=9222` puis `python outreach.py login instagram --cdp`."
    )
    u = (url or "").lower()
    if "auth_platform/recaptcha" in u or "/auth_platform/recaptcha" in u:
        return (
            "Instagram impose une vérification reCAPTCHA. "
            "La connexion automatique ne peut pas la résoudre."
            + blank
        )
    if "recaptcha" in u and "instagram.com" in u:
        return (
            "Instagram affiche une page reCAPTCHA."
            + blank
        )
    if "two_factor" in u or "checkpoint" in u or "challenge" in u or "/accounts/suspended" in u:
        return (
            "Instagram demande une vérification (2FA, challenge ou compte restreint). "
            "Connectez-vous une fois avec `python outreach.py login instagram`, "
            "puis réessayez."
        )
    return None


def _instagram_likely_authenticated_url(url: str) -> bool:
    """True si l'URL ressemble à une session déjà connectée (hors login / captcha)."""
    u = (url or "").lower()
    if "instagram.com" not in u:
        return False
    if _instagram_automation_blocked_message(u):
        return False
    if "/accounts/login" in u or "/accounts/emailsignup" in u:
        return False
    if "auth_platform" in u or "consent" in u:
        return False
    return True


def _wait_for_instagram_username_field(page, timeout_ms: int = 40000):
    """Attend un champ identifiant visible ; lève si reCAPTCHA / challenge pendant l'attente."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    deadline = time.monotonic() + timeout_ms / 1000.0
    selectors = (
        'input[name="username"]',
        'input[autocomplete="username"]',
        'input[autocomplete="tel"]',
        "#loginForm input[type='text']",
        'form[method="post"] input[type="text"]',
    )
    while time.monotonic() < deadline:
        blocked = _instagram_automation_blocked_message(page.url or "")
        if blocked:
            raise RuntimeError(blocked)
        for sel in selectors:
            loc = page.locator(sel).first
            try:
                if loc.count() == 0:
                    continue
                loc.wait_for(state="visible", timeout=2000)
                return loc
            except PlaywrightTimeout:
                continue
            except Exception:
                continue
        page.wait_for_timeout(450)
    blocked = _instagram_automation_blocked_message(page.url or "")
    if blocked:
        raise RuntimeError(blocked)
    raise RuntimeError(
        "Champ identifiant Instagram introuvable après attente. "
        "Instagram a peut-être redirigé vers une page de blocage ou la page a changé. "
        "Essayez SCRAPER_HEADLESS=false et `python outreach.py login instagram` pour créer "
        "sessions/instagram.json après connexion manuelle."
    )


def instagram_password_login_configured() -> bool:
    u = (getattr(settings, "instagram_username", "") or "").strip()
    p = (getattr(settings, "instagram_password", "") or "").strip()
    return bool(u and p)


def instagram_session_storage_ready() -> bool:
    """
    True si ``sessions/instagram.json`` existe et semble exploitable.
    Dans ce cas le scraper doit l'utiliser en priorité pour éviter le flux mot de passe
    Playwright (souvent bloqué par reCAPTCHA) lorsque l'utilisateur a déjà fait un login CDP / outreach.
    """
    from utils.browser_session import session_path

    path = session_path("instagram")
    try:
        if not path.exists():
            return False
        if path.stat().st_size < 80:
            return False
    except OSError:
        return False
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return len(raw) > 40 and "cookies" in raw


def launch_chromium_for_instagram_password(playwright) -> tuple[object, object]:
    """Navigateur Playwright isolé (sans fichier session préalable)."""
    from utils.browser_session import chromium_outreach_launch_options

    browser = playwright.chromium.launch(
        **chromium_outreach_launch_options(headless=settings.scraper_headless)
    )
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        locale="fr-FR",
    )
    return browser, context


def ensure_instagram_logged_in_with_password(page) -> None:
    """
    Ouvre la page de connexion et soumet INSTAGRAM_USERNAME / INSTAGRAM_PASSWORD.

    Ne gère pas la 2FA / SMS : dans ce cas, utilisez ``outreach.py login instagram`` une fois.
    """
    page.goto(
        "https://www.instagram.com/accounts/login/",
        wait_until="domcontentloaded",
        timeout=90000,
    )
    page.wait_for_timeout(1200)
    low = (page.url or "").lower()
    blocked = _instagram_automation_blocked_message(low)
    if blocked:
        raise RuntimeError(blocked)
    if _instagram_likely_authenticated_url(low):
        return

    user = (settings.instagram_username or "").strip()
    password = (settings.instagram_password or "").strip()
    if not user or not password:
        raise RuntimeError(
            "INSTAGRAM_USERNAME et INSTAGRAM_PASSWORD doivent être renseignés dans .env pour cette option."
        )

    loc_user = _wait_for_instagram_username_field(page, timeout_ms=40000)
    loc_user.fill(user)

    loc_pass = page.locator('input[name="password"]').first
    loc_pass.wait_for(state="visible", timeout=15000)
    loc_pass.fill(password)

    try:
        page.get_by_role("button", name=re.compile(r"(Log in|Connexion|Se connecter)", re.I)).first.click(
            timeout=8000
        )
    except Exception:
        page.locator("form button[type='submit']").first.click(timeout=8000)

    deadline = time.monotonic() + 55.0
    while time.monotonic() < deadline:
        url = (page.url or "").lower()
        blocked_after = _instagram_automation_blocked_message(url)
        if blocked_after:
            raise RuntimeError(blocked_after)
        if "two_factor" in url or "checkpoint" in url or "challenge" in url:
            raise RuntimeError(
                "Instagram demande une vérification (2FA / challenge). "
                "Connectez-vous une fois avec `python outreach.py login instagram`, "
                "ou complétez la vérification dans un navigateur puis réessayez."
            )
        if "/accounts/login" not in url:
            break
        body = ""
        try:
            body = (page.locator("#slfErrorAlert, div[role='alert']").first.inner_text() or "").strip()
        except Exception:
            pass
        if body:
            raise RuntimeError(f"Instagram refuse la connexion : {body[:280]}")
        page.wait_for_timeout(500)
    else:
        raise RuntimeError(
            "Délai dépassé sur la page de connexion Instagram. "
            "Vérifiez le couple identifiant / mot de passe dans .env."
        )

    page.wait_for_timeout(1200)
    _dismiss_instagram_dialogs(page)


def _dismiss_instagram_dialogs(page) -> None:
    for _ in range(5):
        clicked = False
        for label in (
            "Not Now",
            "Not now",
            "Pas maintenant",
            "Plus tard",
            "Later",
            "OK",
        ):
            try:
                btn = page.get_by_role("button", name=label)
                if btn.count() > 0:
                    btn.first.click(timeout=2500)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            break
        page.wait_for_timeout(400)
