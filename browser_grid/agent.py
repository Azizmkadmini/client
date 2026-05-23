"""Agent HTTP minimal browser-grid (E1) — lancer: python -m browser_grid.agent"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="AIOS Browser Grid Agent", version="1.0.0")


class PublishBody(BaseModel):
    body: str
    tenant_id: str | None = None
    account_id: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "browser-grid"}


@app.post("/jobs/publish")
def publish_job(body: PublishBody) -> dict[str, Any]:
    from content.publishing.linkedin import publish_text_post

    return publish_text_post(body.body, tenant_id=body.tenant_id, account_id=body.account_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8090)
