from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import AuthContext
from content.accounts import LinkedInAccountStore

router = APIRouter(prefix="/accounts", tags=["accounts"])


class AccountCreate(BaseModel):
    label: str
    profile_url: str = ""
    scrape: bool = False
    outreach: bool = False
    publish: bool = True


@router.get("/linkedin")
def list_linkedin_accounts(ctx: AuthContext) -> dict:
    store = LinkedInAccountStore()
    return {"accounts": store.list_accounts(ctx["tenant_id"])}


@router.post("/linkedin")
def create_linkedin_account(body: AccountCreate, ctx: AuthContext) -> dict:
    store = LinkedInAccountStore()
    acc = store.create(
        body.label,
        tenant_id=ctx["tenant_id"],
        scrape=body.scrape,
        outreach=body.outreach,
        publish=body.publish,
        profile_url=body.profile_url,
    )
    return {"account": acc}
