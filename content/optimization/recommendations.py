"""Recommandations IA — horaires, formats, templates."""

from __future__ import annotations

from typing import Any

from content.store import ContentStore


def get_recommendations() -> dict[str, Any]:
    store = ContentStore()
    tenant_id = store.ensure_default_tenant()
    with store.db.connect() as conn:
        rows = conn.execute(
            """
            SELECT template_key, format, hour_bucket, engagement_ema, sample_count
            FROM content_template_scores
            WHERE tenant_id = ?
            ORDER BY engagement_ema DESC
            LIMIT 20
            """,
            (tenant_id,),
        ).fetchall()
    scores = [dict(r) for r in rows]
    best_hour = 9
    best_format = "expertise"
    if scores:
        top = scores[0]
        best_hour = int(top.get("hour_bucket") or 9)
        best_format = top.get("format") or top.get("template_key") or "expertise"
    return {
        "best_hour_utc": best_hour,
        "best_format": best_format,
        "template_scores": scores,
        "tips": [
            f"Publier vers {best_hour}h UTC (ajuster fuseau local)",
            f"Format le plus performant : {best_format}",
            "Tester 2 hooks A/B par semaine",
            "Relancer sync métriques après 48h",
        ],
    }


def predict_engagement(format: str, hour_bucket: int) -> float:
    store = ContentStore()
    tenant_id = store.ensure_default_tenant()
    with store.db.connect() as conn:
        row = conn.execute(
            """
            SELECT engagement_ema FROM content_template_scores
            WHERE tenant_id = ? AND (format = ? OR template_key = ?) AND hour_bucket = ?
            """,
            (tenant_id, format, format, hour_bucket),
        ).fetchone()
    if row:
        return float(row["engagement_ema"])
    return 2.5
