from pathlib import Path

import pytest

from config import settings
from scraper.cli import run_search
from scraper.contact_recovery import (
    guess_emails_from_name_and_domain,
    merge_contact_layers,
    split_display_name_for_guess,
)
from scraper.extractors import (
    normalize_email,
    normalize_whatsapp_number,
    parse_email,
    parse_linkedin_card,
    parse_linkedin_company_card,
    parse_website,
    parse_whatsapp,
    parse_whatsapp_from_links,
    website_from_href,
)
from scraper.linkedin_contacts import extract_company_from_sources, extract_contacts_from_sources
from scraper.models import EMPTY_VALUE, ScraperRecord
from scraper.linkedin_search import (
    LINKEDIN_SCOPE_PATHS,
    build_linkedin_search_url,
    resolve_linkedin_scopes,
)
from scraper.site_contact_fetch import discover_same_site_links, extract_email_phone_from_html
from scraper.writer import ScraperWriter


@pytest.fixture()
def temp_scraper_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "scraper_output_csv", "leads/scraper_output.csv")
    (tmp_path / "leads").mkdir()
    return tmp_path / "leads" / "scraper_output.csv"


def test_writer_uses_vide_for_empty_fields(temp_scraper_output: Path) -> None:
    writer = ScraperWriter(temp_scraper_output)
    writer.write([ScraperRecord(nom="Alex", app="linkedin")], append=False)
    content = temp_scraper_output.read_text(encoding="utf-8")
    assert "vide" in content
    assert "Alex" in content
    assert "whatsapp_link" in content
    assert "whatsapp_verif" in content


def test_whatsapp_wa_me_url_from_digits() -> None:
    from scraper.extractors import whatsapp_wa_me_url

    assert whatsapp_wa_me_url("+33612345678") == "https://api.whatsapp.com/send?phone=33612345678"


def test_scraper_record_to_row_includes_whatsapp_link() -> None:
    row = ScraperRecord(whatsapp="33612345678").to_row()
    assert row["whatsapp_link"] == "https://api.whatsapp.com/send?phone=33612345678"
    assert row.get("whatsapp_verif") == EMPTY_VALUE


def test_scraper_record_whatsapp_webhook_hides_link_when_not_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"on_whatsapp": False}
    mock_client = MagicMock()
    mock_client.post.return_value = mock_response
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_client
    mock_cm.__exit__.return_value = None
    monkeypatch.setattr("utils.whatsapp_verify.httpx.Client", lambda **kwargs: mock_cm)
    monkeypatch.setattr(settings, "whatsapp_verify_mode", "webhook")
    monkeypatch.setattr(settings, "whatsapp_verify_webhook_url", "https://example.invalid/whatsapp-check")
    row = ScraperRecord(whatsapp="33612345678").to_row()
    assert row["whatsapp_link"] == EMPTY_VALUE
    assert row["whatsapp_verif"] == "non"


def test_scraper_record_whatsapp_webhook_keeps_link_when_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 502
    mock_client = MagicMock()
    mock_client.post.return_value = mock_response
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_client
    mock_cm.__exit__.return_value = None
    monkeypatch.setattr("utils.whatsapp_verify.httpx.Client", lambda **kwargs: mock_cm)
    monkeypatch.setattr(settings, "whatsapp_verify_mode", "webhook")
    monkeypatch.setattr(settings, "whatsapp_verify_webhook_url", "https://example.invalid/whatsapp-check")
    monkeypatch.setattr(settings, "whatsapp_verify_unknown_keep_link", True)
    row = ScraperRecord(whatsapp="33612345678").to_row()
    assert row["whatsapp_link"] == "https://api.whatsapp.com/send?phone=33612345678"
    assert row["whatsapp_verif"] == "inconnu"


def test_scraper_record_whatsapp_webhook_shows_link_when_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"registered": True}
    mock_client = MagicMock()
    mock_client.post.return_value = mock_response
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_client
    mock_cm.__exit__.return_value = None
    monkeypatch.setattr("utils.whatsapp_verify.httpx.Client", lambda **kwargs: mock_cm)
    monkeypatch.setattr(settings, "whatsapp_verify_mode", "webhook")
    monkeypatch.setattr(settings, "whatsapp_verify_webhook_url", "https://example.invalid/whatsapp-check")
    row = ScraperRecord(whatsapp="33612345678").to_row()
    assert row["whatsapp_link"] == "https://api.whatsapp.com/send?phone=33612345678"
    assert row["whatsapp_verif"] == "oui"


def test_scraper_record_whatsapp_gratuit_rejects_landline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "whatsapp_verify_mode", "gratuit")
    row = ScraperRecord(whatsapp="+33142278100").to_row()
    assert row["whatsapp_link"] == EMPTY_VALUE
    assert row["whatsapp_verif"] == "non"


def test_scraper_record_whatsapp_gratuit_keeps_mobile_as_inconnu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "whatsapp_verify_mode", "gratuit")
    monkeypatch.setattr(settings, "whatsapp_verify_unknown_keep_link", True)
    row = ScraperRecord(whatsapp="+33612345678").to_row()
    assert row["whatsapp_link"] == "https://api.whatsapp.com/send?phone=33612345678"
    assert row["whatsapp_verif"] == "inconnu"


def test_scraper_record_whatsapp_free_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "whatsapp_verify_mode", "free")
    row = ScraperRecord(whatsapp="+18005551212").to_row()
    assert row["whatsapp_link"] == EMPTY_VALUE
    assert row["whatsapp_verif"] == "non"


def test_scraper_fast_mode_reduces_site_crawl_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    from scraper.timing import site_crawl_max_pages_effective, site_crawl_total_seconds_effective

    monkeypatch.setattr(settings, "scraper_stable_linkedin_mode", False)
    monkeypatch.setattr(settings, "scraper_site_crawl_max_pages", 55)
    monkeypatch.setattr(settings, "scraper_site_crawl_total_seconds", 150.0)
    monkeypatch.setattr(settings, "scraper_fast_mode", True)
    assert site_crawl_max_pages_effective() <= 31
    assert site_crawl_total_seconds_effective() <= 75.0


