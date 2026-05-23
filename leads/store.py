from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from compliance.registry import ComplianceRegistry
from config import settings
from leads.models import Channel, FollowUpStage, Lead, LeadStatus, LeadTag
from storage.database import Database
from utils.file_lock import locked_path


REQUIRED_COLUMNS = {"name"}
OPTIONAL_COLUMNS = {"company", "link", "email", "phone", "tag", "channel", "notes"}


class LeadStore:
    def __init__(self, csv_path: Optional[Path] = None) -> None:
        self.csv_path = Path(csv_path or settings.path(settings.leads_csv))
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self.compliance = ComplianceRegistry()
        self.database = Database()
        self.database.migrate()
        if not self._use_postgres() and not self.csv_path.exists():
            self._write_empty()

    @staticmethod
    def _use_postgres() -> bool:
        from storage.postgres import postgres_configured

        return postgres_configured()

    def _write_empty(self) -> None:
        df = pd.DataFrame(
            columns=[
                "id",
                "name",
                "company",
                "link",
                "email",
                "phone",
                "tag",
                "status",
                "channel",
                "follow_up_stage",
                "last_contacted_at",
                "next_follow_up_at",
                "notes",
                "fingerprint",
                "created_at",
            ]
        )
        df.to_csv(self.csv_path, index=False)

    def _load(self) -> pd.DataFrame:
        if self._use_postgres():
            from storage.postgres_backend import fetch_all_leads_df

            df = fetch_all_leads_df()
        else:
            df = pd.read_csv(self.csv_path, dtype=str).fillna("")
        for col in [
            "id",
            "name",
            "company",
            "link",
            "email",
            "phone",
            "tag",
            "status",
            "channel",
            "follow_up_stage",
            "last_contacted_at",
            "next_follow_up_at",
            "notes",
            "fingerprint",
            "created_at",
        ]:
            if col not in df.columns:
                df[col] = ""
        return df

    def _save(self, df: pd.DataFrame) -> None:
        if self._use_postgres():
            from storage.postgres_backend import save_leads_df

            save_leads_df(df)
            if getattr(settings, "leads_csv_export", True):
                with locked_path(self.csv_path):
                    df.to_csv(self.csv_path, index=False)
            return
        with locked_path(self.csv_path):
            df.to_csv(self.csv_path, index=False)
        self._sync_sqlite(df)
        self._sync_postgres(df)

    def _sync_postgres(self, df: pd.DataFrame) -> None:
        try:
            from storage.postgres import postgres_configured
            from storage.postgres_backend import upsert_lead_row

            if not postgres_configured():
                return
            for _, row in df.iterrows():
                if not str(row.get("name", "")).strip():
                    continue
                channel = str(row.get("channel", ""))
                upsert_lead_row(
                    {
                        "id": row.get("id"),
                        "fingerprint": row.get("fingerprint"),
                        "name": row.get("name"),
                        "company": row.get("company"),
                        "email": row.get("email"),
                        "phone": row.get("phone"),
                        "link": row.get("link"),
                        "linkedin": row.get("link") if channel == Channel.LINKEDIN.value else "",
                        "instagram": row.get("link") if channel == Channel.INSTAGRAM.value else "",
                        "tag": row.get("tag"),
                        "status": row.get("status"),
                        "channel": channel,
                        "follow_up_stage": row.get("follow_up_stage"),
                        "last_contacted_at": row.get("last_contacted_at"),
                        "next_follow_up_at": row.get("next_follow_up_at"),
                        "notes": row.get("notes"),
                        "created_at": row.get("created_at"),
                    }
                )
        except Exception:
            pass

    def upsert_lead(self, lead: Lead) -> Lead:
        df = self._load()
        if lead.fingerprint and not df[df["fingerprint"] == lead.fingerprint].empty:
            return self._row_to_lead(df[df["fingerprint"] == lead.fingerprint].iloc[0])
        row = self._lead_to_row(lead)
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        self._save(df)
        return lead

    def find_by_fingerprint(self, fingerprint: str) -> Optional[Lead]:
        if not fingerprint:
            return None
        df = self._load()
        match = df[df["fingerprint"] == fingerprint]
        if match.empty:
            return None
        return self._row_to_lead(match.iloc[0])

    def _sync_sqlite(self, df: pd.DataFrame) -> None:
        if settings.storage_backend.lower() != "sqlite":
            return
        with self.database.connect() as connection:
            for _, row in df.iterrows():
                if not str(row.get("name", "")).strip():
                    continue
                connection.execute(
                    """
                    INSERT OR REPLACE INTO leads
                    (id, fingerprint, name, company, email, phone, link, linkedin, instagram,
                     tag, status, channel, follow_up_stage, last_contacted_at, next_follow_up_at,
                     notes, consent, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, datetime('now'))
                    """,
                    (
                        row.get("id", ""),
                        row.get("fingerprint", ""),
                        row.get("name", ""),
                        row.get("company", ""),
                        row.get("email", ""),
                        row.get("phone", ""),
                        row.get("link", ""),
                        row.get("link", "") if row.get("channel") == Channel.LINKEDIN.value else "",
                        row.get("link", "") if row.get("channel") == Channel.INSTAGRAM.value else "",
                        row.get("tag", LeadTag.COLD.value),
                        row.get("status", LeadStatus.NEW.value),
                        row.get("channel", Channel.LINKEDIN.value),
                        int(row.get("follow_up_stage") or FollowUpStage.INTRO.value),
                        row.get("last_contacted_at", ""),
                        row.get("next_follow_up_at", ""),
                        row.get("notes", ""),
                        row.get("created_at", datetime.utcnow().isoformat()),
                    ),
                )

    def import_csv(self, source: Path, merge: bool = True) -> int:
        incoming = pd.read_csv(source, dtype=str).fillna("")
        missing = REQUIRED_COLUMNS - set(incoming.columns)
        if missing:
            raise ValueError(f"CSV missing required columns: {sorted(missing)}")

        rows: list[dict] = []
        for _, row in incoming.iterrows():
            tag = (row.get("tag") or LeadTag.COLD.value).lower()
            if tag not in {t.value for t in LeadTag}:
                tag = LeadTag.COLD.value
            channel = (row.get("channel") or Channel.LINKEDIN.value).lower()
            if channel not in {c.value for c in Channel}:
                channel = Channel.LINKEDIN.value
            rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "name": row["name"].strip(),
                    "company": str(row.get("company", "")).strip(),
                    "link": str(row.get("link", "")).strip(),
                    "email": str(row.get("email", "")).strip(),
                    "phone": str(row.get("phone", "")).strip(),
                    "tag": tag,
                    "status": LeadStatus.NEW.value,
                    "channel": channel,
                    "follow_up_stage": str(FollowUpStage.INTRO.value),
                    "last_contacted_at": "",
                    "next_follow_up_at": "",
                    "notes": str(row.get("notes", "")).strip(),
                    "fingerprint": str(row.get("fingerprint", "")).strip(),
                    "created_at": datetime.utcnow().isoformat(),
                }
            )

        if not rows:
            return 0

        if merge and self.csv_path.exists() and self.csv_path.stat().st_size > 0:
            existing = self._load()
            if not existing.empty and existing["name"].str.strip().any():
                combined = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True)
            else:
                combined = pd.DataFrame(rows)
        else:
            combined = pd.DataFrame(rows)

        self._save(combined)
        return len(rows)

    def all(self) -> list[Lead]:
        return [self._row_to_lead(row) for _, row in self._load().iterrows() if row.get("name")]

    def list_page(self, *, offset: int = 0, limit: int = 100) -> tuple[list[Lead], int]:
        if self._use_postgres():
            from storage.postgres_backend import fetch_leads_page

            df, total = fetch_leads_page(offset=offset, limit=limit)
            items = [self._row_to_lead(row) for _, row in df.iterrows() if row.get("name")]
            return items, total
        df = self._load()
        total = len(df)
        slice_df = df.iloc[offset : offset + limit]
        items = [self._row_to_lead(row) for _, row in slice_df.iterrows() if row.get("name")]
        return items, total

    def get(self, lead_id: str) -> Optional[Lead]:
        df = self._load()
        match = df[df["id"] == lead_id]
        if match.empty:
            return None
        return self._row_to_lead(match.iloc[0])

    def update(self, lead: Lead) -> None:
        df = self._load()
        idx = df.index[df["id"] == lead.id]
        if len(idx) == 0:
            return
        df.loc[idx[0]] = self._lead_to_row(lead)
        self._save(df)

    def due_for_follow_up(self, channel: Optional[Channel] = None) -> list[Lead]:
        now = datetime.utcnow()
        leads = []
        for lead in self.all():
            if channel and lead.channel != channel:
                continue
            if lead.status in {LeadStatus.REPLIED, LeadStatus.COMPLETED, LeadStatus.FAILED}:
                continue
            if self._is_opted_out(lead):
                continue
            if lead.follow_up_stage == FollowUpStage.FINAL and lead.last_contacted_at:
                continue
            if lead.status in {LeadStatus.NEW, LeadStatus.QUEUED}:
                leads.append(lead)
                continue
            if lead.next_follow_up_at and lead.next_follow_up_at <= now:
                leads.append(lead)
        return leads

    def mark_contacted(self, lead: Lead, stage: FollowUpStage) -> Lead:
        lead.last_contacted_at = datetime.utcnow()
        lead.follow_up_stage = stage
        lead.status = LeadStatus.CONTACTED
        if stage == FollowUpStage.INTRO:
            lead.next_follow_up_at = lead.last_contacted_at + timedelta(days=2)
        elif stage == FollowUpStage.FOLLOW_UP:
            lead.next_follow_up_at = lead.last_contacted_at + timedelta(days=2)
        else:
            lead.next_follow_up_at = None
            lead.status = LeadStatus.COMPLETED
        self.update(lead)
        return lead

    def mark_replied(self, lead_id: str) -> None:
        lead = self.get(lead_id)
        if not lead:
            return
        lead.status = LeadStatus.REPLIED
        lead.next_follow_up_at = None
        self.update(lead)

    def mark_failed(self, lead_id: str, note: str = "") -> None:
        lead = self.get(lead_id)
        if not lead:
            return
        lead.status = LeadStatus.FAILED
        if note:
            lead.notes = f"{lead.notes}\n{note}".strip()
        self.update(lead)

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for lead in self.all():
            counts[lead.status.value] = counts.get(lead.status.value, 0) + 1
        return counts

    def _row_to_lead(self, row: pd.Series) -> Lead:
        def parse_dt(value: str) -> Optional[datetime]:
            if not value:
                return None
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None

        tag = (row.get("tag") or LeadTag.COLD.value).lower()
        try:
            tag_enum = LeadTag(tag)
        except ValueError:
            tag_enum = LeadTag.COLD

        status = (row.get("status") or LeadStatus.NEW.value).lower()
        try:
            status_enum = LeadStatus(status)
        except ValueError:
            status_enum = LeadStatus.NEW

        channel = (row.get("channel") or Channel.LINKEDIN.value).lower()
        try:
            channel_enum = Channel(channel)
        except ValueError:
            channel_enum = Channel.LINKEDIN

        stage_raw = row.get("follow_up_stage") or str(FollowUpStage.INTRO.value)
        try:
            stage = FollowUpStage(int(stage_raw))
        except (ValueError, TypeError):
            stage = FollowUpStage.INTRO

        return Lead(
            id=row.get("id") or str(uuid.uuid4()),
            name=row["name"],
            company=row.get("company", ""),
            link=row.get("link", ""),
            email=row.get("email", ""),
            phone=row.get("phone", ""),
            tag=tag_enum,
            status=status_enum,
            channel=channel_enum,
            follow_up_stage=stage,
            last_contacted_at=parse_dt(row.get("last_contacted_at", "")),
            next_follow_up_at=parse_dt(row.get("next_follow_up_at", "")),
            notes=row.get("notes", ""),
            fingerprint=row.get("fingerprint", ""),
            created_at=parse_dt(row.get("created_at", "")) or datetime.utcnow(),
        )

    def _is_opted_out(self, lead: Lead) -> bool:
        for identifier in (lead.email, lead.link, lead.name):
            if identifier and self.compliance.is_opted_out(identifier):
                return True
        return False

    def _lead_to_row(self, lead: Lead) -> dict:
        return {
            "id": lead.id,
            "name": lead.name,
            "company": lead.company,
            "link": lead.link,
            "email": lead.email,
            "phone": lead.phone,
            "tag": lead.tag.value,
            "status": lead.status.value,
            "channel": lead.channel.value,
            "follow_up_stage": str(lead.follow_up_stage.value),
            "last_contacted_at": lead.last_contacted_at.isoformat() if lead.last_contacted_at else "",
            "next_follow_up_at": lead.next_follow_up_at.isoformat() if lead.next_follow_up_at else "",
            "notes": lead.notes,
            "fingerprint": lead.fingerprint,
            "created_at": lead.created_at.isoformat(),
        }


def next_stage(lead: Lead) -> FollowUpStage:
    if lead.status == LeadStatus.NEW or lead.follow_up_stage == FollowUpStage.INTRO:
        if lead.last_contacted_at is None:
            return FollowUpStage.INTRO
        return FollowUpStage.FOLLOW_UP
    if lead.follow_up_stage == FollowUpStage.FOLLOW_UP:
        return FollowUpStage.FINAL
    return FollowUpStage.FINAL
