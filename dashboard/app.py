from __future__ import annotations

import shutil

import pandas as pd
import streamlit as st

from compliance.registry import ComplianceRegistry
from config import settings
from connector.ingest import QueueIngestor
from dashboard.services import (
    load_jsonl,
    load_leads_frame,
    load_opt_out_frame,
    load_queue,
    load_scraper_frame,
    run_channel_isolated,
    run_pipeline_isolated,
    run_email_campaign_isolated,
    run_scraper_isolated,
    run_web_scraper_isolated,
    snapshot,
)
from dashboard.content_tab import render_content
from dashboard.theme import DASHBOARD_CSS
from leads.store import LeadStore
from utils.outreach_logger import OutreachLogger
from scraper.cli import ScraperRunResult
from scraper.instagram_login import (
    instagram_password_login_configured,
    instagram_session_storage_ready,
)
from scraper.country_presets import TUNISIA_EXCLUDE_PRESET, country_labels, keywords_for_country_form
from scraper.query_parse import split_scraper_queries
from utils.smtp_config import smtp_configured
from scraper.models import is_empty_value


def ensure_auth() -> None:
    if not settings.dashboard_password:
        return
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return
    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="hero"><h1>Outreach Platform</h1>'
        "<p>Connectez-vous pour accéder au centre de contrôle.</p></div>",
        unsafe_allow_html=True,
    )
    password = st.text_input("Mot de passe dashboard", type="password")
    if password == settings.dashboard_password:
        st.session_state.authenticated = True
        st.rerun()
    st.stop()


def render_header() -> None:
    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <div class="hero">
          <h1>AI Acquisition OS</h1>
          <p>Acquisition (scraper, outreach) + Content OS (posts LinkedIn, calendrier, publication).</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_overview(data: dict) -> None:
    metrics = data["outreach_metrics"]
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    cards = [
        ("Envoyés", metrics["sent"]),
        ("Échecs", metrics["failed"]),
        ("Réponses", metrics["replies"]),
        ("Succès", f"{metrics['success_rate']}%"),
        ("File", data["queue_size"]),
        ("Traités", data["processed"]),
    ]
    for col, (label, value) in zip((c1, c2, c3, c4, c5, c6), cards):
        col.markdown(
            f'<div class="metric-card"><div class="metric-label">{label}</div>'
            f'<div class="metric-value">{value}</div></div>',
            unsafe_allow_html=True,
        )

    left, right = st.columns(2)
    with left:
        st.markdown('<div class="section-title">Statuts des leads</div>', unsafe_allow_html=True)
        if data["lead_stats"]:
            st.bar_chart(data["lead_stats"])
        else:
            st.info("Aucun lead pour le moment.")
    with right:
        st.markdown('<div class="section-title">Envois par canal</div>', unsafe_allow_html=True)
        if metrics["by_channel"]:
            st.bar_chart(metrics["by_channel"])
        else:
            st.caption("Aucun envoi enregistré.")


def render_pipeline() -> None:
    st.markdown('<div class="section-title">Pilotage du pipeline</div>', unsafe_allow_html=True)
    with st.container():
        source = st.selectbox("Source connecteur", ["csv", "sqlite", "mongo"], index=0)
        limit = st.number_input("Limite par canal", min_value=1, max_value=100, value=5)
        retry = st.checkbox("Réessayer les échecs connecteur", value=False)
        run_scraper = st.checkbox("Lancer la commande scraper (SCRAPER_COMMAND)", value=True)
        run_outreach = st.checkbox("Lancer l'outreach après ingest", value=True)

        col1, col2, col3 = st.columns(3)
        if col1.button("Exécuter le pipeline complet"):
            with st.spinner("Exécution en cours..."):
                try:
                    result = run_pipeline_isolated(
                        source=source,
                        retry_failed=retry,
                        per_channel_limit=int(limit),
                        run_scraper_step=run_scraper,
                        run_outreach=run_outreach,
                    )
                except RuntimeError as exc:
                    st.error(str(exc))
                else:
                    st.success("Pipeline terminé.")
                    st.json(result)

        if col2.button("Connecteur + ingest seulement"):
            with st.spinner("Connecteur..."):
                try:
                    result = run_pipeline_isolated(
                        source=source,
                        retry_failed=retry,
                        per_channel_limit=None,
                        run_scraper_step=run_scraper,
                        run_outreach=False,
                    )
                except RuntimeError as exc:
                    st.error(str(exc))
                else:
                    st.json(result)

        if col3.button("Ingest manuel de la file"):
            result = QueueIngestor().ingest()
            st.success(
                f"Ingestés: {result.ingested} | Ignorés: {result.skipped} | Opt-out: {result.opted_out}"
            )

    st.markdown('<div class="section-title">Lancer un canal</div>', unsafe_allow_html=True)
    channel = st.selectbox("Canal", ["linkedin", "instagram", "whatsapp", "email"])
    channel_limit = st.number_input("Limite pour ce canal", min_value=1, max_value=50, value=3, key="channel_limit")
    if st.button(f"Envoyer sur {channel}"):
        with st.spinner(f"Outreach {channel}..."):
            try:
                sent = run_channel_isolated(channel, limit=int(channel_limit))
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                st.success(f"{sent} message(s) envoyé(s) sur {channel}.")


