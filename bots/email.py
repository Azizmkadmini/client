from __future__ import annotations

import smtplib
import uuid
from email.message import EmailMessage
from email.utils import formataddr

from config import settings
from leads.models import Channel, Lead
from leads.store import LeadStore, next_stage
from logs.logger import OutreachLogger
from ai.generator import MessageGenerator
from utils.behavior import HumanBehavior, RateLimiter
from utils.retry import retry_call

# Mots déclencheurs de filtres spam — retirés du contenu généré par l'IA
_SPAM_WORDS = [
    "free", "gratuit", "urgent", "limited time", "act now", "click here",
    "buy now", "order now", "100%", "guaranteed", "no obligation",
    "risk-free", "winner", "congratulations", "félicitations",
    "offre exceptionnelle", "promotion", "réduction", "soldes",
    "money back", "earn money", "make money", "million",
    "investment", "profit", "revenue", "income", "cash",
    "unsubscribe", "opt-out", "dear friend", "cher ami",
]


class EmailBot:
    channel = "email"

    def __init__(
        self,
        store: LeadStore,
        generator: MessageGenerator,
        logger: OutreachLogger,
    ) -> None:
        self.store = store
        self.generator = generator
        self.logger = logger
        self.behavior = HumanBehavior()
        self.rate_limiter = RateLimiter(self.channel, settings.email_daily_max)

    def run_batch(self, limit: int | None = None, allow_weekend: bool = False) -> int:
        import datetime as _dt
        if not allow_weekend and _dt.datetime.now().weekday() >= 5:
            return 0  # Samedi=5, Dimanche=6 — pas d'envoi le weekend

        sent = 0
        leads = self.store.due_for_follow_up(channel=Channel.EMAIL)
        if limit is not None:
            leads = leads[:limit]

        for lead in leads:
            if not self.rate_limiter.can_send():
                break
            if not lead.email:
                self.logger.log_failed(lead.id, self.channel, "Missing email address")
                self.store.mark_failed(lead.id, "Missing email address")
                continue
            stage = next_stage(lead)
            try:
                profile_context = (lead.notes or "").strip()
                subject, message = self.generator.generate(
                    lead,
                    stage,
                    self.channel,
                    extra_context=profile_context,
                )
                if not self.generator.ensure_not_duplicate(message):
                    subject, message = self.generator.generate(
                        lead,
                        stage,
                        self.channel,
                        extra_context=(
                            f"{profile_context} | Use different wording from prior outreach."
                            if profile_context
                            else "Use different wording from prior outreach."
                        ),
                    )
                self.behavior.random_delay()
                self._send_email(lead, subject, message)
                self.rate_limiter.record_send()
                self.store.mark_contacted(lead, stage)
                self.logger.log_sent(
                    lead.id,
                    self.channel,
                    stage.value,
                    message,
                    subject=subject,
                )
                sent += 1
                self.behavior.maybe_long_pause()
            except Exception as exc:  # noqa: BLE001
                self.store.mark_failed(lead.id, str(exc))
                self.logger.log_failed(lead.id, self.channel, str(exc))
        return sent

    def _clean_for_spam(self, text: str) -> str:
        """Retire les mots déclencheurs de filtres spam du texte généré."""
        import re
        result = text
        for word in _SPAM_WORDS:
            result = re.sub(re.escape(word), "", result, flags=re.IGNORECASE)
        # Nettoie les espaces doubles laissés par les suppressions
        result = re.sub(r"  +", " ", result).strip()
        return result

    def _send_email(self, lead: Lead, subject: str, body: str) -> None:
        if not settings.smtp_user or not settings.smtp_password:
            raise RuntimeError("SMTP credentials are not configured")

        sender_name = getattr(settings, "sender_name", "").strip() or "Mohamed Aziz Mkadmini"
        smtp_from   = settings.smtp_from or settings.smtp_user

        # Nettoie le contenu IA des mots spam avant envoi
        subject = self._clean_for_spam(subject)
        body    = self._clean_for_spam(body)

        # Ajoute ligne de désinscription RGPD (texte neutre, pas de lien)
        unsubscribe_line = (
            "\n\n---\nSi vous ne souhaitez plus recevoir de messages, répondez simplement \"stop\"."
            if any(c in (lead.notes or "") for c in ["France", "Maroc", "Belgique", "Tunisie", "france", "maroc"])
            else "\n\n---\nTo stop receiving messages, simply reply \"stop\"."
        )
        body_final = body + unsubscribe_line

        def action() -> None:
            msg = EmailMessage()
            msg["Subject"]    = subject
            # Format "Prénom Nom <email>" — améliore la délivrabilité et évite le filtre spam
            msg["From"]       = formataddr((sender_name, smtp_from))
            msg["To"]         = lead.email
            msg["Reply-To"]   = smtp_from
            # Message-ID unique par email — évite la détection de contenu dupliqué
            msg["Message-ID"] = f"<{uuid.uuid4().hex}@{smtp_from.split('@')[-1]}>"
            msg.set_content(body_final)
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)

        retry_call(action)
