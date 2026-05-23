"""Billing + crédits + API keys (Phase 5)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request

from api.deps import AuthContext
from billing.service import ApiKeyService, BillingService

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/credits")
def get_credits(ctx: AuthContext) -> dict[str, Any]:
    svc = BillingService()
    return svc.ensure_credits(ctx["tenant_id"])


@router.post("/checkout")
def checkout(ctx: AuthContext, plan: str = "pro") -> dict[str, Any]:
    return BillingService().create_checkout_session(ctx["tenant_id"], plan=plan)


@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, Any]:
    body = await request.body()
    return BillingService().handle_webhook(body, stripe_signature or "")


@router.get("/api-keys")
def list_api_keys(ctx: AuthContext) -> list[dict[str, Any]]:
    return ApiKeyService().list_keys(ctx["tenant_id"])


@router.post("/api-keys")
def create_api_key(ctx: AuthContext, name: str = "default") -> dict[str, Any]:
    return ApiKeyService().create_key(ctx["tenant_id"], name)
