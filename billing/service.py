"""Stripe checkout + crédits — mode mock si STRIPE_SECRET_KEY vide."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from config import settings
from storage.database import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BillingService:
    def __init__(self) -> None:
        self.db = Database()
        self.db.migrate()

    def ensure_credits(self, tenant_id: str, *, initial: int = 100) -> dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM tenant_credits WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO tenant_credits (tenant_id, balance, plan, updated_at)
                    VALUES (?, ?, 'starter', ?)
                    """,
                    (tenant_id, initial, _now()),
                )
                row = conn.execute(
                    "SELECT * FROM tenant_credits WHERE tenant_id = ?", (tenant_id,)
                ).fetchone()
        return dict(row) if row else {"tenant_id": tenant_id, "balance": initial, "plan": "starter"}

    def get_balance(self, tenant_id: str) -> int:
        return int(self.ensure_credits(tenant_id)["balance"])

    def consume(self, tenant_id: str, amount: int, *, reason: str = "") -> bool:
        bal = self.get_balance(tenant_id)
        if bal < amount:
            return False
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE tenant_credits SET balance = balance - ?, updated_at = ? WHERE tenant_id = ?",
                (amount, _now(), tenant_id),
            )
            conn.execute(
                """
                INSERT INTO billing_events (id, tenant_id, event_type, payload, created_at)
                VALUES (?, ?, 'credit_consume', ?, ?)
                """,
                (str(uuid.uuid4()), tenant_id, f'{{"amount": {amount}, "reason": "{reason}"}}', _now()),
            )
        return True

    def add_credits(self, tenant_id: str, amount: int, *, reason: str = "topup") -> int:
        self.ensure_credits(tenant_id)
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE tenant_credits SET balance = balance + ?, updated_at = ? WHERE tenant_id = ?",
                (amount, _now(), tenant_id),
            )
        return self.get_balance(tenant_id)

    def create_checkout_session(self, tenant_id: str, plan: str = "pro") -> dict[str, Any]:
        if not settings.stripe_secret_key:
            self.add_credits(tenant_id, 500, reason=f"mock_checkout_{plan}")
            return {
                "mode": "mock",
                "plan": plan,
                "message": "STRIPE_SECRET_KEY absent — 500 crédits ajoutés en mode démo",
                "balance": self.get_balance(tenant_id),
            }
        try:
            import stripe

            stripe.api_key = settings.stripe_secret_key
            price = settings.stripe_price_pro if plan == "pro" else settings.stripe_price_starter
            if not price:
                raise ValueError("Stripe price id non configuré")
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": price, "quantity": 1}],
                success_url="http://127.0.0.1:3000/billing?success=1",
                cancel_url="http://127.0.0.1:3000/billing?canceled=1",
                metadata={"tenant_id": tenant_id, "plan": plan},
            )
            return {"mode": "stripe", "checkout_url": session.url, "session_id": session.id}
        except Exception as exc:
            return {"mode": "error", "error": str(exc)}

    def handle_webhook(self, payload: bytes, sig_header: str) -> dict[str, Any]:
        if not settings.stripe_secret_key or not settings.stripe_webhook_secret:
            return {"status": "ignored", "reason": "stripe_not_configured"}
        try:
            import stripe

            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.stripe_webhook_secret
            )
            if event["type"] == "checkout.session.completed":
                meta = event["data"]["object"].get("metadata", {})
                tid = meta.get("tenant_id", settings.default_tenant_id)
                self.add_credits(tid, 1000, reason="stripe_checkout")
                with self.db.connect() as conn:
                    conn.execute(
                        "UPDATE tenant_credits SET plan = ?, updated_at = ? WHERE tenant_id = ?",
                        (meta.get("plan", "pro"), _now(), tid),
                    )
            return {"status": "ok", "type": event["type"]}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}


class ApiKeyService:
    def __init__(self) -> None:
        self.db = Database()
        self.db.migrate()

    def create_key(self, tenant_id: str, name: str) -> dict[str, Any]:
        raw = f"aios_{secrets.token_urlsafe(32)}"
        prefix = raw[:12]
        key_hash = hashlib.sha256(raw.encode()).hexdigest()
        kid = str(uuid.uuid4())
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO api_keys (id, tenant_id, name, key_hash, key_prefix, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (kid, tenant_id, name, key_hash, prefix, _now()),
            )
        return {"id": kid, "name": name, "api_key": raw, "prefix": prefix}

    def verify(self, raw_key: str) -> dict[str, Any] | None:
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT tenant_id, name FROM api_keys
                WHERE key_hash = ? AND revoked_at IS NULL
                """,
                (key_hash,),
            ).fetchone()
        return dict(row) if row else None

    def list_keys(self, tenant_id: str) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, tenant_id, name, key_prefix, created_at, last_used_at FROM api_keys WHERE tenant_id = ? AND revoked_at IS NULL",
                (tenant_id,),
            ).fetchall()
        return [dict(r) for r in rows]