def test_linkedin_max_profiles_to_try_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from scraper.collectors import _linkedin_collect_scope_batch_size, _linkedin_max_profiles_to_try

    monkeypatch.setattr(settings, "scraper_stable_linkedin_mode", False)
    monkeypatch.setattr(settings, "scraper_linkedin_max_profiles_to_try", 0)
    monkeypatch.setattr(settings, "scraper_fast_mode", True)
    assert _linkedin_max_profiles_to_try(1) >= 50
    assert _linkedin_collect_scope_batch_size(1) >= 10
    monkeypatch.setattr(settings, "scraper_linkedin_max_profiles_to_try", 120)
    assert _linkedin_max_profiles_to_try(5) == 120


def test_linkedin_max_profiles_stable_mode_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from scraper.collectors import _linkedin_max_profiles_to_try

    monkeypatch.setattr(settings, "scraper_stable_linkedin_mode", True)
    monkeypatch.setattr(settings, "scraper_linkedin_stable_max_profiles_per_search", 25)
    monkeypatch.setattr(settings, "scraper_linkedin_max_profiles_to_try", 0)
    assert _linkedin_max_profiles_to_try(10) == 25
    assert _linkedin_max_profiles_to_try(100) == 25


def test_mx_domain_rejects_slogan_and_ipv4_without_dns_crash() -> None:
    from scraper.contact_recovery import guess_emails_from_name_and_domain, mx_domain_has_records

    assert mx_domain_has_records("1 événement, 1 agence") is False
    assert mx_domain_has_records("192.168.1.1") is False
    assert mx_domain_has_records("tagline événement, slug.invalid") is False
    assert guess_emails_from_name_and_domain("Jane", "Doe", "1 événement, 1 agence") == []


def test_fast_mode_disables_site_bfs_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from scraper.timing import site_crawl_bfs_enabled

    monkeypatch.setattr(settings, "scraper_stable_linkedin_mode", False)
    monkeypatch.setattr(settings, "scraper_fast_mode", True)
    monkeypatch.setattr(settings, "scraper_site_crawl_bfs_in_fast_mode", False)
    assert site_crawl_bfs_enabled() is False
    monkeypatch.setattr(settings, "scraper_site_crawl_bfs_in_fast_mode", True)
    assert site_crawl_bfs_enabled() is True


def test_website_from_linkedin_redir_path() -> None:
    redirected = (
        "https://www.linkedin.com/redir/redirect?url=https%3A%2F%2Fwww.acme-corp.io%2F"
    )
    assert website_from_href(redirected) == "https://www.acme-corp.io"


def test_extract_contacts_consulter_site_web_label() -> None:
    contacts = extract_contacts_from_sources(
        text="Site web\nConsulter le site web\n",
        hrefs=[
            "https://www.linkedin.com/redir/redirect?url=https%3A%2F%2Fstudio-demo.fr",
        ],
    )
    assert "studio-demo.fr" in contacts["site_web"].lower()


def test_linkedin_three_dots_menu_respects_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    from scraper.linkedin_contacts import _linkedin_three_dots_menu_enabled

    monkeypatch.setattr(settings, "scraper_linkedin_use_three_dots_menu", True)
    assert _linkedin_three_dots_menu_enabled() is True
    monkeypatch.setattr(settings, "scraper_linkedin_use_three_dots_menu", False)
    assert _linkedin_three_dots_menu_enabled() is False


def test_website_triple_probe_builds_three_steps() -> None:
    from scraper.site_contact_fetch import _triple_probe_url_candidates

    steps = _triple_probe_url_candidates("https://example-agency.fr")
    labels = [label for label, _ in steps]
    assert labels[0] == "accueil"
    assert "contact" in labels
    assert "mentions / à propos" in labels
    assert any("contact" in url for _, url in steps)
    assert any("mentions-legales" in url or "about" in url for _, url in steps)


def test_extract_linkedin_scope_records_skips_links() -> None:
    from scraper.linkedin_search import extract_linkedin_scope_records

    class _Anchor:
        def __init__(self, href: str, text: str) -> None:
            self._href = href
            self._text = text

        def get_attribute(self, name: str) -> str:
            return self._href if name == "href" else ""

        def inner_text(self) -> str:
            return self._text

        def locator(self, _xpath: str):
            return self

        @property
        def count(self) -> int:
            return 0

    class _Locator:
        def __init__(self, anchors: list[_Anchor]) -> None:
            self._anchors = anchors

        def all(self):
            return self._anchors

        def first(self):
            return self._anchors[0] if self._anchors else _Anchor("", "")

        def count(self) -> int:
            return len(self._anchors)

    class _Page:
        def locator(self, selector: str) -> _Locator:
            if "search-result-lockup" in selector:
                return _Locator([])
            if "/in/" in selector:
                return _Locator(
                    [
                        _Anchor("/in/alice", "Alice\nCEO"),
                        _Anchor("/in/bob", "Bob\nCTO"),
                    ]
                )
            return _Locator([])

    page = _Page()
    all_records = extract_linkedin_scope_records(page, "people", 5)
    assert len(all_records) == 2
    filtered = extract_linkedin_scope_records(
        page,
        "people",
        5,
        skip_links={all_records[0].link},
    )
    assert len(filtered) == 1
    assert filtered[0].nom != "Alice" or "bob" in filtered[0].link.lower()


def test_linkedin_use_keep_searching_requires_contact(monkeypatch: pytest.MonkeyPatch) -> None:
    from scraper.collectors import _linkedin_use_keep_searching

    monkeypatch.setattr(settings, "scraper_linkedin_require_email_or_whatsapp", True)
    monkeypatch.setattr(settings, "scraper_linkedin_keep_searching_until_contact", True)
    assert _linkedin_use_keep_searching() is True
    monkeypatch.setattr(settings, "scraper_linkedin_keep_searching_until_contact", False)
    assert _linkedin_use_keep_searching() is False


