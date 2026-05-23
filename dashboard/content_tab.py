"""Onglet Streamlit — AI LinkedIn Content OS."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import streamlit as st

from content.generation.service import generate_hooks, generate_post
from content.models import GenerateHookRequest, GeneratePostRequest
from content.optimization.recommendations import get_recommendations
from content.store import ContentStore
from workers.content_jobs import execute_content_job
from workers.queue import ScraperJob


def render_content() -> None:
    st.subheader("AI LinkedIn Content OS")
    store = ContentStore()
    store.ensure_default_tenant()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Brouillons", len(store.list_drafts(limit=200)))
    with col2:
        st.metric("Planifiés", len(store.list_posts(status="scheduled", limit=200)))
    with col3:
        st.metric("Publiés aujourd'hui", store.posts_published_today_count())

    tab_gen, tab_cal, tab_pub, tab_opt = st.tabs(
        ["Génération IA", "Calendrier", "Publication", "Optimisation"]
    )

    with tab_gen:
        topic = st.text_input("Sujet", value="automation B2B outbound")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Générer hooks"):
                hooks = generate_hooks(GenerateHookRequest(topic=topic, count=5))
                for h in hooks:
                    st.write(f"• {h.text}")
        with c2:
            if st.button("Générer post complet"):
                draft = generate_post(GeneratePostRequest(topic=topic))
                saved = store.create_draft(
                    body=draft.body,
                    hook=draft.hook,
                    cta=draft.cta,
                    format=draft.format.value,
                )
                st.success(f"Brouillon enregistré : {saved['id']}")
                st.text_area("Aperçu", value=draft.body, height=200)

    with tab_cal:
        drafts = store.list_drafts(status="draft", limit=20)
        if not drafts:
            st.info("Aucun brouillon. Générez un post dans l'onglet Génération.")
        else:
            labels = [f"{d.get('title') or d['id'][:8]} — {d['body'][:40]}..." for d in drafts]
            pick = st.selectbox("Brouillon", range(len(drafts)), format_func=lambda i: labels[i])
            when = st.datetime_input(
                "Date/heure publication",
                value=datetime.now(timezone.utc) + timedelta(days=1),
            )
            if st.button("Planifier"):
                d = drafts[pick]
                post = store.create_post_from_draft(d["id"])
                store.schedule_post(post["id"], when.isoformat())
                st.success(f"Post planifié : {post['id']}")

        st.markdown("#### Calendrier")
        slots = store.list_calendar()
        if slots:
            st.dataframe(
                [
                    {
                        "slot": s.get("slot_start"),
                        "status": s.get("status"),
                        "extrait": (s.get("body") or "")[:60],
                    }
                    for s in slots
                ],
                use_container_width=True,
            )
        else:
            st.caption("Aucun créneau planifié.")

    with tab_pub:
        posts = store.list_posts(limit=30)
        for p in posts:
            with st.expander(f"{p['status']} — {p['id'][:8]}…"):
                st.write(p.get("body", "")[:500])
                if p["status"] in ("draft", "scheduled", "failed"):
                    if st.button("Publier maintenant", key=f"pub_{p['id']}"):
                        try:
                            job_info = store.enqueue_publish(p["id"])
                            job = ScraperJob(
                                job_type="content-publish",
                                payload={"post_id": p["id"], "job_id": job_info["job_id"]},
                            )
                            result = execute_content_job(job)
                            if result.get("success"):
                                st.success("Publié")
                            else:
                                st.error(result.get("error", "Échec"))
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))

    with tab_opt:
        rec = get_recommendations()
        st.json(rec)
