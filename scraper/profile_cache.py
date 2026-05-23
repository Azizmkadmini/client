"""
Incremental scraping cache — évite de re-scraper des profils déjà collectés.

Deux couches :
  - In-memory dict  : O(1) lookups dans un run (clé = URL normalisée)
  - SQLite persisté : survit entre les runs quotidiens (data/scraper_cache.db)

Clés de déduplication (ordre de priorité) :
  1. URL LinkedIn exacte   (/in/slug ou /company/slug)  → clé primaire
  2. Domain entreprise     (agence.fr)                  → fallback si URL change
  3. Profile hash          sha1(nom|entreprise|poste)   → fallback dernier recours

Comportement :
  - Profil avec email, vu < TTL_WITH_EMAIL    → retourner le record caché, 0 Playwright
  - Profil sans email,  vu < TTL_NO_EMAIL     → skip (déjà essayé, pas d'email)
  - Profil expiré                             → re-enrichir normalement
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
import threading
import time
from dataclasses import replace
from pathlib import Path

from scraper.models import EMPTY_VALUE, ScraperRecord, is_empty_value

log = logging.getLogger(__name__)

# ── Schéma SQLite ─────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS scraper_profile_cache (
    url              TEXT PRIMARY KEY,
    domain           TEXT,
    phash            TEXT,
    last_seen        REAL  NOT NULL,
    has_email        INTEGER NOT NULL DEFAULT 0,
    nom              TEXT,
    email            TEXT,
    whatsapp         TEXT,
    pays             TEXT,
    entreprise       TEXT,
    poste            TEXT,
    domaine          TEXT,
    site_web         TEXT,
    about            TEXT,
    app              TEXT,
    score            REAL,
    outreach_status  TEXT,
    contacted_at     REAL
);
CREATE INDEX IF NOT EXISTS idx_domain   ON scraper_profile_cache(domain);
CREATE INDEX IF NOT EXISTS idx_phash    ON scraper_profile_cache(phash);
CREATE INDEX IF NOT EXISTS idx_seen     ON scraper_profile_cache(last_seen);
CREATE INDEX IF NOT EXISTS idx_outreach ON scraper_profile_cache(outreach_status);
"""

# Colonnes ajoutées après la v1 — migration safe (ALTER TABLE idempotente)
_MIGRATION_COLUMNS: list[tuple[str, str]] = [
    ("score",           "REAL"),
    ("outreach_status", "TEXT"),
    ("contacted_at",    "REAL"),
]


# ── Utilitaires ───────────────────────────────────────────────────────────────

def _normalize_url(url: str) -> str:
    """Retire les query-strings et normalise la casse."""
    return (url or "").split("?")[0].strip().rstrip("/").lower()


def _normalize_domain(domain: str) -> str:
    d = re.sub(r"^https?://", "", (domain or "").strip().lower())
    return d.split("/")[0].removeprefix("www.").strip()


def _profile_hash(nom: str, entreprise: str, poste: str) -> str:
    """Hash stable : insensible à la casse et aux caractères spéciaux."""
    parts = [
        re.sub(r"[^a-z0-9]", "", (nom or "").lower()),
        re.sub(r"[^a-z0-9]", "", (entreprise or "").lower()),
        re.sub(r"[^a-z0-9]", "", (poste or "").lower()),
    ]
    raw = "|".join(p for p in parts if p)
    if not raw:
        return ""
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


def _record_to_row(record: ScraperRecord, url_key: str) -> dict:
    domain = _normalize_domain(record.domaine or record.site_web or "")
    phash  = _profile_hash(record.nom, record.entreprise, record.poste)
    has_email = 0 if is_empty_value(record.email) else 1
    return {
        "url":        url_key,
        "domain":     domain or None,
        "phash":      phash  or None,
        "last_seen":  time.time(),
        "has_email":  has_email,
        "nom":        record.nom        or None,
        "email":      record.email      or None,
        "whatsapp":   record.whatsapp   or None,
        "pays":       record.pays       or None,
        "entreprise": record.entreprise or None,
        "poste":      record.poste      or None,
        "domaine":    record.domaine    or None,
        "site_web":   record.site_web   or None,
        "about":      record.about      or None,
        "app":        record.app        or None,
    }