def test_linkedin_inter_profile_pause_ignores_bot_delay_min(monkeypatch: pytest.MonkeyPatch) -> None:
    from scraper.timing import linkedin_inter_profile_pause_ms

    monkeypatch.setattr(settings, "delay_min", 60)
    monkeypatch.setattr(settings, "scraper_inter_profile_pause_seconds", 2.0)
    monkeypatch.setattr(settings, "scraper_fast_mode", False)
    monkeypatch.setattr(settings, "scraper_stable_linkedin_mode", False)
    assert linkedin_inter_profile_pause_ms() == 2000


def test_scraper_fast_mode_off_preserves_site_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    from scraper.timing import site_crawl_max_pages_effective, site_crawl_total_seconds_effective

    monkeypatch.setattr(settings, "scraper_fast_mode", False)
    monkeypatch.setattr(settings, "scraper_site_crawl_max_pages", 44)
    monkeypatch.setattr(settings, "scraper_site_crawl_total_seconds", 99.0)
    assert site_crawl_max_pages_effective() == 44
    assert site_crawl_total_seconds_effective() == 99.0


def test_instagram_password_login_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from scraper.instagram_login import instagram_password_login_configured

    monkeypatch.setattr(settings, "instagram_username", "")
    monkeypatch.setattr(settings, "instagram_password", "")
    assert instagram_password_login_configured() is False
    monkeypatch.setattr(settings, "instagram_username", "user")
    monkeypatch.setattr(settings, "instagram_password", "secret")
    assert instagram_password_login_configured() is True


def test_instagram_session_storage_ready(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from scraper.instagram_login import instagram_session_storage_ready

    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "session_dir", "sessions")
    (tmp_path / "sessions").mkdir()
    assert instagram_session_storage_ready() is False

    ig = tmp_path / "sessions" / "instagram.json"
    ig.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")
    assert instagram_session_storage_ready() is False

    ig.write_text(
        '{"cookies":[{"name":"sessionid","value":"x","domain":".instagram.com","path":"/"}],'
        '"origins":[]}',
        encoding="utf-8",
    )
    assert instagram_session_storage_ready() is True


def test_instagram_automation_blocked_recaptcha_url() -> None:
    from scraper.instagram_login import (
        _instagram_automation_blocked_message,
        _instagram_likely_authenticated_url,
    )

    u = "https://www.instagram.com/auth_platform/recaptcha/?apc=test"
    msg = _instagram_automation_blocked_message(u)
    assert msg is not None
    assert "reCAPTCHA" in msg
    assert _instagram_likely_authenticated_url(u) is False


def test_instagram_likely_authenticated_vs_login() -> None:
    from scraper.instagram_login import _instagram_likely_authenticated_url

    assert _instagram_likely_authenticated_url("https://www.instagram.com/") is True
    assert _instagram_likely_authenticated_url("https://www.instagram.com/explore/tags/foo/") is True
    assert _instagram_likely_authenticated_url("https://www.instagram.com/accounts/login/") is False


def test_instagram_ui_noise_skips_note_placeholder() -> None:
    from scraper.collectors import _instagram_line_is_ui_noise

    assert _instagram_line_is_ui_noise("Note...", "demotestai")
    assert _instagram_line_is_ui_noise("Note…", "demotestai")
    assert _instagram_line_is_ui_noise("Suivre", "demotestai")
    assert not _instagram_line_is_ui_noise("Studio Demo", "demotestai")


def test_resolve_scraper_csv_path_instagram_vs_linkedin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from scraper.writer import resolve_scraper_csv_path

    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "scraper_output_csv", "leads/scraper_output.csv")
    monkeypatch.setattr(settings, "scraper_instagram_output_csv", "leads/scraper_instagram.csv")
    (tmp_path / "leads").mkdir()
    assert resolve_scraper_csv_path("instagram") == tmp_path / "leads" / "scraper_instagram.csv"
    assert resolve_scraper_csv_path("linkedin") == tmp_path / "leads" / "scraper_output.csv"


def test_resolve_scraper_csv_path_instagram_falls_back_when_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from scraper.writer import resolve_scraper_csv_path

    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "scraper_output_csv", "leads/out.csv")
    monkeypatch.setattr(settings, "scraper_instagram_output_csv", "")
    (tmp_path / "leads").mkdir()
    assert resolve_scraper_csv_path("instagram") == tmp_path / "leads" / "out.csv"


def test_location_filter_excludes_tunisia() -> None:
    from scraper.location_filter import filter_records_excluded_locations, record_indicates_excluded_location
    from scraper.models import EMPTY_VALUE, ScraperRecord

    excl = ("tunisia", "tunisie", "tunis", "monastir")
    tn = ScraperRecord(
        nom="Ali",
        pays="Gouvernorat Tunis, Tunisie",
        email="a@b.co",
        link="https://www.linkedin.com/in/ali",
    )
    fr = ScraperRecord(
        nom="Marie",
        pays="Paris, France",
        email="m@b.co",
        link="https://www.linkedin.com/in/marie",
    )
    unknown = ScraperRecord(nom="X", pays=EMPTY_VALUE, email="x@b.co", link="https://www.linkedin.com/in/x")
    tn_email = ScraperRecord(
        nom="Safa",
        pays=EMPTY_VALUE,
        email="contact@centremami.tn",
        link="https://www.linkedin.com/in/safa",
    )
    tn_phone = ScraperRecord(
        nom="Y",
        pays=EMPTY_VALUE,
        email="y@b.co",
        whatsapp="+216 20 123 456",
        link="https://www.linkedin.com/in/y",
    )
    assert record_indicates_excluded_location(tn, excl)
    assert not record_indicates_excluded_location(fr, excl)
    assert not record_indicates_excluded_location(unknown, excl)
    assert record_indicates_excluded_location(tn_email, excl)
    assert record_indicates_excluded_location(tn_phone, excl)
    kept = filter_records_excluded_locations([tn, fr, unknown, tn_email, tn_phone], excl)
    assert len(kept) == 2
    assert {r.nom for r in kept} == {"Marie", "X"}


def test_location_filter_no_false_positive_nice_in_magnificent() -> None:
    from scraper.country_presets import keywords_for_country_form
    from scraper.location_filter import record_matches_include_location
    from scraper.models import EMPTY_VALUE, ScraperRecord

    include = keywords_for_country_form(["France"], "")
    record = ScraperRecord(
        nom="John",
        about="Magnificent growth leader",
        pays=EMPTY_VALUE,
        link="https://li/in/j",
    )
    assert not record_matches_include_location(record, include)


