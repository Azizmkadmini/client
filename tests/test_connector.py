from __future__ import annotations

import json
from pathlib import Path

import pytest

from config import settings
from connector.cleaner import LeadCleaner, LeadEnricher, _notes_from_scraper_metadata
from connector.ingest import QueueIngestor
from connector.models import BotLead, RawLead
from leads.models import Channel
from leads.store import LeadStore


@pytest.fixture()
def temp_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "project_root", tmp_path)
    (tmp_path / "leads").mkdir()
    (tmp_path / "bot").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "compliance").mkdir()
    monkeypatch.setattr(settings, "leads_csv", "leads/leads.csv")
    monkeypatch.setattr(settings, "scraper_output_csv", "leads/scraper_output.csv")
    monkeypatch.setattr(settings, "connector_source_csv", "leads/scraper_output.csv")
    monkeypatch.setattr(settings, "connector_queue_path", "bot/leads_queue.json")
    monkeypatch.setattr(settings, "connector_sqlite_path", "data/connector.db")
    monkeypatch.setattr(settings, "app_db_path", "data/app.db")
    monkeypatch.setattr(settings, "opt_out_csv", "compliance/opt_out.csv")
    monkeypatch.setattr(settings, "connector_processed_log", "logs/connector_processed_leads.jsonl")
    monkeypatch.setattr(settings, "connector_failed_log", "logs/connector_failed_leads.jsonl")
    monkeypatch.setattr(settings, "log_dir", "logs")
    monkeypatch.setattr(settings, "storage_backend", "sqlite")
    return tmp_path


def test_cleaner_deduplicates_and_rejects_invalid_email(temp_project: Path) -> None:
    leads = [
        RawLead(name="Alex", email="alex@example.com", company="A"),
        RawLead(name="Alex", email="alex@example.com", company="A"),
        RawLead(name="Bad", email="not-an-email", company="B"),
    ]
    result = LeadCleaner().clean(leads)
    assert len(result.accepted) == 1
    assert len(result.rejected) == 2


def test_ingest_prefers_email_channel_when_address_present() -> None:
    ingestor = QueueIngestor()
    channel, link, phone = ingestor._resolve_channel(
        BotLead(
            name="Alex",
            email="alex@example.com",
            linkedin="https://www.linkedin.com/in/alex",
            company="Acme",
        )
    )
    assert channel == Channel.EMAIL
    assert link == "alex@example.com"
    assert phone == ""


def test_notes_from_scraper_metadata() -> None:
    notes = _notes_from_scraper_metadata(
        {"poste": "CEO", "about": "SaaS founder", "pays": "vide", "email": "x@y.com"}
    )
    assert "CEO" in notes
    assert "SaaS" in notes
    assert "email:" not in notes.lower() or "email" not in notes


def test_enricher_assigns_tags(temp_project: Path) -> None:
    leads = [
        RawLead(name="Hot", email="a@b.com", linkedin="https://linkedin.com/in/a", company="Co"),
    ]
    enriched = LeadEnricher().enrich(leads)
    assert enriched[0].tag.value in {"hot", "warm", "cold"}


def test_ingest_moves_queue_items_into_lead_store(temp_project: Path) -> None:
    queue_path = temp_project / "bot" / "leads_queue.json"
    queue_path.write_text(
        json.dumps(
            [
                {
                    "fingerprint": "abc123",
                    "lead": {
                        "name": "Taylor",
                        "company": "Harbor",
                        "email": "taylor@example.com",
                        "linkedin": "",
                        "instagram": "",
                        "tag": "cold",
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    result = QueueIngestor().ingest()
    assert result.ingested == 1
    store = LeadStore()
    assert any(lead.email == "taylor@example.com" for lead in store.all())


def test_lead_loader_merges_instagram_csv_when_configured(
    temp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from connector.loader import LeadLoader

    monkeypatch.setattr(settings, "scraper_instagram_output_csv", "leads/scraper_instagram.csv")
    main = temp_project / "leads" / "scraper_output.csv"
    ig = temp_project / "leads" / "scraper_instagram.csv"
    cols = (
        "nom,email,whatsapp,whatsapp_link,whatsapp_verif,pays,entreprise,poste,"
        "domaine,site_web,about,app,link\n"
    )
    main.write_text(
        cols + "Lin,vide,vide,vide,vide,vide,Co,vide,vide,vide,vide,linkedin,https://www.linkedin.com/in/lin\n",
        encoding="utf-8",
    )
    ig.write_text(
        cols + "Ig,vide,vide,vide,vide,vide,vide,vide,vide,vide,vide,instagram,https://www.instagram.com/ig/\n",
        encoding="utf-8",
    )
    leads = LeadLoader().load_csv()
    assert len(leads) == 2
    links = {str(lead.metadata.get("link", "")) for lead in leads}
    assert "https://www.linkedin.com/in/lin" in links
    assert "https://www.instagram.com/ig/" in links