def _row_to_record(row: dict) -> ScraperRecord:
    def v(k: str) -> str:
        val = row.get(k)
        return str(val) if val is not None else EMPTY_VALUE
    return ScraperRecord(
        nom=v("nom"), email=v("email"), whatsapp=v("whatsapp"),
        pays=v("pays"), entreprise=v("entreprise"), poste=v("poste"),
        domaine=v("domaine"), site_web=v("site_web"),
        about=v("about"), app=v("app"),
        link=row.get("url", EMPTY_VALUE),
    )


# ── Classe principale ─────────────────────────────────────────────────────────

class ProfileCache:
    """
    Cache incrémental de profils LinkedIn.

    Paramètres :
        db_path         : chemin vers le fichier SQLite
        ttl_with_email  : durée de validité (s) si email trouvé  (défaut 7 jours)
        ttl_no_email    : durée de validité (s) si pas d'email   (défaut 1 jour)
        enabled         : False = cache désactivé (mode --no-cache)
    """

    def __init__(
        self,
        db_path: str | Path = "data/scraper_cache.db",
        ttl_with_email: float = 7 * 86400,
        ttl_no_email:   float = 1 * 86400,
        enabled: bool = True,
    ) -> None:
        self._enabled = enabled
        self._ttl_hit  = float(ttl_with_email)
        self._ttl_miss = float(ttl_no_email)
        self._lock     = threading.Lock()

        # In-memory indexes : url → row dict
        self._by_url:    dict[str, dict] = {}
        self._by_domain: dict[str, str]  = {}   # domain → url
        self._by_phash:  dict[str, str]  = {}   # phash  → url

        # Counters for telemetry
        self._hits    = 0
        self._misses  = 0
        self._skipped = 0  # "tried before, no email"
        self._stores  = 0

        if not self._enabled:
            return

        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(db_path)
        self._init_db()
        self._load_into_memory()

    # ── Init & persistence ────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate_schema(conn)

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        """Ajoute les colonnes manquantes si la table existait déjà avant la migration."""
        existing_cols: set[str] = set()
        try:
            cur = conn.execute("PRAGMA table_info(scraper_profile_cache)")
            existing_cols = {row["name"] for row in cur.fetchall()}
        except Exception:
            return
        for col_name, col_type in _MIGRATION_COLUMNS:
            if col_name not in existing_cols:
                try:
                    conn.execute(
                        f"ALTER TABLE scraper_profile_cache ADD COLUMN {col_name} {col_type}"
                    )
                    log.debug("ProfileCache: migration — colonne '%s' ajoutée.", col_name)
                except Exception as exc:
                    log.debug("ProfileCache: migration '%s' ignorée — %s", col_name, exc)

    def _load_into_memory(self) -> None:
        """Charge toutes les entrées non-expirées en mémoire au démarrage."""
        now = time.time()
        max_ttl = max(self._ttl_hit, self._ttl_miss)
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "SELECT * FROM scraper_profile_cache WHERE last_seen > ?",
                    (now - max_ttl,),
                )
                for row in cur.fetchall():
                    self._store_in_memory(dict(row))
            log.debug("ProfileCache: %d entrées chargées depuis %s", len(self._by_url), self._db_path)
        except Exception as exc:
            log.warning("ProfileCache: échec du chargement mémoire — %s", exc)

    def _store_in_memory(self, row: dict) -> None:
        url = row.get("url", "")
        if not url:
            return
        self._by_url[url] = row
        if row.get("domain"):
            self._by_domain[row["domain"]] = url
        if row.get("phash"):
            self._by_phash[row["phash"]] = url

    # ── Lookup ────────────────────────────────────────────────────────────────

    def _ttl_for(self, row: dict) -> float:
        return self._ttl_hit if row.get("has_email") else self._ttl_miss

    def _row_is_fresh(self, row: dict) -> bool:
        age = time.time() - float(row.get("last_seen", 0))
        return age < self._ttl_for(row)

    def _find_row(self, url: str, domain: str = "", phash: str = "") -> dict | None:
        """Cherche par URL, puis domain, puis hash."""
        row = self._by_url.get(url)
        if row:
            return row
        if domain:
            u = self._by_domain.get(domain)
            if u:
                row = self._by_url.get(u)
                if row:
                    return row
        if phash:
            u = self._by_phash.get(phash)
            if u:
                row = self._by_url.get(u)
                if row:
                    return row
        return None

    def lookup(
        self,
        url: str,
        domain: str = "",
        phash: str = "",
    ) -> tuple[str, ScraperRecord | None]:
        """
        Retourne (status, record) :
          "hit"   → profil frais avec email  → utiliser le record directement
          "skip"  → profil frais sans email  → abandonner ce candidat
          "stale" → expiré ou inconnu        → enrichir normalement
        """
        if not self._enabled:
            return "stale", None

        url_key = _normalize_url(url)
        dom_key = _normalize_domain(domain) if domain else ""
        ph_key  = phash or ""

        with self._lock:
            row = self._find_row(url_key, dom_key, ph_key)

        if row is None or not self._row_is_fresh(row):
            self._misses += 1
            return "stale", None

        record = _row_to_record(row)
        if row.get("has_email"):
            self._hits += 1
            return "hit", record
        else:
            self._skipped += 1
            return "skip", None

    # ── Store ─────────────────────────────────────────────────────────────────

    def mark_seen(self, record: ScraperRecord, score: float | None = None) -> None:
        """Persiste un record après enrichissement (avec ou sans email)."""
        if not self._enabled:
            return
        url_key = _normalize_url(record.link or "")
        if not url_key:
            return

        row = _record_to_row(record, url_key)
        if score is not None:
            row["score"] = score
        with self._lock:
            self._store_in_memory(row)

        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO scraper_profile_cache
                        (url, domain, phash, last_seen, has_email,
                         nom, email, whatsapp, pays, entreprise, poste,
                         domaine, site_web, about, app, score)
                    VALUES
                        (:url, :domain, :phash, :last_seen, :has_email,
                         :nom, :email, :whatsapp, :pays, :entreprise, :poste,
                         :domaine, :site_web, :about, :app,
                         :score)
                    ON CONFLICT(url) DO UPDATE SET
                        domain    = excluded.domain,
                        phash     = excluded.phash,
                        last_seen = excluded.last_seen,
                        has_email = excluded.has_email,
                        nom       = excluded.nom,
                        email     = excluded.email,
                        whatsapp  = excluded.whatsapp,
                        pays      = excluded.pays,
                        entreprise= excluded.entreprise,
                        poste     = excluded.poste,
                        domaine   = excluded.domaine,
                        site_web  = excluded.site_web,
                        about     = excluded.about,
                        app       = excluded.app,
                        score     = COALESCE(excluded.score, scraper_profile_cache.score)
                    """,
                    {**row, "score": row.get("score")},
                )
            self._stores += 1
        except Exception as exc:
            log.warning("ProfileCache.mark_seen: %s", exc)

    # ── Maintenance ───────────────────────────────────────────────────────────

    def prune_expired(self) -> int:
        """Supprime les entrées expirées de SQLite. Appeler en début de run."""
        if not self._enabled:
            return 0
        now = time.time()
        cutoff_hit  = now - self._ttl_hit
        cutoff_miss = now - self._ttl_miss
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    DELETE FROM scraper_profile_cache
                    WHERE (has_email = 1 AND last_seen < ?)
                       OR (has_email = 0 AND last_seen < ?)
                    """,
                    (cutoff_hit, cutoff_miss),
                )
                deleted = cur.rowcount
            if deleted:
                log.debug("ProfileCache: %d entrées expirées supprimées.", deleted)
            return deleted
        except Exception as exc:
            log.warning("ProfileCache.prune_expired: %s", exc)
            return 0

    def invalidate(self, url: str) -> None:
        """Force la ré-enrichissement d'un profil spécifique."""
        if not self._enabled:
            return
        url_key = _normalize_url(url)
        with self._lock:
            self._by_url.pop(url_key, None)
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM scraper_profile_cache WHERE url = ?", (url_key,))
        except Exception as exc:
            log.warning("ProfileCache.invalidate: %s", exc)

    def clear_all(self) -> None:
        """Vide complètement le cache (équivalent --no-cache permanent)."""
        with self._lock:
            self._by_url.clear()
            self._by_domain.clear()
            self._by_phash.clear()
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM scraper_profile_cache")
        except Exception as exc:
            log.warning("ProfileCache.clear_all: %s", exc)

    # ── Outreach tracking ─────────────────────────────────────────────────────

    def mark_outreach_queued(self, url: str, score: float | None = None) -> None:
        """Marque un profil comme mis en file d'envoi email (idempotent)."""
        if not self._enabled:
            return
        url_key = _normalize_url(url)
        if not url_key:
            return
        now = time.time()
        with self._lock:
            row = self._by_url.get(url_key)
            if row:
                row["outreach_status"] = "queued"
                if score is not None:
                    row["score"] = score
        try:
            with self._connect() as conn:
                if score is not None:
                    conn.execute(
                        "UPDATE scraper_profile_cache SET outreach_status='queued', score=? WHERE url=?",
                        (score, url_key),
                    )
                else:
                    conn.execute(
                        "UPDATE scraper_profile_cache SET outreach_status='queued' WHERE url=?",
                        (url_key,),
                    )
        except Exception as exc:
            log.warning("ProfileCache.mark_outreach_queued: %s", exc)

    def mark_contacted(self, url: str) -> None:
        """Marque un profil comme contacté (email envoyé)."""
        if not self._enabled:
            return
        url_key = _normalize_url(url)
        if not url_key:
            return
        now = time.time()
        with self._lock:
            row = self._by_url.get(url_key)
            if row:
                row["outreach_status"] = "sent"
                row["contacted_at"] = now
        try:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE scraper_profile_cache SET outreach_status='sent', contacted_at=? WHERE url=?",
                    (now, url_key),
                )
        except Exception as exc:
            log.warning("ProfileCache.mark_contacted: %s", exc)

    def is_contacted(self, url: str) -> bool:
        """Retourne True si ce profil a déjà reçu un email."""
        if not self._enabled:
            return False
        url_key = _normalize_url(url)
        with self._lock:
            row = self._by_url.get(url_key)
            if row:
                return row.get("outreach_status") in ("sent",)
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "SELECT outreach_status FROM scraper_profile_cache WHERE url=?",
                    (url_key,),
                )
                row = cur.fetchone()
                return bool(row and row["outreach_status"] == "sent")
        except Exception:
            return False

    def is_outreach_queued(self, url: str) -> bool:
        """Retourne True si ce profil est déjà en file d'envoi ou déjà contacté."""
        if not self._enabled:
            return False
        url_key = _normalize_url(url)
        with self._lock:
            row = self._by_url.get(url_key)
            if row:
                return row.get("outreach_status") in ("queued", "sent")
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "SELECT outreach_status FROM scraper_profile_cache WHERE url=?",
                    (url_key,),
                )
                row = cur.fetchone()
                return bool(row and row["outreach_status"] in ("queued", "sent"))
        except Exception:
            return False

    def get_pending_outreach(self, limit: int = 200) -> list[ScraperRecord]:
        """
        Retourne les leads ACCEPTED (has_email=1) pas encore en file.
        Utile pour batch-processing des leads enrichis lors d'un run précédent.
        """
        if not self._enabled:
            return []
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    SELECT * FROM scraper_profile_cache
                    WHERE has_email = 1
                      AND (outreach_status IS NULL OR outreach_status = '')
                    ORDER BY last_seen DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                return [_row_to_record(dict(row)) for row in cur.fetchall()]
        except Exception as exc:
            log.warning("ProfileCache.get_pending_outreach: %s", exc)
            return []

    def sync_contacted_from_store(self) -> int:
        """
        Synchronise l'outreach_status depuis LeadStore (après un run d'envoi).
        Marque 'sent' dans le cache tous les leads dont le status est CONTACTED dans app.db.
        Retourne le nombre de records mis à jour.
        """
        if not self._enabled:
            return 0
        updated = 0
        try:
            from storage.database import Database
            db = Database()
            with db.connect() as conn:
                cur = conn.execute(
                    "SELECT link, email FROM leads WHERE status = 'contacted'"
                )
                rows = cur.fetchall()
            # Collecte toutes les URLs/emails pouvant correspondre à une entrée du cache
            contacted_links: list[str] = []
            for row in rows:
                if row["link"]:
                    contacted_links.append(row["link"])
                # Email channel : link peut être l'email — on tente aussi avec l'email
                # pour gérer les anciens leads injectés avant le fix
                if row["email"] and row["email"] not in contacted_links:
                    contacted_links.append(row["email"])
            for link in contacted_links:
                url_key = _normalize_url(link)
                if not url_key:
                    continue
                with self._lock:
                    row = self._by_url.get(url_key)
                    if row and row.get("outreach_status") != "sent":
                        row["outreach_status"] = "sent"
                try:
                    with self._connect() as conn:
                        conn.execute(
                            "UPDATE scraper_profile_cache SET outreach_status='sent' "
                            "WHERE url=? AND (outreach_status IS NULL OR outreach_status != 'sent')",
                            (url_key,),
                        )
                    updated += 1
                except Exception:
                    pass
        except Exception as exc:
            log.warning("ProfileCache.sync_contacted_from_store: %s", exc)
        return updated

    def stats(self) -> dict:
        return {
            "enabled":    self._enabled,
            "in_memory":  len(self._by_url),
            "hits":       self._hits,
            "skipped":    self._skipped,
            "misses":     self._misses,
            "stores":     self._stores,
            "hit_rate":   (
                f"{self._hits / max(1, self._hits + self._skipped + self._misses):.1%}"
            ),
        }