def test_location_filter_includes_france_only() -> None:
    from scraper.country_presets import keywords_for_country_form
    from scraper.location_filter import apply_location_filters, record_matches_include_location
    from scraper.models import ScraperRecord

    include = keywords_for_country_form(["France"], "")
    fr = ScraperRecord(nom="Marie", pays="Paris, France", link="https://li/in/m")
    us = ScraperRecord(nom="John", pays="Austin, Texas", link="https://li/in/j")
    assert record_matches_include_location(fr, include)
    assert not record_matches_include_location(us, include)
    kept = apply_location_filters([fr, us], include_keywords=include, exclude_keywords=())
    assert len(kept) == 1
    assert kept[0].nom == "Marie"


def test_split_scraper_queries_keyword_mode() -> None:
    from scraper.query_parse import split_scraper_queries

    assert split_scraper_queries("founder saas b2b") == ["founder saas b2b"]
    assert split_scraper_queries("founder, CEO; marketing") == ["founder", "CEO", "marketing"]
    assert split_scraper_queries("a\nb\nc") == ["a", "b", "c"]
    assert split_scraper_queries("dup, dup, other") == ["dup", "other"]


def test_split_scraper_queries_hashtag_mode() -> None:
    from scraper.query_parse import split_scraper_queries

    assert split_scraper_queries("#startup #marketing", mode="hashtag") == [
        "startup",
        "marketing",
    ]
    assert split_scraper_queries("design, startup", mode="hashtag") == ["design", "startup"]


def test_linkedin_filter_prioritize_email(monkeypatch: pytest.MonkeyPatch) -> None:
    from scraper.collectors import _filter_linkedin_records_with_contact, _linkedin_has_email_or_whatsapp
    from scraper.models import EMPTY_VALUE, ScraperRecord

    monkeypatch.setattr(settings, "scraper_linkedin_require_email_or_whatsapp", True)
    monkeypatch.setattr(settings, "scraper_linkedin_prioritize_email", True)
    with_email = ScraperRecord(nom="A", email="a@b.co", whatsapp=EMPTY_VALUE, link="https://li/in/a")
    with_both = ScraperRecord(nom="D", email="d@b.co", whatsapp="33601020304", link="https://li/in/d")
    with_wa = ScraperRecord(nom="B", email=EMPTY_VALUE, whatsapp="33601020304", link="https://li/in/b")
    empty = ScraperRecord(nom="C", email=EMPTY_VALUE, whatsapp=EMPTY_VALUE, link="https://li/in/c")
    assert _linkedin_has_email_or_whatsapp(with_email)
    assert _linkedin_has_email_or_whatsapp(with_both)
    assert not _linkedin_has_email_or_whatsapp(with_wa)
    assert not _linkedin_has_email_or_whatsapp(empty)
    filtered = _filter_linkedin_records_with_contact([with_email, with_wa, empty, with_both])
    assert len(filtered) == 2

    monkeypatch.setattr(settings, "scraper_linkedin_prioritize_email", False)
    assert _linkedin_has_email_or_whatsapp(with_wa)
    filtered2 = _filter_linkedin_records_with_contact([with_email, with_wa, empty])
    assert len(filtered2) == 2

    monkeypatch.setattr(settings, "scraper_linkedin_require_email_or_whatsapp", False)
    assert len(_filter_linkedin_records_with_contact([empty])) == 1


def test_instagram_validate_record_strips_social_domain() -> None:
    from scraper.collectors import _instagram_validate_record
    from scraper.models import EMPTY_VALUE, ScraperRecord

    r = ScraperRecord(
        nom="Test",
        email="contact@gmail.com",
        whatsapp="+33612345678",
        domaine="cdninstagram.com",
        app="instagram",
        link="https://www.instagram.com/t/",
    )
    v = _instagram_validate_record(r)
    assert v.email == "contact@gmail.com"
    assert v.whatsapp and v.whatsapp.isdigit()
    assert v.domaine == EMPTY_VALUE


