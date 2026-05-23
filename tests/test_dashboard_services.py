from __future__ import annotations

from pathlib import Path

import pytest

from config import settings


@pytest.fixture()
def temp_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "project_root", tmp_path)
    (tmp_path / "leads").mkdir()
    monkeypatch.setattr(settings, "scraper_output_csv", "leads/scraper_output.csv")
    monkeypatch.setattr(settings, "scraper_instagram_output_csv", "leads/scraper_instagram.csv")
    return tmp_path


def test_load_scraper_frame_separates_linkedin_and_instagram(
    temp_project: Path,
) -> None:
    from dashboard.services import load_scraper_frame

    cols = (
        "nom,email,whatsapp,whatsapp_link,whatsapp_verif,pays,entreprise,poste,"
        "domaine,site_web,about,app,link\n"
    )
    (temp_project / "leads" / "scraper_output.csv").write_text(
        cols + "Lin,a@b.co,vide,vide,vide,vide,Co,vide,vide,vide,vide,linkedin,https://www.linkedin.com/in/lin\n",
        encoding="utf-8",
    )
    (temp_project / "leads" / "scraper_instagram.csv").write_text(
        cols + "Ig,ig@b.co,vide,vide,vide,vide,vide,vide,vide,vide,vide,instagram,https://www.instagram.com/ig/\n",
        encoding="utf-8",
    )

    li = load_scraper_frame("linkedin")
    ig = load_scraper_frame("instagram")

    assert len(li) == 1
    assert li.iloc[0]["app"] == "linkedin"
    assert len(ig) == 1
    assert ig.iloc[0]["app"] == "instagram"
    assert "instagram.com" not in str(li.iloc[0]["link"])