# ── Singleton par run ─────────────────────────────────────────────────────────
# Une seule instance par process — partagée entre tous les appels collectors.

_cache_instance: ProfileCache | None = None
_cache_lock = threading.Lock()


def get_profile_cache() -> ProfileCache:
    """Retourne (ou crée) l'instance singleton du cache pour ce run."""
    global _cache_instance
    if _cache_instance is not None:
        return _cache_instance
    with _cache_lock:
        if _cache_instance is not None:
            return _cache_instance
        from config import settings
        enabled  = bool(getattr(settings, "scraper_profile_cache_enabled", True))
        db_path  = str(getattr(settings, "scraper_profile_cache_path", "data/scraper_cache.db"))
        ttl_hit  = float(getattr(settings, "scraper_profile_cache_ttl_days", 7)) * 86400
        ttl_miss = float(getattr(settings, "scraper_profile_cache_ttl_no_email_days", 1)) * 86400
        inst = ProfileCache(
            db_path=db_path,
            ttl_with_email=ttl_hit,
            ttl_no_email=ttl_miss,
            enabled=enabled,
        )
        inst.prune_expired()
        _cache_instance = inst
        return inst


def reset_profile_cache(*, enabled: bool | None = None, clear: bool = False) -> ProfileCache:
    """
    Réinitialise le singleton (utilisé par --no-cache CLI et les tests).
    Si clear=True, vide aussi la base SQLite.
    """
    global _cache_instance
    with _cache_lock:
        if _cache_instance and clear:
            _cache_instance.clear_all()
        from config import settings
        _enabled = enabled if enabled is not None else bool(
            getattr(settings, "scraper_profile_cache_enabled", True)
        )
        db_path  = str(getattr(settings, "scraper_profile_cache_path", "data/scraper_cache.db"))
        ttl_hit  = float(getattr(settings, "scraper_profile_cache_ttl_days", 7)) * 86400
        ttl_miss = float(getattr(settings, "scraper_profile_cache_ttl_no_email_days", 1)) * 86400
        inst = ProfileCache(
            db_path=db_path,
            ttl_with_email=ttl_hit,
            ttl_no_email=ttl_miss,
            enabled=_enabled,
        )
        if not clear:
            inst.prune_expired()
        _cache_instance = inst
        return inst