def test_run_search_writes_live_rows(
    temp_scraper_output: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_collect(_request):
        return [ScraperRecord(nom="Alex", app="linkedin", link="https://www.linkedin.com/in/alex")]

    monkeypatch.setattr("scraper.cli.collect_live", fake_collect)
    result = run_search(mode="keyword", app="linkedin", query="founder", limit=1, append=False)
    assert result.written == 1
    assert Path(result.output_path).exists()


def test_parse_linkedin_card_maps_location_and_role() -> None:
    parsed = parse_linkedin_card(
        "Samer G. • 2e\n"
        "Software Engineer | Backend & AI Systems | Founder @ Glitch Inc\n"
        "Monastir, Gouvernorat Monastir, Tunisie"
    )
    assert parsed["nom"] == "Samer G."
    assert "Software Engineer" in parsed["poste"]
    assert "Monastir" in parsed["pays"]
    assert "Glitch Inc" in parsed["entreprise"]


def test_parse_linkedin_card_ignores_follower_noise() -> None:
    parsed = parse_linkedin_card(
        "Zaineb Huzefa ali\n"
        "Ayurveda Practitioner +17 yrs in UAE\n"
        "822 abonnés\n"
        "Suivre"
    )
    assert parsed["nom"] == "Zaineb Huzefa ali"
    assert "Ayurveda" in parsed["poste"]
    assert parsed["pays"] == EMPTY_VALUE
    assert parsed["entreprise"] == EMPTY_VALUE


def test_parse_linkedin_card_keeps_headline_and_location() -> None:
    parsed = parse_linkedin_card(
        "Safa DERBALI\n"
        "Gouvernorat Tunis, Tunisie\n"
        "Data Scientist | AI Engineer | Python Developer\n"
        "• 2e"
    )
    assert parsed["nom"] == "Safa DERBALI"
    assert "Gouvernorat Tunis" in parsed["pays"]
    assert "Data Scientist" in parsed["poste"]


def test_writer_deduplicates_links(temp_scraper_output: Path) -> None:
    writer = ScraperWriter(temp_scraper_output)
    lead = ScraperRecord(
        nom="Zaineb",
        app="linkedin",
        link="https://www.linkedin.com/in/zaineb-huzefa-ali-660955178",
    )
    writer.write([lead], append=False)
    writer.write([lead], append=True)
    frame = temp_scraper_output.read_text(encoding="utf-8")
    assert frame.count("zaineb-huzefa-ali-660955178") == 1


def test_resolve_linkedin_scopes_defaults_to_all_categories() -> None:
    assert resolve_linkedin_scopes([]) == list(LINKEDIN_SCOPE_PATHS.keys())
    assert resolve_linkedin_scopes(["all"]) == list(LINKEDIN_SCOPE_PATHS.keys())


def test_resolve_linkedin_scopes_accepts_comma_separated_values() -> None:
    assert resolve_linkedin_scopes(["people,posts", "jobs"]) == ["people", "posts", "jobs"]


def test_build_linkedin_search_url_maps_learning_scope() -> None:
    url = build_linkedin_search_url("python", "courses")
    assert "/search/results/learning/" in url
    assert "keywords=python" in url


def test_website_from_linkedin_redirect() -> None:
    redirected = (
        "https://www.linkedin.com/redir/redirect?url=https%3A%2F%2Fwww.acme-corp.io%2Fabout"
    )
    assert website_from_href(redirected) == "https://www.acme-corp.io/about"


def test_parse_website_reads_plain_domain_after_label() -> None:
    text = "Coordonnées\nSite web\nwww.glitch.inc"
    assert parse_website(text) == "https://www.glitch.inc"


def test_extract_contacts_from_mailto_and_tel_hrefs() -> None:
    contacts = extract_contacts_from_sources(
        text="Coordonnées\nSite web\nacme-corp.io",
        hrefs=[
            "mailto:contact@acme-corp.io",
            "tel:+21620123456",
            "https://www.linkedin.com/redir/redirect?url=https%3A%2F%2Fwww.acme-corp.io",
        ],
    )
    assert contacts["email"] == "contact@acme-corp.io"
    assert contacts["whatsapp"] == "21620123456"
    assert "acme-corp.io" in contacts["site_web"].lower()


def test_extract_contacts_company_redirect_and_surface_style() -> None:
    contacts = extract_contacts_from_sources(
        text="Clinic Anywhere\nHôpitaux et services de santé\nSite web\n",
        hrefs=[
            "https://www.linkedin.com/redir/redirect?url=https%3A%2F%2Fwww.clinic-anywhere.com%2F",
        ],
    )
    assert "clinic-anywhere.com" in contacts["site_web"].lower()


def test_extract_contacts_ignores_linkedin_html_noise() -> None:
    contacts = extract_contacts_from_sources(
        text="",
        hrefs=[
            "https://static.licdn.com/sc/h/abc123",
            "mailto:tracking@linkedin.com",
            "tel:19992025",
        ],
    )
    assert contacts["email"] == EMPTY_VALUE
    assert contacts["whatsapp"] == EMPTY_VALUE
    assert contacts["site_web"] == EMPTY_VALUE


def test_extract_contacts_email_same_line_as_label() -> None:
    contacts = extract_contacts_from_sources(
        text="Phone\n+33123456789\nEmail: Jane.Doe@acme.io\n",
        hrefs=[],
    )
    assert contacts["email"] == "jane.doe@acme.io"


def test_extract_contacts_email_from_unlabeled_modal_blob() -> None:
    """Plain address in contact overlay without strict label/newline layout."""
    contacts = extract_contacts_from_sources(
        text="Reach me at outreach@acme.io for collaborations.",
        hrefs=[],
    )
    assert contacts["email"] == "outreach@acme.io"


def test_normalize_email_accepts_gmail() -> None:
    assert normalize_email("Jane.Doe@gmail.com") == "jane.doe@gmail.com"


def test_parse_email_skips_blocked_host_then_takes_next() -> None:
    blob = "sales@linkedin.com also contact@partner.io"
    assert parse_email(blob) == "contact@partner.io"


def test_parse_email_deobfuscates_bracket_at_dot() -> None:
    assert parse_email("john [at] acme [dot] com") == "john@acme.com"


def test_extract_contacts_from_percent_encoded_mailto() -> None:
    contacts = extract_contacts_from_sources(
        text="",
        hrefs=["mailto:jane.doe%40gmail.com"],
    )
    assert contacts["email"] == "jane.doe@gmail.com"


def test_merge_contact_layers_respects_priority() -> None:
    first = extract_contacts_from_sources(text="Email: first@acme.io", hrefs=[])
    second = extract_contacts_from_sources(text="Email: second@other.com", hrefs=[])
    merged = merge_contact_layers(first, second)
    assert merged["email"] == "first@acme.io"


def test_split_display_name_for_guess() -> None:
    assert split_display_name_for_guess("Ilyes Ben Mansour") == ("Ilyes", "Mansour")


def test_guess_emails_from_name_and_domain_patterns() -> None:
    out = guess_emails_from_name_and_domain("Ilyes", "Mansour", "acme.io")
    assert "ilyes.mansour@acme.io" in out
    assert "imansour@acme.io" in out


def test_extract_company_from_headline_and_company_link() -> None:
    company = extract_company_from_sources(
        text="Expérience\nEquinor",
        hrefs=["https://www.linkedin.com/company/equinor/"],
        headline="Consultant Data Engineer @ Equinor | PySpark",
    )
    assert company == "Equinor"


def test_parse_linkedin_company_card_maps_company_fields() -> None:
    parsed = parse_linkedin_company_card(
        "Equinor\n"
        "Oil and Gas\n"
        "Stavanger, Norway"
    )
    assert parsed["nom"] == "Equinor"
    assert parsed["entreprise"] == "Equinor"
    assert parsed["poste"] == "Oil and Gas"
    assert "Norway" in parsed["pays"]


def test_normalize_whatsapp_rejects_national_without_country_code() -> None:
    assert normalize_whatsapp_number("0612345678") == EMPTY_VALUE
    assert normalize_whatsapp_number("+33612345678") == "33612345678"


def test_parse_whatsapp_from_wa_me_link() -> None:
    html = '<p><a href="https://wa.me/21612345678">WhatsApp</a></p>'
    assert parse_whatsapp_from_links(html) == "21612345678"
    assert parse_whatsapp(html) == "21612345678"


def test_parse_whatsapp_from_web_whatsapp_send_url() -> None:
    html = 'Contact <a href="https://web.whatsapp.com/send?phone=33123456789">WhatsApp</a>'
    assert parse_whatsapp_from_links(html) == "33123456789"


def test_parse_whatsapp_from_send_url_percent_encoded_plus() -> None:
    blob = "https://web.whatsapp.com/send?phone=%2B33698765432"
    assert parse_whatsapp_from_links(blob) == "33698765432"


def test_parse_whatsapp_from_wa_me_path_with_plus() -> None:
    assert parse_whatsapp_from_links("https://wa.me/+33611122333") == "33611122333"


def test_linkedin_coordonees_email_french_multiline() -> None:
    from scraper.linkedin_contacts import _linkedin_coordonees_email

    blob = (
        "Coordonnées\nProfil de ilyes\nlinkedin.com/in/ilyesbenmansour\nE-mail\n\n"
        "ilyesbenmansour@hotmail.com\nConnecté(e) depuis\n"
    )
    assert _linkedin_coordonees_email(blob) == "ilyesbenmansour@hotmail.com"


def test_extract_contacts_from_sources_picks_email_after_e_mail_label() -> None:
    text = "E-mail\nrihabbraiek1996@gmail.com\n"
    contacts = extract_contacts_from_sources(text=text, hrefs=[])
    assert contacts["email"] == "rihabbraiek1996@gmail.com"


def test_linkedin_coordonees_unicode_hyphen_in_email_label() -> None:
    from scraper.linkedin_contacts import _linkedin_coordonees_email

    blob = "E\u2011mail\nuser@fixture-leads.io\n"
    assert _linkedin_coordonees_email(blob) == "user@fixture-leads.io"


def test_extract_email_phone_from_html_mailto_and_tel() -> None:
    html = (
        '<html><body>'
        '<a href="mailto:contact@fixture-leads.io?subject=Hello">mail</a>'
        '<a href="tel:+21698765432">tel</a>'
        "</body></html>"
    )
    email, phone = extract_email_phone_from_html(html)
    assert email == "contact@fixture-leads.io"
    assert phone == "21698765432"


def test_extract_email_phone_from_ld_json() -> None:
    html = (
        '<script type="application/ld+json">'
        '{"@type":"Organization","email":"info@acme.test","telephone":"+33 1 23 45 67 89"}'
        "</script>"
    )
    email, phone = extract_email_phone_from_html(html)
    assert email == "info@acme.test"
    assert phone == "33123456789"


def test_discover_same_site_links_filters_external() -> None:
    html = """
    <a href="/contact">c</a>
    <a href="https://evil.com/x">bad</a>
    <a href="/about">a</a>
    """
    hosts = {"shop.example", "www.shop.example"}
    links = discover_same_site_links(
        html,
        "https://www.shop.example/fr/",
        hosts,
        max_links=20,
    )
    assert any("/contact" in u for u in links)
    assert any("/about" in u for u in links)
    assert not any("evil.com" in u for u in links)


def test_extract_email_phone_from_html_plain_text() -> None:
    html = "<div>Reach us at support@acme.test or +1 415 555 0100</div>"
    email, phone = extract_email_phone_from_html(html)
    assert email == "support@acme.test"
    assert phone == "14155550100"


# ── ProfileCache ──────────────────────────────────────────────────────────────

def _make_cache(tmp_path) -> "ProfileCache":
    from scraper.profile_cache import ProfileCache
    return ProfileCache(
        db_path=tmp_path / "test_cache.db",
        ttl_with_email=7 * 86400,
        ttl_no_email=1 * 86400,
        enabled=True,
    )


def test_profile_cache_hit_with_email(tmp_path) -> None:
    """Un profil avec email doit retourner 'hit' après mark_seen."""
    from scraper.profile_cache import ProfileCache
    cache = _make_cache(tmp_path)
    rec = ScraperRecord(
        nom="Alice Dupont", email="alice@example.com", entreprise="Agence X",
        poste="CEO", domaine="example.com", link="https://linkedin.com/in/alice"
    )
    cache.mark_seen(rec)
    status, cached = cache.lookup(url="https://linkedin.com/in/alice")
    assert status == "hit"
    assert cached is not None
    assert cached.email == "alice@example.com"


def test_profile_cache_skip_no_email(tmp_path) -> None:
    """Un profil sans email doit retourner 'skip' (on ne réessaie pas avant TTL)."""
    cache = _make_cache(tmp_path)
    rec = ScraperRecord(
        nom="Bob Martin", email="vide", entreprise="Startup Y",
        poste="CTO", domaine="startup-y.fr", link="https://linkedin.com/company/startup-y"
    )
    cache.mark_seen(rec)
    status, cached = cache.lookup(url="https://linkedin.com/company/startup-y")
    assert status == "skip"
    assert cached is None


def test_profile_cache_stale_unknown(tmp_path) -> None:
    """Un profil jamais vu doit retourner 'stale'."""
    cache = _make_cache(tmp_path)
    status, cached = cache.lookup(url="https://linkedin.com/in/unknown-person")
    assert status == "stale"
    assert cached is None


def test_profile_cache_domain_fallback(tmp_path) -> None:
    """Lookup par domain doit retrouver un profil enregistré avec une URL différente."""
    from scraper.profile_cache import ProfileCache
    cache = _make_cache(tmp_path)
    rec = ScraperRecord(
        nom="Claire Legrand", email="claire@domaine-test.fr", entreprise="Domaine Test",
        poste="DG", domaine="domaine-test.fr", link="https://linkedin.com/company/domaine-test"
    )
    cache.mark_seen(rec)
    # Lookup via domain seulement (pas l'URL exacte)
    status, cached = cache.lookup(url="https://linkedin.com/in/autre-url", domain="domaine-test.fr")
    assert status == "hit"
    assert cached is not None
    assert cached.email == "claire@domaine-test.fr"


def test_profile_cache_phash_fallback(tmp_path) -> None:
    """Lookup par profile_hash doit fonctionner si URL et domain sont inconnus."""
    from scraper.profile_cache import ProfileCache, _profile_hash
    cache = _make_cache(tmp_path)
    rec = ScraperRecord(
        nom="David Noir", email="david@agence.io", entreprise="Agence IO",
        poste="Fondateur", domaine="agence.io", link="https://linkedin.com/in/david-noir"
    )
    cache.mark_seen(rec)
    phash = _profile_hash("David Noir", "Agence IO", "Fondateur")
    status, cached = cache.lookup(url="https://linkedin.com/in/autre", phash=phash)
    assert status == "hit"
    assert cached is not None


def test_profile_cache_expired(tmp_path) -> None:
    """Un profil avec TTL de 0 secondes doit être immédiatement expiré."""
    from scraper.profile_cache import ProfileCache
    cache = ProfileCache(
        db_path=tmp_path / "test_expire.db",
        ttl_with_email=0,
        ttl_no_email=0,
        enabled=True,
    )
    rec = ScraperRecord(
        nom="Eve Blanc", email="eve@test.com", entreprise="Test Co",
        poste="Dir", link="https://linkedin.com/in/eve"
    )
    cache.mark_seen(rec)
    status, _ = cache.lookup(url="https://linkedin.com/in/eve")
    assert status == "stale"


def test_profile_cache_url_normalization(tmp_path) -> None:
    """Les URLs avec query-string et casse mixte sont normalisées identiquement."""
    cache = _make_cache(tmp_path)
    rec = ScraperRecord(
        nom="Frank Gris", email="frank@co.fr", entreprise="Co FR",
        poste="PDG", link="https://Linkedin.com/in/frank-gris?trk=123"
    )
    cache.mark_seen(rec)
    # Lookup sans query-string, casse différente
    status, cached = cache.lookup(url="https://linkedin.com/in/frank-gris")
    assert status == "hit"


def test_profile_cache_prune(tmp_path) -> None:
    """prune_expired() supprime les entrées expirées de SQLite."""
    from scraper.profile_cache import ProfileCache
    import time
    cache = ProfileCache(
        db_path=tmp_path / "test_prune.db",
        ttl_with_email=0,
        ttl_no_email=0,
        enabled=True,
    )
    rec = ScraperRecord(
        nom="Grace Beige", email="grace@prune.io", entreprise="Prune Inc",
        poste="CEO", link="https://linkedin.com/in/grace"
    )
    cache.mark_seen(rec)
    deleted = cache.prune_expired()
    assert deleted >= 1


def test_profile_cache_stats(tmp_path) -> None:
    """stats() retourne les compteurs attendus."""
    cache = _make_cache(tmp_path)
    rec = ScraperRecord(
        nom="Hugo Vert", email="hugo@stats.io", entreprise="Stats Co",
        poste="CTO", link="https://linkedin.com/in/hugo"
    )
    cache.mark_seen(rec)
    cache.lookup(url="https://linkedin.com/in/hugo")       # hit
    cache.lookup(url="https://linkedin.com/in/inconnu")    # miss
    s = cache.stats()
    assert s["hits"] == 1
    assert s["misses"] == 1
    assert s["stores"] == 1


def test_profile_cache_disabled(tmp_path) -> None:
    """Quand enabled=False, toutes les lookups retournent 'stale'."""
    from scraper.profile_cache import ProfileCache
    cache = ProfileCache(db_path=tmp_path / "x.db", enabled=False)
    rec = ScraperRecord(
        nom="Iris Rouge", email="iris@x.fr", link="https://linkedin.com/in/iris"
    )
    cache.mark_seen(rec)  # ne doit pas planter
    status, _ = cache.lookup(url="https://linkedin.com/in/iris")
    assert status == "stale"  # disabled → toujours stale


def test_profile_cache_outreach_queued(tmp_path) -> None:
    """mark_outreach_queued / is_outreach_queued fonctionnent correctement."""
    cache = _make_cache(tmp_path)
    rec = ScraperRecord(
        nom="Jules Blanc", email="jules@outreach.io", link="https://linkedin.com/in/jules",
        entreprise="Outreach Co", poste="CEO",
    )
    cache.mark_seen(rec)
    assert not cache.is_outreach_queued("https://linkedin.com/in/jules")
    cache.mark_outreach_queued("https://linkedin.com/in/jules", score=6.5)
    assert cache.is_outreach_queued("https://linkedin.com/in/jules")


def test_profile_cache_contacted(tmp_path) -> None:
    """mark_contacted / is_contacted fonctionnent correctement."""
    cache = _make_cache(tmp_path)
    rec = ScraperRecord(
        nom="Lea Noir", email="lea@contacted.fr", link="https://linkedin.com/in/lea",
    )
    cache.mark_seen(rec)
    assert not cache.is_contacted("https://linkedin.com/in/lea")
    cache.mark_contacted("https://linkedin.com/in/lea")
    assert cache.is_contacted("https://linkedin.com/in/lea")
    # is_outreach_queued doit aussi retourner True pour les leads déjà contactés
    assert cache.is_outreach_queued("https://linkedin.com/in/lea")


def test_profile_cache_get_pending_outreach(tmp_path) -> None:
    """get_pending_outreach retourne les leads avec email non encore en file."""
    from scraper.profile_cache import ProfileCache
    cache = ProfileCache(
        db_path=tmp_path / "pending.db",
        ttl_with_email=7 * 86400,
        ttl_no_email=1 * 86400,
        enabled=True,
    )
    # 3 leads avec email
    for i in range(3):
        cache.mark_seen(ScraperRecord(
            nom=f"Lead {i}", email=f"lead{i}@test.io",
            link=f"https://linkedin.com/in/lead-{i}",
        ))
    # 1 lead sans email
    cache.mark_seen(ScraperRecord(
        nom="No Email", email="vide", link="https://linkedin.com/in/no-email",
    ))
    # 1 lead déjà queued
    cache.mark_seen(ScraperRecord(
        nom="Already Q", email="q@test.io", link="https://linkedin.com/in/already-q",
    ))
    cache.mark_outreach_queued("https://linkedin.com/in/already-q")

    pending = cache.get_pending_outreach(limit=50)
    pending_urls = {r.link for r in pending}
    # les 3 leads avec email et pas encore queued
    assert "https://linkedin.com/in/lead-0" in pending_urls
    assert "https://linkedin.com/in/lead-1" in pending_urls
    assert "https://linkedin.com/in/lead-2" in pending_urls
    # le lead sans email ne doit pas apparaître
    assert "https://linkedin.com/in/no-email" not in pending_urls
    # le lead déjà queued ne doit pas apparaître
    assert "https://linkedin.com/in/already-q" not in pending_urls


# ── EmailPipeline ─────────────────────────────────────────────────────────────

def test_score_lead_with_email_and_decision_maker() -> None:
    """Un décideur avec email professionnel doit avoir un score élevé."""
    from scraper.email_pipeline import score_lead
    rec = ScraperRecord(
        nom="Marie Dupont", email="marie@agence.fr", entreprise="Agence Top",
        poste="Directrice", domaine="agence.fr", site_web="https://agence.fr",
        about="Agence de communication digitale.", pays="France",
    )
    s = score_lead(rec)
    assert s >= 5.0, f"Score trop bas pour un décideur avec email professionnel : {s}"


def test_score_lead_generic_email() -> None:
    """Un email Gmail doit minorer le score."""
    from scraper.email_pipeline import score_lead
    rec = ScraperRecord(
        nom="Paul Test", email="paul@gmail.com", entreprise="Test SA",
        poste="Employé", link="https://linkedin.com/in/paul",
    )
    s_gmail = score_lead(rec)
    rec2 = ScraperRecord(
        nom="Paul Pro", email="paul@test-sa.fr", entreprise="Test SA",
        poste="Employé", link="https://linkedin.com/in/paul-pro",
    )
    s_pro = score_lead(rec2)
    assert s_pro > s_gmail


def test_score_lead_no_email() -> None:
    """Sans email, le score doit être inférieur à celui avec email (pas de bonus +3)."""
    from scraper.email_pipeline import score_lead
    rec_no_email  = ScraperRecord(nom="Sans Email", email="vide",          poste="CEO")
    rec_with_email = ScraperRecord(nom="Avec Email", email="ceo@test.fr",  poste="CEO")
    assert score_lead(rec_no_email) < score_lead(rec_with_email)
    # Sans email, le score doit être < 3 (threshold par défaut) → ignoré par le pipeline
    assert score_lead(rec_no_email) < 3.0


def test_classify_lead_agency() -> None:
    from scraper.email_pipeline import LeadCategory, classify_lead
    rec = ScraperRecord(
        nom="Sophie", entreprise="Agence Digitale", poste="Directrice marketing",
    )
    assert classify_lead(rec) == LeadCategory.AGENCY


def test_classify_lead_ecommerce() -> None:
    from scraper.email_pipeline import LeadCategory, classify_lead
    rec = ScraperRecord(nom="Marc", entreprise="Ma Boutique Online", poste="Gérant e-commerce")
    assert classify_lead(rec) == LeadCategory.ECOMMERCE


def test_classify_lead_unknown() -> None:
    from scraper.email_pipeline import LeadCategory, classify_lead
    rec = ScraperRecord(nom="Inconnu", entreprise="Entreprise XYZ", poste="Opérateur")
    assert classify_lead(rec) == LeadCategory.UNKNOWN


def test_classify_tag_hot_warm_cold() -> None:
    from scraper.email_pipeline import classify_tag
    from leads.models import LeadTag
    assert classify_tag(8.0) == LeadTag.HOT
    assert classify_tag(5.0) == LeadTag.WARM
    assert classify_tag(1.0) == LeadTag.COLD


def test_record_to_bot_lead() -> None:
    from scraper.email_pipeline import LeadCategory, record_to_bot_lead, score_lead
    rec = ScraperRecord(
        nom="Alice Legrand", email="alice@marketing.fr", entreprise="Marketing Pro",
        poste="CEO", domaine="marketing.fr", link="https://linkedin.com/in/alice",
        pays="France", about="Expert en marketing digital",
    )
    s = score_lead(rec)
    bot = record_to_bot_lead(rec, LeadCategory.AGENCY, s)
    assert bot.name == "Alice Legrand"
    assert bot.email == "alice@marketing.fr"
    assert bot.linkedin == "https://linkedin.com/in/alice"
    assert "Poste" in bot.notes
    assert "Score" in bot.notes
    assert bot.fingerprint()  # must not be empty


def test_email_pipeline_below_threshold() -> None:
    """Un lead avec score < threshold ne doit pas être injecté."""
    from scraper.email_pipeline import EmailPipeline
    pipeline = EmailPipeline(score_threshold=8.0, enabled=True)
    rec = ScraperRecord(
        nom="Bas Score", email="low@score.io", entreprise="Low Co",
        poste="Stagiaire", link="https://linkedin.com/in/low-score",
    )
    result = pipeline.process_accepted_lead(rec)
    assert result is False
    assert pipeline.stats().skipped >= 1


def test_email_pipeline_disabled() -> None:
    """Pipeline désactivé → process_accepted_lead retourne False immédiatement."""
    from scraper.email_pipeline import EmailPipeline
    pipeline = EmailPipeline(score_threshold=0.0, enabled=False)
    rec = ScraperRecord(
        nom="Disabled", email="test@enabled.io", link="https://linkedin.com/in/disabled"
    )
    assert pipeline.process_accepted_lead(rec) is False
    assert pipeline.stats().processed == 0


def test_email_pipeline_no_email() -> None:
    """Un lead sans email ne doit jamais passer dans le pipeline."""
    from scraper.email_pipeline import EmailPipeline
    pipeline = EmailPipeline(score_threshold=0.0, enabled=True)
    rec = ScraperRecord(nom="Sans Email", email="vide", link="https://linkedin.com/in/no-mail")
    assert pipeline.process_accepted_lead(rec) is False
