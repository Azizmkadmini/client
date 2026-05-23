"""Jobs Redis — module Content OS."""

from __future__ import annotations

from typing import Any

from content.analytics.sync import sync_all_published, sync_post_metrics
from content.generation.service import generate_cta, generate_hooks, generate_post
from content.models import GenerateHookRequest, GeneratePostRequest
from content.publishing.linkedin import publish_text_post
from content.store import ContentStore
from workers.queue import ScraperJob


def execute_content_job(job: ScraperJob) -> dict[str, Any]:
    payload = job.payload or {}
    store = ContentStore()

    if job.job_type == "content-generate-hooks":
        req = GenerateHookRequest(**payload)
        hooks = generate_hooks(req)
        return {"hooks": [h.model_dump() for h in hooks]}

    if job.job_type == "content-generate-post":
        req = GeneratePostRequest(**payload)
        draft = generate_post(req)
        saved = store.create_draft(
            body=draft.body,
            hook=draft.hook,
            cta=draft.cta,
            format=draft.format.value if hasattr(draft.format, "value") else str(draft.format),
        )
        return {"draft": saved, "generated": draft.model_dump(mode="json")}

    if job.job_type == "content-generate-cta":
        return {"cta": generate_cta(str(payload.get("topic", "")), language=payload.get("language", "fr"))}

    if job.job_type == "content-publish":
        post_id = str(payload.get("post_id", ""))
        if not post_id:
            raise ValueError("post_id requis")
        job_id = payload.get("job_id")
        if not job_id:
            try:
                job_row = store.enqueue_publish(post_id)
                job_id = job_row["job_id"]
            except RuntimeError:
                raise
        post = store.get_post(post_id)
        full_text = post["body"]
        if post.get("hook"):
            full_text = f"{post['hook']}\n\n{full_text}"
        if post.get("cta"):
            full_text = f"{full_text}\n\n{post['cta']}"
        from browser_grid.executor import execute_publish

        result = execute_publish(
            full_text,
            tenant_id=str(post.get("tenant_id") or ""),
        )
        store.complete_publish_job(
            str(job_id),
            success=bool(result.get("success")),
            linkedin_url=result.get("url"),
            error=result.get("error"),
            result=result,
        )
        if result.get("success"):
            from services.outbox import emit_event

            emit_event(
                "content.published",
                {"post_id": post_id, "url": result.get("url")},
                tenant_id=str(post.get("tenant_id") or ""),
            )
        return result

    if job.job_type == "content-sync-metrics":
        if payload.get("post_id"):
            return sync_post_metrics(str(payload["post_id"]))
        return {"synced": sync_all_published(limit=int(payload.get("limit", 50)))}

    if job.job_type == "content-scheduler-tick":
        due = store.list_due_scheduled_posts()
        results = []
        for post in due[: int(payload.get("max", 3))]:
            sub = ScraperJob(job_type="content-publish", payload={"post_id": post["id"]})
            results.append(execute_content_job(sub))
        return {"processed": len(results), "results": results}

    raise ValueError(f"Job content inconnu: {job.job_type}")