def render_leads() -> None:
    st.markdown('<div class="section-title">Leads outreach</div>', unsafe_allow_html=True)
    df = load_leads_frame()
    if df.empty:
        st.info("Aucun lead dans le store outreach.")
    else:
        status_filter = st.multiselect(
            "Filtrer par statut",
            sorted(df["status"].unique().tolist()) if "status" in df.columns else [],
            default=[],
        )
        channel_filter = st.multiselect(
            "Filtrer par canal",
            sorted(df["channel"].unique().tolist()) if "channel" in df.columns else [],
            default=[],
        )
        view = df.copy()
        if status_filter:
            view = view[view["status"].isin(status_filter)]
        if channel_filter:
            view = view[view["channel"].isin(channel_filter)]
        st.dataframe(view, use_container_width=True, hide_index=True)

    st.markdown('<div class="section-title">Importer vers le scraper</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader("CSV scraper (name, company, link, email, phone...)", type=["csv"])
    replace = st.checkbox("Remplacer le fichier scraper existant", value=False)
    if uploaded is not None and st.button("Importer et lancer le pipeline"):
        target = settings.path(settings.scraper_output_csv)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = settings.path("leads/_upload.csv")
        temp.write_bytes(uploaded.getvalue())
        if replace:
            shutil.copyfile(temp, target)
        else:
            if target.exists():
                existing = target.read_text(encoding="utf-8").splitlines()
                incoming = temp.read_text(encoding="utf-8").splitlines()
                merged = existing + incoming[1:] if incoming else existing
                target.write_text("\n".join(merged) + "\n", encoding="utf-8")
            else:
                shutil.copyfile(temp, target)
        try:
            result = run_pipeline_isolated(
                source="csv",
                retry_failed=False,
                per_channel_limit=None,
                run_scraper_step=False,
                run_outreach=True,
            )
        except RuntimeError as exc:
            st.error(str(exc))
        else:
            st.success("Import et pipeline terminés.")
            st.json(result)

    st.markdown('<div class="section-title">Marquer une réponse</div>', unsafe_allow_html=True)
    lead_id = st.text_input("ID du lead")
    snippet = st.text_area("Extrait de réponse", height=80)
    if st.button("Marquer comme répondu") and lead_id.strip():
        store = LeadStore()
        logger = OutreachLogger()
        store.mark_replied(lead_id.strip())
        logger.log_reply(lead_id.strip(), channel="manual", snippet=snippet)
        st.success("Lead marqué comme répondu.")


def render_queue() -> None:
    st.markdown('<div class="section-title">File bot</div>', unsafe_allow_html=True)
    queue = load_queue()
    if not queue:
        st.info("La file est vide.")
        return
    st.dataframe(
        [
            {
                "fingerprint": item.get("fingerprint", "")[:12],
                "name": (item.get("lead") or {}).get("name", ""),
                "company": (item.get("lead") or {}).get("company", ""),
                "email": (item.get("lead") or {}).get("email", ""),
                "tag": (item.get("lead") or {}).get("tag", ""),
                "enqueued_at": item.get("enqueued_at", ""),
            }
            for item in queue
        ],
        use_container_width=True,
        hide_index=True,
    )


def render_logs() -> None:
    log_dir = settings.path(settings.log_dir)
    sent = load_jsonl(log_dir / "sent.jsonl")
    failed = load_jsonl(log_dir / "failed.jsonl")
    replies = load_jsonl(log_dir / "replies.jsonl")
    tab1, tab2, tab3 = st.tabs(["Envoyés", "Échecs", "Réponses"])
    with tab1:
        st.dataframe(pd.DataFrame(sent), use_container_width=True, hide_index=True)
    with tab2:
        st.dataframe(pd.DataFrame(failed), use_container_width=True, hide_index=True)
    with tab3:
        st.dataframe(pd.DataFrame(replies), use_container_width=True, hide_index=True)


def render_compliance() -> None:
    st.markdown('<div class="section-title">Registre opt-out</div>', unsafe_allow_html=True)
    st.dataframe(load_opt_out_frame(), use_container_width=True, hide_index=True)
    identifier = st.text_input("Identifiant à bloquer (email, URL profil, nom)")
    reason = st.text_input("Raison", value="user_request")
    if st.button("Enregistrer l'opt-out") and identifier.strip():
        ComplianceRegistry().register_opt_out(identifier.strip(), reason)
        st.success("Opt-out enregistré.")


def render_settings(data: dict) -> None:
    st.markdown('<div class="section-title">Configuration active</div>', unsafe_allow_html=True)
    st.json(
        {
            "ai_provider": settings.ai_provider,
            "ollama_model": settings.ollama_model,
            "openai_model": settings.openai_model,
            "orchestrator_interval_hours": settings.orchestrator_interval_hours,
            "orchestrator_headless": settings.orchestrator_headless,
            "storage_backend": settings.storage_backend,
            "connector_export_mode": settings.connector_export_mode,
            "paths": data["paths"],
            "sessions": data["session_files"],
        }
    )
    st.markdown('<div class="section-title">Limites journalières restantes</div>', unsafe_allow_html=True)
    st.dataframe(
        [
            {
                "canal": channel,
                "restant": values["remaining"],
                "max_jour": values["daily_max"],
            }
            for channel, values in data["rate_limits"].items()
        ],
        use_container_width=True,
        hide_index=True,
    )


def render_guide() -> None:
    steps = [
        ("1. Préparer l'environnement", "Créez le venv, installez les dépendances, copiez `.env.example` vers `.env`, configurez SMTP, IA et `DASHBOARD_PASSWORD`."),
        ("2. Alimenter le scraper", "Onglet **Scraper** : 3 colonnes (LinkedIn, Instagram, Web/Google), chacune avec **mot-clé**, **pays** et **exclure Tunisie** indépendants. CSV : `SCRAPER_OUTPUT_CSV`, `SCRAPER_INSTAGRAM_OUTPUT_CSV`, `SCRAPER_WEB_OUTPUT_CSV`."),
        ("3. Lancer le pipeline", "Utilisez `python run.py run --source csv` ou l'onglet Pipeline de ce dashboard pour connecter, mettre en file, ingérer et envoyer."),
        ("4. Sessions sociales", "Importez la session depuis Chrome ou Edge déjà connecté: `python outreach.py login instagram --from-browser chrome`. Pour un onglet déjà ouvert, lancez Chrome avec `--remote-debugging-port=9222`, mettez `BROWSER_CONNECTION_MODE=cdp`, puis `python outreach.py login instagram --cdp`."),
        ("5. Suivre les relances", "Les relances sont gérées dans le store outreach selon `next_follow_up_at`. Marquez une réponse depuis l'onglet Leads ou `python outreach.py reply <id>`."),
        ("6. Automatiser", "`python run.py schedule --hours 6 --limit 5` exécute le pipeline complet en boucle."),
        ("7. API externe", "Démarrez `uvicorn api.main:app` et appelez `POST /orchestrator/run` avec la clé `X-API-Key`."),
    ]
    for title, body in steps:
        st.markdown(
            f'<div class="guide-step"><strong>{title}</strong><br>{body}</div>',
            unsafe_allow_html=True,
        )


def _scraper_dataframe_kwargs(frame: pd.DataFrame) -> dict:
    column_config: dict = {}
    if "whatsapp_link" in frame.columns:
        column_config["whatsapp_link"] = st.column_config.LinkColumn(
            "WhatsApp",
            help="Lien api.whatsapp.com (numéro international, sans +)",
        )
    if "whatsapp_verif" in frame.columns:
        column_config["whatsapp_verif"] = st.column_config.TextColumn(
            "WhatsApp (vérif)",
            help="oui / non / inconnu — mode gratuit = filtre type de ligne (phonenumbers) ; webhook = votre API",
        )
    if "link" in frame.columns:
        column_config["link"] = st.column_config.LinkColumn("Lien", width="medium")
    kwargs: dict = {"use_container_width": True, "hide_index": True}
    if column_config:
        kwargs["column_config"] = column_config
    return kwargs


def _scraper_rows_with_email(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "email" not in frame.columns:
        return pd.DataFrame()
    mask = ~frame["email"].astype(str).map(is_empty_value)
    return frame.loc[mask].copy()


def _scraper_rows_with_whatsapp(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    parts: list[pd.Series] = []
    if "whatsapp" in frame.columns:
        parts.append(~frame["whatsapp"].astype(str).map(is_empty_value))
    if "whatsapp_link" in frame.columns:
        parts.append(~frame["whatsapp_link"].astype(str).map(is_empty_value))
    if not parts:
        return pd.DataFrame()
    mask = parts[0]
    for p in parts[1:]:
        mask = mask | p
    return frame.loc[mask].copy()


def render_scraper_table(title: str = "Résultats scraper", *, app: str | None = None) -> None:
    frame = load_scraper_frame(app)
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    if frame.empty:
        st.info("Aucune ligne à afficher pour le moment.")
        return
    kwargs = _scraper_dataframe_kwargs(frame)
    st.dataframe(frame, **kwargs)

    with_email = _scraper_rows_with_email(frame)
    if not with_email.empty:
        st.markdown('<div class="section-title">Avec e-mail</div>', unsafe_allow_html=True)
        st.dataframe(with_email, **_scraper_dataframe_kwargs(with_email))

    with_wa = _scraper_rows_with_whatsapp(frame)
    if not with_wa.empty:
        st.markdown('<div class="section-title">Avec WhatsApp</div>', unsafe_allow_html=True)
        st.dataframe(with_wa, **_scraper_dataframe_kwargs(with_wa))


def _column_geo_kwargs(prefix: str) -> dict[str, str | None]:
    """Filtre pays / exclusion propre à chaque colonne (LinkedIn, Instagram, Web)."""
    st.caption("Pays")
    geo_filter = st.radio(
        "Filtrage géographique",
        options=["all", "include"],
        format_func=lambda key: {
            "all": "Tous",
            "include": "Pays choisis",
        }[key],
        horizontal=True,
        key=f"{prefix}_geo_filter",
        label_visibility="collapsed",
    )
    selected_countries: list[str] = []
    extra_geo = ""
    if geo_filter == "include":
        selected_countries = st.multiselect(
            "Pays à garder",
            options=country_labels(),
            default=[],
            key=f"{prefix}_include_countries",
        )
        extra_geo = st.text_input(
            "Mots en plus",
            value="",
            placeholder="ex: dubai, qatar",
            key=f"{prefix}_include_extra",
        )
    exclude_default = prefix != "web"
    exclude_tn = st.checkbox(
        "Exclure Tunisie",
        value=exclude_default,
        key=f"{prefix}_exclude_tunisia",
        help="Web : décochez pour garder les contacts .tn / +216. "
        "« Pays choisis » ne s'applique pas aux sites (utilisez la requête Bing).",
    )
    include_kw = (
        keywords_for_country_form(selected_countries, extra_geo) if geo_filter == "include" else ()
    )
    include_str = ",".join(include_kw)
    if exclude_tn:
        env_excl = (getattr(settings, "scraper_exclude_location_keywords", "") or "").strip()
        exclude_str = env_excl if env_excl else ",".join(TUNISIA_EXCLUDE_PRESET)
    else:
        exclude_str = "__none__"
    return {"include_location": include_str, "exclude_location": exclude_str}


def render_scraper() -> None:
    st.markdown('<div class="section-title">Scraper</div>', unsafe_allow_html=True)
    data = snapshot()
    if data["session_files"]:
        st.caption(f"Sessions détectées: {', '.join(data['session_files'])}")
    else:
        st.warning(
            "Aucune session pour LinkedIn/Instagram. Web (Google) n'en a pas besoin. "
            "`python outreach.py login linkedin` ou `login instagram`."
        )
    st.markdown('<div class="section-title">Collecte</div>', unsafe_allow_html=True)
    st.caption(
        "Trois colonnes indépendantes : mot-clé, pays et exclusions **par canal**. "
        "LinkedIn → `SCRAPER_OUTPUT_CSV` · Instagram → `SCRAPER_INSTAGRAM_OUTPUT_CSV` · "
        "Web → `SCRAPER_WEB_OUTPUT_CSV`."
    )

    def run_scraper_with_progress_bar(
        *,
        mode: str,
        app: str,
        query: str,
        limit: int,
        replace: bool,
        linkedin_scopes: list[str],
        geo: dict[str, str | None],
    ) -> ScraperRunResult:
        progress = st.progress(0, text="0% — Préparation…")
        detail = st.empty()

        def on_progress(payload: dict) -> None:
            frac = min(1.0, max(0.0, float(payload.get("fraction", 0))))
            pct = int(round(frac * 100))
            msg = str(payload.get("message") or payload.get("phase") or "…")
            label = f"{pct}% — {msg}"
            progress.progress(frac, text=label)
            detail.markdown(f"**{pct}%** · {msg}")

        try:
            return run_scraper_isolated(
                mode=mode,
                app=app,
                query=query,
                limit=int(limit),
                append=not replace,
                linkedin_scopes=linkedin_scopes if app == "linkedin" else [],
                include_location=geo["include_location"],
                exclude_location=geo["exclude_location"],
                on_progress=on_progress,
            )
        finally:
            detail.empty()

    def run_web_with_progress_bar(
        *,
        mode: str,
        query: str,
        limit: int,
        replace: bool,
        geo: dict[str, str | None],
        search_provider: str,
    ) -> ScraperRunResult:
        progress = st.progress(0, text="0% — Préparation…")
        detail = st.empty()

        def on_progress(payload: dict) -> None:
            frac = min(1.0, max(0.0, float(payload.get("fraction", 0))))
            pct = int(round(frac * 100))
            msg = str(payload.get("message") or payload.get("phase") or "…")
            progress.progress(frac, text=f"{pct}% — {msg}")
            detail.markdown(f"**{pct}%** · {msg}")

        try:
            return run_web_scraper_isolated(
                mode=mode,
                query=query,
                limit=int(limit),
                append=not replace,
                include_location=geo["include_location"],
                exclude_location=geo["exclude_location"],
                search_provider=search_provider,
                on_progress=on_progress,
            )
        finally:
            detail.empty()

    col_li, col_ig, col_web = st.columns(3, gap="medium")

    with col_li:
        st.markdown("**LinkedIn**")
        if getattr(settings, "scraper_linkedin_require_email_or_whatsapp", True):
            st.caption(
                "Priorité **e-mail** : seuls les profils avec une adresse e-mail sont enregistrés. "
                "Le scraper ouvre le menu **⋯** LinkedIn → Coordonnées, puis « Voir plus », "
                "puis le site web (accueil, contact, mentions légales) si besoin."
            )
        li_mode = st.selectbox("Mode", ["keyword", "hashtag"], index=0, key="linkedin_scraper_mode")
        li_query = st.text_input(
            "Mot-clé ou hashtag",
            value="",
            placeholder="ex: founder, CEO, marketing  (virgule ou retour ligne)",
            key="linkedin_scraper_query",
            help="Plusieurs termes : séparez par virgule, point-virgule ou une ligne par mot-clé. "
            "Une phrase avec espaces = une seule recherche (ex. marketing digital).",
        )
        li_geo = _column_geo_kwargs("linkedin")
        li_scope = st.radio(
            "Cible de recherche",
            ("both", "people", "companies"),
            index=0,
            format_func=lambda key: {
                "both": "Personnes et entreprises",
                "people": "Personnes uniquement",
                "companies": "Entreprises uniquement",
            }[key],
            horizontal=True,
            key="linkedin_scraper_scope",
            help="Personnes = profils /in/… ; Entreprises = pages /company/… ; les deux enchaîne deux recherches.",
        )
        li_scopes = ["people", "companies"] if li_scope == "both" else [li_scope]
        if li_query.strip():
            n_kw = len(split_scraper_queries(li_query.strip(), mode=li_mode))
            n_steps = n_kw * len(li_scopes)
            if n_steps > 12:
                st.warning(
                    f"**{n_kw} mots-clés × {len(li_scopes)} catégorie(s) = {n_steps} recherches LinkedIn.** "
                    f"Cela peut dépasser 1 h (enrichissement des profils). Conseil : 5–8 mots-clés max, "
                    f"ou « Personnes uniquement », ou `SCRAPER_FAST_MODE=true` dans `.env`."
                )
            else:
                st.caption(
                    f"Prévu : {n_kw} mot(s)-clé × {len(li_scopes)} catégorie(s) = **{n_steps}** recherche(s) LinkedIn."
                )
        li_limit = st.number_input(
            "Nombre de leads par catégorie",
            min_value=1,
            max_value=100,
            value=10,
            key="linkedin_scraper_limit",
        )
        li_replace = st.checkbox("Remplacer le fichier scraper", value=False, key="linkedin_scraper_replace")
        if st.button("Lancer le scraper LinkedIn", type="primary", key="linkedin_scraper_run"):
            if not li_query.strip():
                st.error("Indiquez un mot-clé ou un hashtag.")
            elif not li_scopes:
                st.error("Sélectionnez au moins une catégorie LinkedIn.")
            else:
                try:
                    if st.session_state.get("linkedin_geo_filter") == "include" and not li_geo["include_location"]:
                        raise ValueError("LinkedIn : choisissez au moins un pays à garder.")
                    result = run_scraper_with_progress_bar(
                        mode=li_mode,
                        app="linkedin",
                        query=li_query,
                        limit=int(li_limit),
                        replace=li_replace,
                        linkedin_scopes=li_scopes,
                        geo=li_geo,
                    )
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    if result.error:
                        st.error(result.error)
                    else:
                        st.success(f"{result.written} lead(s) écrits dans {result.output_path}")
                        render_scraper_table(app="linkedin")
        if st.button("LinkedIn puis pipeline complet", key="linkedin_scraper_pipeline"):
            if not li_query.strip():
                st.error("Indiquez un mot-clé ou un hashtag.")
                return
            if not li_scopes:
                st.error("Sélectionnez au moins une catégorie LinkedIn.")
                return
            try:
                if st.session_state.get("linkedin_geo_filter") == "include" and not li_geo["include_location"]:
                    raise ValueError("LinkedIn : choisissez au moins un pays à garder.")
                result = run_scraper_with_progress_bar(
                    mode=li_mode,
                    app="linkedin",
                    query=li_query,
                    limit=int(li_limit),
                    replace=li_replace,
                    linkedin_scopes=li_scopes,
                    geo=li_geo,
                )
            except ValueError as exc:
                st.error(str(exc))
                return
            if result.error:
                st.error(result.error)
                return
            render_scraper_table("Leads scrapés (LinkedIn)", app="linkedin")
            try:
                pipeline = run_pipeline_isolated(
                    source="csv",
                    retry_failed=False,
                    per_channel_limit=None,
                    run_scraper_step=False,
                    run_outreach=True,
                )
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                st.json(pipeline)

    with col_ig:
        st.markdown("**Instagram**")
        if instagram_session_storage_ready():
            st.caption(
                "Session **`sessions/instagram.json`** détectée : le scraper l’utilise en priorité "
                "(identifiants `.env` ignorés tant que ce fichier existe)."
            )
        elif instagram_password_login_configured():
            uname = (settings.instagram_username or "").strip()
            st.caption(f"Connexion automatique : compte **{uname}** (`INSTAGRAM_*` dans `.env`, sans fichier session).")
        else:
            st.caption(
                "Sans fichier `sessions/instagram.json` : `python outreach.py login instagram` "
                "(ou identifiants `INSTAGRAM_USERNAME` / `INSTAGRAM_PASSWORD` dans `.env`)."
            )
        ig_mode = st.selectbox("Mode", ["keyword", "hashtag"], index=0, key="instagram_scraper_mode")
        ig_query = st.text_input(
            "Mot-clé ou hashtag",
            value="",
            placeholder="ex: design, startup  ou  #design #marketing",
            key="instagram_scraper_query",
            help="Plusieurs termes : virgule / retour ligne, ou plusieurs #hashtag. "
            "Mode hashtag : un tag par recherche.",
        )
        ig_geo = _column_geo_kwargs("instagram")
        ig_limit = st.number_input(
            "Nombre de profils",
            min_value=1,
            max_value=100,
            value=10,
            key="instagram_scraper_limit",
        )
        ig_replace = st.checkbox("Remplacer le fichier scraper", value=False, key="instagram_scraper_replace")
        if st.button("Lancer le scraper Instagram", type="primary", key="instagram_scraper_run"):
            if not ig_query.strip():
                st.error("Indiquez un hashtag ou un mot-clé.")
            else:
                try:
                    if st.session_state.get("instagram_geo_filter") == "include" and not ig_geo["include_location"]:
                        raise ValueError("Instagram : choisissez au moins un pays à garder.")
                    result = run_scraper_with_progress_bar(
                        mode=ig_mode,
                        app="instagram",
                        query=ig_query,
                        limit=int(ig_limit),
                        replace=ig_replace,
                        linkedin_scopes=[],
                        geo=ig_geo,
                    )
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    if result.error:
                        st.error(result.error)
                    else:
                        st.success(f"{result.written} lead(s) écrits dans {result.output_path}")
                        render_scraper_table(app="instagram")
        if st.button("Instagram puis pipeline complet", key="instagram_scraper_pipeline"):
            if not ig_query.strip():
                st.error("Indiquez un hashtag ou un mot-clé.")
                return
            try:
                if st.session_state.get("instagram_geo_filter") == "include" and not ig_geo["include_location"]:
                    raise ValueError("Instagram : choisissez au moins un pays à garder.")
                result = run_scraper_with_progress_bar(
                    mode=ig_mode,
                    app="instagram",
                    query=ig_query,
                    limit=int(ig_limit),
                    replace=ig_replace,
                    linkedin_scopes=[],
                    geo=ig_geo,
                )
            except ValueError as exc:
                st.error(str(exc))
                return
            if result.error:
                st.error(result.error)
                return
            render_scraper_table("Leads scrapés (Instagram)", app="instagram")
            try:
                pipeline = run_pipeline_isolated(
                    source="csv",
                    retry_failed=False,
                    per_channel_limit=None,
                    run_scraper_step=False,
                    run_outreach=True,
                )
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                st.json(pipeline)

    with col_web:
        st.markdown("**Web (Google)**")
        st.caption("Recherche Google → sites → e-mails. Pas de LinkedIn.")
        web_mode = st.selectbox("Mode", ["keyword", "hashtag"], index=0, key="web_scraper_mode")
        web_query = st.text_input(
            "Requête Google",
            value="",
            placeholder="ex: agence événementiel Paris contact email",
            key="web_scraper_query",
        )
        st.caption("Web : pas de filtre pays (la requête Bing cible déjà la zone).")
        web_geo = {"include_location": "", "exclude_location": "__none__"}
        web_provider = st.selectbox(
            "Moteur",
            ["auto", "google_playwright", "google_cse", "bing", "duckduckgo"],
            index=0,
            key="web_scraper_provider",
        )
        web_limit = st.number_input(
            "Nombre de sites",
            min_value=1,
            max_value=50,
            value=10,
            key="web_scraper_limit",
        )
        web_replace = st.checkbox("Remplacer le CSV web", value=False, key="web_scraper_replace")
        if st.button("Lancer Google → sites", type="primary", key="web_scraper_run"):
            if not web_query.strip():
                st.error("Indiquez une requête Google.")
            else:
                try:
                    result = run_web_with_progress_bar(
                        mode=web_mode,
                        query=web_query,
                        limit=int(web_limit),
                        replace=web_replace,
                        geo=web_geo,
                        search_provider=web_provider if web_provider != "auto" else "",
                    )
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    if result.error:
                        st.error(result.error)
                    else:
                        st.success(f"{result.written} lead(s) → {result.output_path}")
                        render_scraper_table(app="web")

    st.markdown('<div class="section-title">Résultats par canal</div>', unsafe_allow_html=True)
    res_li, res_ig, res_web = st.columns(3, gap="medium")
    with res_li:
        render_scraper_table("LinkedIn", app="linkedin")
    with res_ig:
        render_scraper_table("Instagram", app="instagram")
    with res_web:
        render_scraper_table("Web (Google)", app="web")

    st.markdown('<div class="section-title">E-mails automatiques</div>', unsafe_allow_html=True)
    if smtp_configured():
        st.caption(
            f"Expéditeur SMTP : **{settings.smtp_from or settings.smtp_user}** · "
            f"Limite journalière : {settings.email_daily_max} e-mails/jour."
        )
    else:
        st.warning(
            "Configurez **SMTP_USER**, **SMTP_PASSWORD** et **SMTP_FROM** dans `.env` pour activer l'envoi."
        )
    email_limit = st.number_input(
        "Nombre max d'e-mails à envoyer maintenant",
        min_value=1,
        max_value=min(50, settings.email_daily_max),
        value=min(10, settings.email_daily_max),
        key="email_campaign_limit",
    )
    st.caption(
        "Importe les profils du CSV scraper (avec e-mail), génère un message **personnalisé par profil** "
        "(nom, entreprise, poste, bio) puis envoie via SMTP. Seuls les leads avec adresse e-mail sont traités."
    )
    if st.button("Envoyer les e-mails aux profils scrapés", type="primary", key="email_campaign_run"):
        if not smtp_configured():
            st.error("SMTP non configuré dans `.env`.")
        else:
            with st.spinner("Import des leads et envoi des e-mails…"):
                try:
                    campaign = run_email_campaign_isolated(limit=int(email_limit))
                except Exception as exc:
                    st.error(str(exc))
                else:
                    if campaign.get("errors"):
                        for err in campaign["errors"]:
                            st.error(err)
                    sent = int(campaign.get("emails_sent", 0))
                    ingested = int(campaign.get("ingested", 0))
                    if sent > 0:
                        st.success(f"{sent} e-mail(s) envoyé(s) ({ingested} lead(s) importé(s) avec e-mail).")
                    elif ingested == 0:
                        st.info(
                            "Aucun nouveau profil avec e-mail à traiter. Lancez d'abord le scraper "
                            "ou vérifiez que le CSV contient une colonne `email` remplie."
                        )
                    else:
                        st.info(
                            "Leads importés mais aucun envoi (quota journalier atteint, opt-out, "
                            "ou leads déjà contactés). Consultez l'onglet Logs."
                        )
                    st.json(campaign)


def main() -> None:
    st.set_page_config(page_title="AI Acquisition OS", layout="wide", page_icon="◎")
    ensure_auth()
    render_header()
    data = snapshot()
    tabs = st.tabs(
        [
            "Vue d'ensemble",
            "Scraper",
            "Content OS",
            "Pipeline",
            "Leads",
            "File",
            "Logs",
            "Conformité",
            "Guide",
            "Paramètres",
        ]
    )
    with tabs[0]:
        render_overview(data)
    with tabs[1]:
        render_scraper()
    with tabs[2]:
        render_content()
    with tabs[3]:
        render_pipeline()
    with tabs[4]:
        render_leads()
    with tabs[5]:
        render_queue()
    with tabs[6]:
        render_logs()
    with tabs[7]:
        render_compliance()
    with tabs[8]:
        render_guide()
    with tabs[9]:
        render_settings(data)


if __name__ == "__main__":
    main()
