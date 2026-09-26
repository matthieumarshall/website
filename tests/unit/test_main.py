"""Tests for FastAPI routes and main application"""

import re
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from website import repository
from website.content import SIDEBAR_ITEMS
from website.main import app
from website.models import EAAthlete, UserRole
from website.passwords import hash_password
from website.services.uploads import DOCUMENT_POLICY, IMAGE_POLICY, FileStore
from website.web.deps import get_athlete_directory, get_document_store, get_image_store


class _FakeAthleteDirectory:
    def __init__(self, athletes: list[dict[str, object]]) -> None:
        self._athletes = [EAAthlete.model_validate(a) for a in athletes]

    def fetch_club_athletes(self, ea_club_id: str) -> list[EAAthlete]:
        return self._athletes


class TestHomeRoute:
    """Test home page endpoint"""

    def test_home_page_loads(self, test_client: TestClient) -> None:
        response = test_client.get("/")
        assert response.status_code == 200

    def test_home_page_html_response(self, test_client: TestClient) -> None:
        response = test_client.get("/")
        assert "text/html" in response.headers.get("content-type", "")

    def test_home_page_contains_title(self, test_client: TestClient) -> None:
        response = test_client.get("/")
        content = response.text.lower()
        assert "<title>" in content or "home" in content

    def test_home_page_unauthenticated_user(self, test_client: TestClient) -> None:
        response = test_client.get("/")
        assert response.status_code == 200

    def test_home_page_authenticated_user(
        self,
        test_client: TestClient,
        test_user,  # noqa: ANN001
        test_user_creds: dict,  # noqa: ANN001
    ) -> None:
        login_page = test_client.get("/login")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
        assert match
        test_client.post(
            "/login",
            data={**test_user_creds, "csrf_token": match.group(1)},
            follow_redirects=True,
        )
        assert test_client.get("/").status_code == 200


class TestLoginPageRoute:
    def test_login_page_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/login").status_code == 200

    def test_login_page_preserves_next_path(self, test_client: TestClient) -> None:
        response = test_client.get("/login?next=/entries")
        assert response.status_code == 200
        assert 'name="next_path" value="/entries"' in response.text


class TestSidebarItems:
    def test_sidebar_items_is_list(self) -> None:
        assert isinstance(SIDEBAR_ITEMS, tuple)

    def test_sidebar_items_has_nine_entries(self) -> None:
        assert len(SIDEBAR_ITEMS) == 9

    def test_all_items_have_required_fields(self) -> None:
        for item in SIDEBAR_ITEMS:
            assert item.name
            assert item.route
            assert item.page
            if item.children:
                for child in item.children:
                    assert child.name
                    assert child.route
                    assert child.page

    def test_all_routes_start_with_slash(self) -> None:
        for item in SIDEBAR_ITEMS:
            assert item.route.startswith("/")
            if item.children:
                for child in item.children:
                    assert child.route.startswith("/")

    def test_news_is_first_item(self) -> None:
        assert SIDEBAR_ITEMS[0].page == "news"
        assert SIDEBAR_ITEMS[0].route == "/news"

    def test_expected_pages_present(self) -> None:
        pages = {item.page for item in SIDEBAR_ITEMS}
        assert pages == {
            "news",
            "results",
            "standings",
            "divisions",
            "winners",
            "clubs",
            "rules_and_constitution",
            "administration",
            "fixtures",
        }

    def test_administration_has_sub_pages(self) -> None:
        admin_item = next(
            item for item in SIDEBAR_ITEMS if item.page == "administration"
        )
        assert admin_item.children
        assert len(admin_item.children) == 6
        sub_names = [child.name for child in admin_item.children]
        assert sub_names == [
            "Documents",
            "Links",
            "Athlete Registration Guide",
            "Race Directors Guide",
            "Suppliers List",
            "Team Managers Guide",
        ]
        sub_pages = {child.page for child in admin_item.children}
        assert sub_pages == {
            "administration",
            "links",
            "athlete_registration_guide",
            "race_directors_guide",
            "suppliers_list",
            "team_managers_guide",
        }


class TestHomeRedirect:
    def test_home_redirects_to_news(self, test_client: TestClient) -> None:
        response = test_client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/news"

    def test_home_eventually_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/").status_code == 200


class TestPublicPageRoutes:
    """Public pages (no auth required) return 200 HTML."""

    _pages = [
        ("news", "/news"),
        ("results", "/results"),
        ("divisions", "/divisions"),
        ("winners", "/winners"),
        ("clubs", "/clubs"),
        ("links", "/links"),
        ("rules_and_constitution", "/rules-and-constitution"),
        ("fixtures", "/fixtures"),
    ]

    def test_news_page_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/news").status_code == 200

    def test_results_page_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/results").status_code == 200

    def test_entries_page_loads(self, test_client: TestClient) -> None:
        # /entries is not linked from navigation and shows a work-in-progress notice.
        response = test_client.get("/entries")
        assert response.status_code == 200
        assert "work in progress" in response.text.lower()

    def test_entries_page_shows_wip_notice_for_admin(
        self, admin_client: TestClient
    ) -> None:
        response = admin_client.get("/entries")
        assert response.status_code == 200
        assert "work in progress" in response.text.lower()

    def test_admin_entries_empty_state_links_to_fixtures(
        self, admin_client: TestClient
    ) -> None:
        response = admin_client.get("/admin/entries")
        assert response.status_code == 200
        assert 'href="/fixtures"' in response.text

    def test_login_redirects_back_to_entries_after_success(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        repository.create_user(
            test_db,
            "admin_login_test",
            hash_password("AdminPassword123!@#"),
            UserRole.admin,
        )
        login_page = test_client.get("/login?next=/entries")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
        assert match
        response = test_client.post(
            "/login",
            data={
                "username": "admin_login_test",
                "password": "AdminPassword123!@#",
                "csrf_token": match.group(1),
                "next_path": "/entries",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/entries"

    def test_rules_and_constitution_page_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/rules-and-constitution").status_code == 200

    def test_rules_and_constitution_renders_mobile_and_desktop_toc_targets(
        self,
        test_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        repository.upsert_static_page(
            test_db,
            "rules-and-constitution",
            "<h1>League Rules</h1><h2>Eligibility</h2><p>Details</p>",
        )

        response = test_client.get("/rules-and-constitution")

        assert re.search(
            r'<button[^>]+data-bs-target="#toc-collapse-mobile"', response.text
        ), "Mobile contents toggle button not found"
        assert re.search(
            r'<ul[^>]+id="toc-list-mobile"[^>]+class="[^"]*\btoc-list\b',
            response.text,
        ), "Mobile TOC list not found"
        assert re.search(
            r'<div[^>]+class="[^"]*\bcol-lg-3\b[^"]*\bd-none\b[^"]*\bd-lg-block\b',
            response.text,
        ), "Desktop TOC sidebar wrapper not found"
        assert re.search(
            r'<ul[^>]+id="toc-list-desktop"[^>]+class="[^"]*\btoc-list\b',
            response.text,
        ), "Desktop TOC list not found"

    def test_all_public_pages_return_html(self, test_client: TestClient) -> None:
        for _, route in self._pages:
            response = test_client.get(route)
            assert "text/html" in response.headers.get("content-type", ""), route

    def test_sidebar_links_rendered_on_all_pages(self, test_client: TestClient) -> None:
        for _, route in self._pages:
            response = test_client.get(route)
            for item in SIDEBAR_ITEMS:
                assert item.name in response.text, f"'{item.name}' not found on {route}"

    def test_only_one_active_link_per_page(self, test_client: TestClient) -> None:
        for _, route in self._pages:
            response = test_client.get(route)
            assert response.text.count("nav-link active") == 1, route

    def test_correct_link_is_active(self, test_client: TestClient) -> None:
        for page, route in self._pages:
            response = test_client.get(route)
            match = re.search(
                r'class="nav-link active"[^>]*href="' + re.escape(route) + '"',
                response.text,
                re.DOTALL,
            )
            assert match is not None, f"No active link for {route}"


class TestEntryBatchGuardsAndAllocation:
    def _seed_manager_entries_domain(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> dict[str, int | str]:
        season = repository.create_season(test_db, "Entries Guard Season")
        other_season = repository.create_season(test_db, "Entries Other Season")
        club = repository.create_club(
            test_db,
            name="Guard Test Club",
            oxl_code="GTC",
            ea_club_id="55555",
        )
        manager = repository.create_user(
            test_db,
            "guard_manager",
            hash_password("GuardPassword123!@#"),
            UserRole.club_manager,
        )
        repository.create_club_manager(
            test_db,
            user_id=manager.id,
            club_id=club.id,
            email="guard@example.com",
        )
        repository.upsert_season_entry_config(
            test_db,
            season_id=season.id,
            entries_open=True,
            ea_reference_date="2025-08-31",
            total_fixtures=5,
            junior_pence_per_fixture=200,
            adult_pence_per_fixture=300,
        )
        repository.create_fixture(
            test_db,
            season_id=season.id,
            title="Guard Fixture",
            date=(date.today() + timedelta(days=14)).isoformat(),
            location_name="Venue",
            address="Address",
            timetable=[],
            travel_instructions="",
        )
        return {
            "season_id": season.id,
            "other_season_id": other_season.id,
            "club_id": club.id,
            "manager_id": manager.id,
            "manager_username": "guard_manager",
            "manager_password": "GuardPassword123!@#",
        }

    def _login_manager(
        self,
        test_client: TestClient,
        username: str,
        password: str,
    ) -> None:
        login_page = test_client.get("/login")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
        assert match
        resp = test_client.post(
            "/login",
            data={
                "username": username,
                "password": password,
                "csrf_token": match.group(1),
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_entries_create_batch_rejects_when_allocation_insufficient(
        self,
        test_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        seeded = self._seed_manager_entries_domain(test_db)
        season_id = int(seeded["season_id"])
        club_id = int(seeded["club_id"])
        self._login_manager(
            test_client,
            str(seeded["manager_username"]),
            str(seeded["manager_password"]),
        )

        # Only one slot allocated, but two athletes will be submitted.
        repository.upsert_club_allocation(
            test_db, season_id, club_id, allocated_slots=1
        )

        athletes = _FakeAthleteDirectory(
            [
                {
                    "IndividualRef": 20001,
                    "FirstName": "Alice",
                    "LastName": "Runner",
                    "DateOfBirth": "2012-04-01",
                    "RegistrationStatus": "Registered",
                },
                {
                    "IndividualRef": 20002,
                    "FirstName": "Bob",
                    "LastName": "Runner",
                    "DateOfBirth": "2010-07-15",
                    "RegistrationStatus": "Registered",
                },
            ]
        )
        app.dependency_overrides[get_athlete_directory] = lambda: athletes

        add_page = test_client.get(f"/entries/{season_id}/add")
        csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', add_page.text)
        assert csrf_match

        response = test_client.post(
            f"/entries/{season_id}/batch",
            data={
                "ea_urns": ["20001", "20002"],
                "csrf_token": csrf_match.group(1),
            },
            follow_redirects=False,
        )

        assert response.status_code == 403
        count = test_db.execute("SELECT COUNT(*) FROM entry_batches").fetchone()
        assert count
        assert count[0] == 0

    def test_batch_preview_404s_when_season_mismatch(
        self,
        test_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        seeded = self._seed_manager_entries_domain(test_db)
        season_id = int(seeded["season_id"])
        other_season_id = int(seeded["other_season_id"])
        club_id = int(seeded["club_id"])
        manager_id = int(seeded["manager_id"])
        self._login_manager(
            test_client,
            str(seeded["manager_username"]),
            str(seeded["manager_password"]),
        )

        batch = repository.create_entry_batch(
            test_db,
            season_id=season_id,
            club_id=club_id,
            manager_user_id=manager_id,
            fixtures_remaining_at_entry=2,
            total_pence=1000,
        )

        response = test_client.get(
            f"/entries/{other_season_id}/batch/{batch.id}/preview",
            follow_redirects=False,
        )
        assert response.status_code == 404

    def test_batch_checkout_404s_when_season_mismatch(
        self,
        test_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        seeded = self._seed_manager_entries_domain(test_db)
        season_id = int(seeded["season_id"])
        other_season_id = int(seeded["other_season_id"])
        club_id = int(seeded["club_id"])
        manager_id = int(seeded["manager_id"])
        self._login_manager(
            test_client,
            str(seeded["manager_username"]),
            str(seeded["manager_password"]),
        )

        batch = repository.create_entry_batch(
            test_db,
            season_id=season_id,
            club_id=club_id,
            manager_user_id=manager_id,
            fixtures_remaining_at_entry=2,
            total_pence=1000,
        )

        entries_page = test_client.get("/entries")
        csrf_match = re.search(
            r'name="csrf_token"\s+value="([^"]+)"', entries_page.text
        )
        assert csrf_match

        response = test_client.post(
            f"/entries/{other_season_id}/batch/{batch.id}/checkout",
            data={"csrf_token": csrf_match.group(1)},
            follow_redirects=False,
        )
        assert response.status_code == 404


class TestAdministrationAccess:
    def test_publicly_accessible(self, test_client: TestClient) -> None:
        assert test_client.get("/administration").status_code == 200

    def test_content_creator_can_access(
        self, content_creator_client: TestClient
    ) -> None:
        assert content_creator_client.get("/administration").status_code == 200

    def test_admin_can_access(self, admin_client: TestClient) -> None:
        assert admin_client.get("/administration").status_code == 200

    def test_document_sections_render(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        # Seed sections so the DB-backed page has content to render
        repository.create_administration_section(
            test_db, slug="notices", title="Notices", description="", sort_order=0
        )
        repository.create_administration_section(
            test_db, slug="agendas", title="Agendas", description="", sort_order=1
        )
        repository.create_administration_section(
            test_db,
            slug="meeting-notes",
            title="Meeting notes",
            description="",
            sort_order=2,
        )
        repository.create_administration_section(
            test_db, slug="accounts", title="Accounts", description="", sort_order=3
        )
        response = test_client.get("/administration")
        assert response.status_code == 200
        expected_sections = (
            ("notices", "Notices"),
            ("agendas", "Agendas"),
            ("meeting-notes", "Meeting notes"),
            ("accounts", "Accounts"),
        )
        for section_id, heading in expected_sections:
            assert f">{heading}</h2>" in response.text
            assert f'id="{section_id}-heading"' in response.text
            assert f'aria-labelledby="{section_id}-heading"' in response.text

    def test_document_download_links_include_pdf_and_zip(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        # Seed a section with one PDF and one ZIP document
        section = repository.create_administration_section(
            test_db, slug="agendas", title="Agendas", description="", sort_order=0
        )
        repository.create_administration_document(
            test_db,
            section_id=section.id,
            display_name="2025 AGM Agenda",
            filename="agenda.pdf",
            file_type="PDF",
            sort_order=2025,
        )
        repository.create_administration_document(
            test_db,
            section_id=section.id,
            display_name="2025 AGM Pack",
            filename="pack.zip",
            file_type="ZIP",
            sort_order=2025,
        )
        response = test_client.get("/administration")
        assert re.search(
            r'<a[^>]+href="/uploads/administration/[^"]+\.pdf"[^>]*\bdownload\b',
            response.text,
        )
        assert re.search(
            r'<a[^>]+href="/uploads/administration/[^"]+\.zip"[^>]*\bdownload\b',
            response.text,
        )


class TestAdministrationManage:
    def test_manage_page_requires_auth(self, test_client: TestClient) -> None:
        response = test_client.get("/administration/manage", follow_redirects=False)
        assert response.status_code in (302, 403)

    def test_manage_page_accessible_to_admin(self, admin_client: TestClient) -> None:
        assert admin_client.get("/administration/manage").status_code == 200

    def test_manage_page_accessible_to_content_creator(
        self, content_creator_client: TestClient
    ) -> None:
        assert content_creator_client.get("/administration/manage").status_code == 200

    def test_create_section(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        manage_page = admin_client.get("/administration/manage")
        csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', manage_page.text)
        assert csrf
        resp = admin_client.post(
            "/administration/manage/sections",
            data={
                "title": "Test Section",
                "slug": "test-section",
                "description": "A test section",
                "csrf_token": csrf.group(1),
            },
        )
        assert resp.status_code == 200
        assert "Test Section" in resp.text
        sections = repository.list_administration_sections(test_db)
        assert any(s.slug == "test-section" for s in sections)

    def test_create_section_invalid_slug(self, admin_client: TestClient) -> None:
        manage_page = admin_client.get("/administration/manage")
        csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', manage_page.text)
        assert csrf
        resp = admin_client.post(
            "/administration/manage/sections",
            data={
                "title": "Bad Slug",
                "slug": "Bad Slug!!",
                "description": "",
                "csrf_token": csrf.group(1),
            },
        )
        assert resp.status_code == 400

    def test_delete_empty_section(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        section = repository.create_administration_section(
            test_db, slug="to-delete", title="To Delete", description="", sort_order=0
        )
        manage_page = admin_client.get("/administration/manage")
        csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', manage_page.text)
        assert csrf
        resp = admin_client.post(
            f"/administration/manage/sections/{section.id}/delete",
            data={"csrf_token": csrf.group(1)},
        )
        assert resp.status_code == 200
        sections = repository.list_administration_sections(test_db)
        assert not any(s.id == section.id for s in sections)

    def test_delete_section_with_documents_rejected(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        section = repository.create_administration_section(
            test_db, slug="nonempty", title="Non-empty", description="", sort_order=0
        )
        repository.create_administration_document(
            test_db,
            section_id=section.id,
            display_name="A doc",
            filename="doc.pdf",
            file_type="PDF",
            sort_order=0,
        )
        manage_page = admin_client.get("/administration/manage")
        csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', manage_page.text)
        assert csrf
        resp = admin_client.post(
            f"/administration/manage/sections/{section.id}/delete",
            data={"csrf_token": csrf.group(1)},
        )
        assert resp.status_code == 400

    def test_upload_document(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        app.dependency_overrides[get_document_store] = lambda: FileStore(
            tmp_path, DOCUMENT_POLICY
        )
        section = repository.create_administration_section(
            test_db, slug="agendas", title="Agendas", description="", sort_order=0
        )
        manage_page = admin_client.get("/administration/manage")
        csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', manage_page.text)
        assert csrf
        resp = admin_client.post(
            f"/administration/manage/sections/{section.id}/documents",
            data={"display_name": "2025 Agenda", "csrf_token": csrf.group(1)},
            files={"file": ("agenda.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert resp.status_code == 200
        assert "2025 Agenda" in resp.text
        sections = repository.list_administration_sections(test_db)
        section_docs = next(s for s in sections if s.slug == "agendas").documents
        assert len(section_docs) == 1
        assert section_docs[0].display_name == "2025 Agenda"

    def test_upload_document_bad_extension(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        section = repository.create_administration_section(
            test_db, slug="agendas", title="Agendas", description="", sort_order=0
        )
        manage_page = admin_client.get("/administration/manage")
        csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', manage_page.text)
        assert csrf
        resp = admin_client.post(
            f"/administration/manage/sections/{section.id}/documents",
            data={"display_name": "Malware", "csrf_token": csrf.group(1)},
            files={"file": ("evil.exe", b"MZ", "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_delete_document(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        section = repository.create_administration_section(
            test_db, slug="agendas", title="Agendas", description="", sort_order=0
        )
        doc = repository.create_administration_document(
            test_db,
            section_id=section.id,
            display_name="Old Doc",
            filename="old.pdf",
            file_type="PDF",
            sort_order=0,
        )
        manage_page = admin_client.get("/administration/manage")
        csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', manage_page.text)
        assert csrf
        resp = admin_client.post(
            f"/administration/manage/documents/{doc.id}/delete",
            data={"csrf_token": csrf.group(1)},
        )
        assert resp.status_code == 200
        sections = repository.list_administration_sections(test_db)
        section_docs = next(s for s in sections if s.slug == "agendas").documents
        assert not any(d.id == doc.id for d in section_docs)


class TestAdministrationGuides:
    """Tests for the 4 editable administration guide pages and their PDF export."""

    _GUIDE_SLUGS = [
        ("athlete-registration-guide", "Athlete Registration Guide"),
        ("race-directors-guide", "Race Directors Guide"),
        ("suppliers-list", "Suppliers List"),
        ("team-managers-guide", "Team Managers Guide"),
    ]

    def test_public_can_view_all_guides(self, test_client: TestClient) -> None:
        for slug, title in self._GUIDE_SLUGS:
            resp = test_client.get(f"/administration/{slug}")
            assert resp.status_code == 200, f"Failed to load /administration/{slug}"
            assert title in resp.text
            assert f"/administration/{slug}/export/pdf" in resp.text
            assert "Export PDF" in resp.text
            # Anonymous user should not see Edit button
            assert f"/administration/{slug}/edit" not in resp.text

    def test_edit_button_visible_to_admin_and_content_creator(
        self, admin_client: TestClient, content_creator_client: TestClient
    ) -> None:
        for slug, _ in self._GUIDE_SLUGS:
            resp_admin = admin_client.get(f"/administration/{slug}")
            assert resp_admin.status_code == 200
            assert f"/administration/{slug}/edit" in resp_admin.text

            resp_creator = content_creator_client.get(f"/administration/{slug}")
            assert resp_creator.status_code == 200
            assert f"/administration/{slug}/edit" in resp_creator.text

    def test_edit_form_requires_auth(self, test_client: TestClient) -> None:
        for slug, _ in self._GUIDE_SLUGS:
            resp = test_client.get(
                f"/administration/{slug}/edit", follow_redirects=False
            )
            assert resp.status_code in (302, 403)

    def test_edit_form_loads_for_admin(self, admin_client: TestClient) -> None:
        for slug, title in self._GUIDE_SLUGS:
            resp = admin_client.get(f"/administration/{slug}/edit")
            assert resp.status_code == 200
            assert f"Edit {title}" in resp.text
            assert f'action="/administration/{slug}/edit"' in resp.text

    def test_edit_guide_submit(
        self,
        admin_client: TestClient,
        test_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        slug = "athlete-registration-guide"
        form_page = admin_client.get(f"/administration/{slug}/edit")
        csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', form_page.text)
        assert csrf is not None
        new_content = (
            "<h2>Updated Athlete Registration Guide</h2>"
            "<p>Step-by-step instructions.</p>"
        )
        post_resp = admin_client.post(
            f"/administration/{slug}/edit",
            data={"csrf_token": csrf.group(1), "content": new_content},
            follow_redirects=False,
        )
        assert post_resp.status_code == 303
        assert post_resp.headers["location"] == f"/administration/{slug}"

        # Public view reflects updated content
        view_resp = test_client.get(f"/administration/{slug}")
        assert "Updated Athlete Registration Guide" in view_resp.text
        assert "Step-by-step instructions." in view_resp.text

        # Database reflects updated content
        page = repository.get_static_page(test_db, slug)
        assert page is not None
        assert "Updated Athlete Registration Guide" in page.content

    def test_export_pdf_returns_valid_pdf(self, test_client: TestClient) -> None:
        for slug, _ in self._GUIDE_SLUGS:
            resp = test_client.get(f"/administration/{slug}/export/pdf")
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/pdf"
            assert f"filename={slug}.pdf" in resp.headers.get("content-disposition", "")
            assert resp.content.startswith(b"%PDF")

    def test_unknown_guide_slug_returns_404(
        self, test_client: TestClient, admin_client: TestClient
    ) -> None:
        assert test_client.get("/administration/unknown-guide").status_code == 404
        assert admin_client.get("/administration/unknown-guide/edit").status_code == 404
        assert (
            test_client.get("/administration/unknown-guide/export/pdf").status_code
            == 404
        )


class TestNewsCrud:
    def test_news_page_accessible_to_public(self, test_client: TestClient) -> None:
        assert test_client.get("/news").status_code == 200

    def test_create_form_requires_auth(self, test_client: TestClient) -> None:
        response = test_client.get("/news/create", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"].startswith("/login")

    def test_create_form_available_to_content_creator(
        self, content_creator_client: TestClient
    ) -> None:
        assert content_creator_client.get("/news/create").status_code == 200

    def test_create_form_available_to_admin(self, admin_client: TestClient) -> None:
        assert admin_client.get("/news/create").status_code == 200

    def test_create_post_and_appears_on_news(
        self, content_creator_client: TestClient
    ) -> None:
        create_page = content_creator_client.get("/news/create")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', create_page.text)
        assert match
        resp = content_creator_client.post(
            "/news/create",
            data={
                "title": "Test Post",
                "content": "<p>Hello world</p>",
                "csrf_token": match.group(1),
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "Test Post" in resp.text

    def test_short_post_has_no_see_more_link(
        self, content_creator_client: TestClient
    ) -> None:
        create_page = content_creator_client.get("/news/create")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', create_page.text)
        assert match
        resp = content_creator_client.post(
            "/news/create",
            data={
                "title": "Short Summary Post",
                "content": "<p>A short announcement that easily fits in summary.</p>",
                "csrf_token": match.group(1),
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "Short Summary Post" in resp.text
        assert "see more" not in resp.text

    def test_long_post_has_see_more_link_navigating_to_full_post(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        create_page = content_creator_client.get("/news/create")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', create_page.text)
        assert match
        long_content = (
            "<p>Welcome to the new season of the cross country league. "
            + "We have many exciting fixtures scheduled across various venues. " * 10
            + "</p>"
        )
        content_creator_client.post(
            "/news/create",
            data={
                "title": "Long Fixture Announcement",
                "content": long_content,
                "csrf_token": match.group(1),
            },
            follow_redirects=True,
        )
        row = test_db.execute(
            "SELECT id FROM posts WHERE title = ?", ["Long Fixture Announcement"]
        ).fetchone()
        assert row is not None
        post_id = row[0]

        news_page = content_creator_client.get("/news")
        assert news_page.status_code == 200
        assert f'href="/news/{post_id}"' in news_page.text
        assert "see more</a>" in news_page.text

        detail_page = content_creator_client.get(f"/news/{post_id}")
        assert detail_page.status_code == 200
        assert "Long Fixture Announcement" in detail_page.text
        assert "scheduled across various venues" in detail_page.text

    def test_delete_post(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        create_page = content_creator_client.get("/news/create")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', create_page.text)
        assert match
        content_creator_client.post(
            "/news/create",
            data={
                "title": "To Delete",
                "content": "<p>bye</p>",
                "csrf_token": match.group(1),
            },
        )
        posts = test_db.execute(
            "SELECT id FROM posts WHERE title = ?", ["To Delete"]
        ).fetchall()
        assert len(posts) == 1
        post_id = posts[0][0]

        csrf_resp = content_creator_client.get("/news")
        csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', csrf_resp.text)
        assert csrf_match
        del_resp = content_creator_client.post(
            f"/news/{post_id}/delete",
            data={"csrf_token": csrf_match.group(1)},
            follow_redirects=True,
        )
        assert del_resp.status_code == 200
        remaining = test_db.execute(
            "SELECT id FROM posts WHERE title = ?", ["To Delete"]
        ).fetchall()
        assert remaining == []

    def test_other_user_cannot_edit_post(
        self,
        test_db: duckdb.DuckDBPyConnection,
        content_creator_client: TestClient,
        admin_client: TestClient,
    ) -> None:
        """A content_creator cannot edit a post authored by a different user."""
        # Admin creates a post
        create_page = admin_client.get("/news/create")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', create_page.text)
        assert match
        admin_client.post(
            "/news/create",
            data={
                "title": "Admin Post",
                "content": "<p>by admin</p>",
                "csrf_token": match.group(1),
            },
        )
        row = test_db.execute(
            "SELECT id FROM posts WHERE title = ?", ["Admin Post"]
        ).fetchone()
        assert row
        post_id = row[0]

        resp = content_creator_client.get(f"/news/{post_id}/edit")
        assert resp.status_code == 403


class TestNewsPagination:
    def test_page_query_param_accepted(self, test_client: TestClient) -> None:
        resp = test_client.get("/news?page=1")
        assert resp.status_code == 200

    def test_out_of_range_page_returns_200(self, test_client: TestClient) -> None:
        resp = test_client.get("/news?page=999")
        assert resp.status_code == 200

    def test_page_zero_clamped_to_one(self, test_client: TestClient) -> None:
        resp = test_client.get("/news?page=0")
        assert resp.status_code == 200


class TestAccountPage:
    def test_account_redirects_when_unauthenticated(
        self, test_client: TestClient
    ) -> None:
        response = test_client.get("/account", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"].startswith("/login")

    def test_account_accessible_when_logged_in_as_admin(
        self, admin_client: TestClient
    ) -> None:
        assert admin_client.get("/account").status_code == 200

    def test_account_accessible_when_logged_in_as_content_creator(
        self, content_creator_client: TestClient
    ) -> None:
        assert content_creator_client.get("/account").status_code == 200

    def test_account_shows_username(self, admin_client: TestClient) -> None:
        response = admin_client.get("/account")
        assert response.status_code == 200
        assert "My Account" in response.text

    def test_account_shows_admin_role_badge(self, admin_client: TestClient) -> None:
        response = admin_client.get("/account")
        assert "Admin" in response.text

    def test_account_shows_content_creator_role_badge(
        self, content_creator_client: TestClient
    ) -> None:
        response = content_creator_client.get("/account")
        assert "Content Creator" in response.text


# ---------------------------------------------------------------------------
# Fixtures routes
# ---------------------------------------------------------------------------


class TestFixturesPublicPage:
    def test_fixtures_page_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/fixtures").status_code == 200

    def test_fixtures_page_no_login_required(self, test_client: TestClient) -> None:
        assert test_client.get("/fixtures").status_code == 200

    def test_fixtures_page_with_unknown_season_id(
        self, test_client: TestClient
    ) -> None:
        response = test_client.get("/fixtures?season_id=9999")
        assert response.status_code == 200

    def test_season_panel_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/fixtures/season-panel").status_code == 200

    def test_fixture_detail_unknown_id_returns_404(
        self, test_client: TestClient
    ) -> None:
        response = test_client.get(
            "/fixtures/fixture-detail?fixture_id=9999", follow_redirects=False
        )
        assert response.status_code == 404


class TestFixturesSeasonCrud:
    def _get_csrf(self, client: TestClient) -> str:
        resp = client.get("/fixtures")
        import re

        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match, "No CSRF token found"
        return match.group(1)

    def test_create_season_requires_auth(self, test_client: TestClient) -> None:
        response = test_client.post(
            "/fixtures/seasons",
            data={"name": "2025-2026", "csrf_token": "fake"},
            follow_redirects=False,
        )
        assert response.status_code in (302, 403)
        if response.status_code == 302:
            assert response.headers["location"].startswith("/login")

    def test_create_season_as_admin(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            "/fixtures/seasons",
            data={"name": "2025-2026", "csrf_token": csrf},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        row = test_db.execute(
            "SELECT name FROM seasons WHERE name = ?", ["2025-2026"]
        ).fetchone()
        assert row is not None

    def test_create_season_as_content_creator(
        self,
        content_creator_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        csrf = self._get_csrf(content_creator_client)
        resp = content_creator_client.post(
            "/fixtures/seasons",
            data={"name": "2024-2025", "csrf_token": csrf},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        row = test_db.execute(
            "SELECT name FROM seasons WHERE name = ?", ["2024-2025"]
        ).fetchone()
        assert row is not None

    def test_delete_season_with_no_fixtures(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "2099-2100")
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            f"/fixtures/seasons/{season.id}/delete",
            data={"csrf_token": csrf},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert repository.get_season_by_id(test_db, season.id) is None

    def test_delete_season_with_fixtures_returns_409(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "2088-2089")
        repository.create_fixture(
            test_db, season.id, "R1", "2088-09-01", "V", "A", [], ""
        )
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            f"/fixtures/seasons/{season.id}/delete",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 409


class TestFixturesFixtureCrud:
    import json as _json

    def _get_csrf(self, client: TestClient) -> str:
        import re

        resp = client.get("/fixtures")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match
        return match.group(1)

    def test_create_fixture_as_admin(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        import json
        from website import repository

        season = repository.create_season(test_db, "2025-2026")
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            f"/fixtures/seasons/{season.id}/fixtures",
            data={
                "title": "Round 1",
                "date": "2025-09-01",
                "location_name": "Town Hall",
                "address": "1 Main St",
                "timetable_json": json.dumps([{"event": "Start", "time": "09:00"}]),
                "travel_instructions": "Take the train.",
                "csrf_token": csrf,
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        fixtures = repository.list_fixtures_for_season(test_db, season.id)
        assert len(fixtures) == 1
        assert fixtures[0].title == "Round 1"

    def test_create_sixth_fixture_returns_409(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "2030-2031")
        for i in range(5):
            repository.create_fixture(
                test_db,
                season.id,
                f"Round {i + 1}",
                f"2030-0{i + 1}-01",
                "V",
                "A",
                [],
                "",
            )
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            f"/fixtures/seasons/{season.id}/fixtures",
            data={
                "title": "Round 6",
                "date": "2030-07-01",
                "location_name": "V",
                "address": "A",
                "timetable_json": "[]",
                "travel_instructions": "",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 409

    def test_delete_fixture(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "2031-2032")
        fixture = repository.create_fixture(
            test_db, season.id, "R1", "2031-09-01", "V", "A", [], ""
        )
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            f"/fixtures/seasons/{season.id}/fixtures/{fixture.id}/delete",
            data={"csrf_token": csrf},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert repository.get_fixture_by_id(test_db, fixture.id) is None

    def test_create_fixture_requires_auth(self, test_client: TestClient) -> None:
        resp = test_client.post(
            "/fixtures/seasons/1/fixtures",
            data={
                "title": "R",
                "date": "2025-01-01",
                "location_name": "V",
                "address": "A",
                "timetable_json": "[]",
                "travel_instructions": "",
                "csrf_token": "fake",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403)
        if resp.status_code == 302:
            assert resp.headers["location"].startswith("/login")

    def test_new_season_form_requires_auth(self, test_client: TestClient) -> None:
        resp = test_client.get("/fixtures/seasons/new", follow_redirects=False)
        assert resp.status_code in (302, 403)
        if resp.status_code == 302:
            assert resp.headers["location"].startswith("/login")


class TestFixturesCopy:
    def _get_csrf(self, client: TestClient) -> str:
        import re

        resp = client.get("/fixtures")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match
        return match.group(1)

    def test_copy_form_requires_auth(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "Copy-Auth-Season")
        fixture = repository.create_fixture(
            test_db, season.id, "R1", "2025-01-01", "V", "A", [], ""
        )
        resp = test_client.get(
            f"/fixtures/seasons/{season.id}/fixtures/{fixture.id}/copy",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403)
        if resp.status_code == 302:
            assert resp.headers["location"].startswith("/login")

    def test_copy_form_loads_as_admin(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        from website import repository
        from website.models import TimetableEntry

        season = repository.create_season(test_db, "Copy-Form-Season")
        fixture = repository.create_fixture(
            test_db,
            season.id,
            "Source Fixture",
            "2025-06-01",
            "Town Hall",
            "1 Main St",
            [TimetableEntry(event="Start", time="09:00")],
            "Take the bus.",
        )
        resp = admin_client.get(
            f"/fixtures/seasons/{season.id}/fixtures/{fixture.id}/copy",
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "Copy Fixture" in resp.text
        assert "Source Fixture" in resp.text
        assert "Save Copy" in resp.text

    def test_copy_form_returns_404_for_missing_fixture(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "Copy-404-Season")
        resp = admin_client.get(
            f"/fixtures/seasons/{season.id}/fixtures/99999/copy",
            follow_redirects=False,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Login/logout
# ---------------------------------------------------------------------------


class TestLoginPageAlreadyAuthenticated:
    def test_redirects_to_news_when_logged_in(self, admin_client: TestClient) -> None:
        resp = admin_client.get("/login", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/news"


class TestLoginBadCredentials:
    def test_invalid_password_returns_401(self, test_client: TestClient) -> None:
        login_page = test_client.get("/login")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
        assert match
        resp = test_client.post(
            "/login",
            data={
                "username": "nonexistent",
                "password": "wrongpass",
                "csrf_token": match.group(1),
            },
        )
        assert resp.status_code == 401
        assert "Invalid username or password" in resp.text


class TestLogout:
    def test_logout_redirects_to_news(self, admin_client: TestClient) -> None:
        news_page = admin_client.get("/news")
        csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', news_page.text)
        assert csrf_match
        resp = admin_client.post(
            "/logout",
            data={"csrf_token": csrf_match.group(1)},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/news"

    def test_logout_clears_session(self, admin_client: TestClient) -> None:
        news_page = admin_client.get("/news")
        csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', news_page.text)
        assert csrf_match
        admin_client.post(
            "/logout",
            data={"csrf_token": csrf_match.group(1)},
            follow_redirects=True,
        )
        # After logout, account page should redirect to login
        resp = admin_client.get("/account", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


# ---------------------------------------------------------------------------
# Privacy policy
# ---------------------------------------------------------------------------


class TestPrivacyPolicyRoute:
    def test_privacy_policy_page_loads(self, test_client: TestClient) -> None:
        resp = test_client.get("/privacy-policy")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_privacy_policy_contains_privacy_content(
        self, test_client: TestClient
    ) -> None:
        resp = test_client.get("/privacy-policy")
        assert resp.status_code == 200


class TestContactRoute:
    def test_contact_page_loads(self, test_client: TestClient) -> None:
        resp = test_client.get("/contact")
        assert resp.status_code == 200
        assert "Contact Us" in resp.text
        assert "committee@oxonxc.org.uk" in resp.text


class TestAboutRoute:
    def test_about_page_loads(self, test_client: TestClient) -> None:
        resp = test_client.get("/about")
        assert resp.status_code == 200
        assert "About Us" in resp.text
        assert "Work in progress" in resp.text


# ---------------------------------------------------------------------------
# Dismiss cookie notice
# ---------------------------------------------------------------------------


class TestDismissCookieNotice:
    def test_dismiss_sets_cookie(self, test_client: TestClient) -> None:
        news_page = test_client.get("/news")
        csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', news_page.text)
        assert csrf_match
        resp = test_client.post(
            "/dismiss-cookie-notice",
            data={"csrf_token": csrf_match.group(1)},
            follow_redirects=False,
            headers={"Referer": "http://testserver/news"},
        )
        assert resp.status_code == 302
        assert "cookie_notice_dismissed" in resp.headers.get("set-cookie", "")

    def test_dismiss_redirects_to_referer_path(self, test_client: TestClient) -> None:
        news_page = test_client.get("/news")
        csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', news_page.text)
        assert csrf_match
        resp = test_client.post(
            "/dismiss-cookie-notice",
            data={"csrf_token": csrf_match.group(1)},
            follow_redirects=False,
            headers={"Referer": "http://testserver/fixtures"},
        )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/fixtures"


# ---------------------------------------------------------------------------
# News detail / edit
# ---------------------------------------------------------------------------


class TestNewsDetailRoute:
    def test_news_detail_loads_for_existing_post(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:

        create_page = content_creator_client.get("/news/create")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', create_page.text)
        assert match
        content_creator_client.post(
            "/news/create",
            data={
                "title": "Detail Test Post",
                "content": "<p>Detail content</p>",
                "csrf_token": match.group(1),
            },
        )
        row = test_db.execute(
            "SELECT id FROM posts WHERE title = ?", ["Detail Test Post"]
        ).fetchone()
        assert row
        post_id = row[0]

        resp = content_creator_client.get(f"/news/{post_id}")
        assert resp.status_code == 200
        assert "Detail Test Post" in resp.text

    def test_news_detail_returns_404_for_missing_post(
        self, test_client: TestClient
    ) -> None:
        resp = test_client.get("/news/99999")
        assert resp.status_code == 404


class TestNewsEditRoute:
    def test_edit_form_loads_for_post_author(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        create_page = content_creator_client.get("/news/create")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', create_page.text)
        assert match
        content_creator_client.post(
            "/news/create",
            data={
                "title": "Edit Me",
                "content": "<p>Original</p>",
                "csrf_token": match.group(1),
            },
        )
        row = test_db.execute(
            "SELECT id FROM posts WHERE title = ?", ["Edit Me"]
        ).fetchone()
        assert row
        post_id = row[0]

        resp = content_creator_client.get(f"/news/{post_id}/edit")
        assert resp.status_code == 200
        assert "Edit Me" in resp.text

    def test_edit_submit_updates_post(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        create_page = content_creator_client.get("/news/create")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', create_page.text)
        assert match
        content_creator_client.post(
            "/news/create",
            data={
                "title": "Before Edit",
                "content": "<p>before</p>",
                "csrf_token": match.group(1),
            },
        )
        row = test_db.execute(
            "SELECT id FROM posts WHERE title = ?", ["Before Edit"]
        ).fetchone()
        assert row
        post_id = row[0]

        edit_page = content_creator_client.get(f"/news/{post_id}/edit")
        csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', edit_page.text)
        assert csrf_match
        resp = content_creator_client.post(
            f"/news/{post_id}/edit",
            data={
                "title": "After Edit",
                "content": "<p>after</p>",
                "csrf_token": csrf_match.group(1),
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        updated = test_db.execute(
            "SELECT title FROM posts WHERE id = ?", [post_id]
        ).fetchone()
        assert updated
        assert updated[0] == "After Edit"


# ---------------------------------------------------------------------------
# Fixtures: season panel with data, fixture detail with data
# ---------------------------------------------------------------------------


class TestFixturesSeasonPanelWithData:
    def test_season_panel_with_seasons_auto_selects_first(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "SPanel-Season-2025")
        repository.create_fixture(
            test_db, season.id, "Round 1", "2025-09-01", "Venue", "Addr", [], ""
        )
        resp = test_client.get("/fixtures/season-panel")
        assert resp.status_code == 200

    def test_season_panel_with_fixture_loads_images(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "SPanel-Imgs-2025")
        fixture = repository.create_fixture(
            test_db, season.id, "Round 1", "2025-10-01", "Venue", "Addr", [], ""
        )
        repository.create_fixture_image(test_db, fixture.id, "photo.jpg")
        resp = test_client.get(f"/fixtures/season-panel?season_id={season.id}")
        assert resp.status_code == 200


class TestFixtureDetailWithData:
    def test_fixture_detail_returns_200_for_existing_fixture(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "FDetail-Season")
        fixture = repository.create_fixture(
            test_db, season.id, "Round 1", "2025-09-01", "Venue", "Addr", [], ""
        )
        resp = test_client.get(
            f"/fixtures/fixture-detail?fixture_id={fixture.id}&season_id={season.id}"
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Fixtures: course map image alt text
# ---------------------------------------------------------------------------


class TestFixtureImageAltText:
    """Course map images include auto-generated alt text from fixture and season names."""

    def test_fixture_detail_image_has_correct_alt_text(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "Alt Text Season 2025")
        fixture = repository.create_fixture(
            test_db, season.id, "Round 1 Alt", "2025-09-01", "Venue", "Addr", [], ""
        )
        repository.create_fixture_image(test_db, fixture.id, "photo.jpg")
        resp = test_client.get(
            f"/fixtures/fixture-detail?fixture_id={fixture.id}&season_id={season.id}"
        )
        assert resp.status_code == 200
        assert "Course map for Round 1 Alt, Alt Text Season 2025" in resp.text

    def test_season_panel_image_has_correct_alt_text(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "Alt Panel Season 2025")
        fixture = repository.create_fixture(
            test_db, season.id, "Round 2 Alt", "2025-10-01", "Venue", "Addr", [], ""
        )
        repository.create_fixture_image(test_db, fixture.id, "photo2.jpg")
        resp = test_client.get(f"/fixtures/season-panel?season_id={season.id}")
        assert resp.status_code == 200
        assert "Course map for Round 2 Alt, Alt Panel Season 2025" in resp.text

    def test_fixtures_page_image_has_correct_alt_text(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "Alt Fixtures Season 2025")
        fixture = repository.create_fixture(
            test_db, season.id, "Round 3 Alt", "2025-11-01", "Venue", "Addr", [], ""
        )
        repository.create_fixture_image(test_db, fixture.id, "photo3.jpg")
        resp = test_client.get(f"/fixtures?season_id={season.id}")
        assert resp.status_code == 200
        assert "Course map for Round 3 Alt, Alt Fixtures Season 2025" in resp.text

    def test_upload_response_has_correct_alt_text(
        self,
        content_creator_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        tmp_path,  # noqa: ANN001
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "Upload Alt Season")
        fixture = repository.create_fixture(
            test_db, season.id, "Upload Round", "2025-09-01", "Venue", "Addr", [], ""
        )
        page = content_creator_client.get("/fixtures")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', page.text)
        assert match
        csrf_token = match.group(1)

        # Redirect file writes to a temporary directory to avoid polluting data/
        app.dependency_overrides[get_image_store] = lambda: FileStore(
            tmp_path, IMAGE_POLICY
        )
        try:
            resp = content_creator_client.post(
                f"/fixtures/seasons/{season.id}/fixtures/{fixture.id}/images",
                files={"file": ("map.jpg", b"\xff\xd8\xff\xe0", "image/jpeg")},
                data={"csrf_token": csrf_token},
            )
        finally:
            app.dependency_overrides.pop(get_image_store)

        assert resp.status_code == 200
        assert "Course map for Upload Round, Upload Alt Season" in resp.text

    def test_delete_response_remaining_images_have_correct_alt_text(
        self,
        content_creator_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        tmp_path,  # noqa: ANN001
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "Delete Alt Season")
        fixture = repository.create_fixture(
            test_db, season.id, "Delete Round", "2025-09-01", "Venue", "Addr", [], ""
        )
        img1 = repository.create_fixture_image(test_db, fixture.id, "photo_a.jpg")
        repository.create_fixture_image(test_db, fixture.id, "photo_b.jpg")

        page = content_creator_client.get("/fixtures")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', page.text)
        assert match
        csrf_token = match.group(1)

        app.dependency_overrides[get_image_store] = lambda: FileStore(
            tmp_path, IMAGE_POLICY
        )
        try:
            resp = content_creator_client.post(
                f"/fixtures/seasons/{season.id}/fixtures/{fixture.id}/images/{img1.id}/delete",
                data={"csrf_token": csrf_token},
            )
        finally:
            app.dependency_overrides.pop(get_image_store)

        assert resp.status_code == 200
        assert "Course map for Delete Round, Delete Alt Season" in resp.text


# ---------------------------------------------------------------------------
# Fixtures: new season form and cancel
# ---------------------------------------------------------------------------


class TestFixturesNewSeasonForm:
    def test_new_season_form_loads_as_admin(self, admin_client: TestClient) -> None:
        resp = admin_client.get("/fixtures/seasons/new")
        assert resp.status_code == 200

    def test_new_season_form_requires_auth(self, test_client: TestClient) -> None:
        resp = test_client.get("/fixtures/seasons/new", follow_redirects=False)
        assert resp.status_code in (302, 403)


class TestFixturesNewSeasonFormCancel:
    def test_cancel_returns_empty_fragment(self, test_client: TestClient) -> None:
        resp = test_client.get("/fixtures/seasons/new-form-cancel")
        assert resp.status_code == 200
        assert resp.text.strip() == ""


# ---------------------------------------------------------------------------
# Fixtures: new fixture form
# ---------------------------------------------------------------------------


class TestFixturesNewFixtureForm:
    def _get_csrf(self, client: TestClient) -> str:
        resp = client.get("/fixtures")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match
        return match.group(1)

    def test_new_fixture_form_loads_for_valid_season(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "NewFix-Form-Season")
        resp = admin_client.get(f"/fixtures/seasons/{season.id}/fixtures/new")
        assert resp.status_code == 200

    def test_new_fixture_form_returns_404_for_missing_season(
        self, admin_client: TestClient
    ) -> None:
        resp = admin_client.get(
            "/fixtures/seasons/99999/fixtures/new", follow_redirects=False
        )
        assert resp.status_code == 404

    def test_new_fixture_form_returns_409_when_season_full(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "Full-Season-NewFix")
        for i in range(5):
            repository.create_fixture(
                test_db,
                season.id,
                f"Round {i + 1}",
                f"2025-0{i + 1}-01",
                "V",
                "A",
                [],
                "",
            )
        resp = admin_client.get(
            f"/fixtures/seasons/{season.id}/fixtures/new", follow_redirects=False
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Fixtures: edit form and update
# ---------------------------------------------------------------------------


class TestFixturesEditForm:
    def test_edit_form_loads_for_existing_fixture(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "EditForm-Season")
        fixture = repository.create_fixture(
            test_db, season.id, "Round 1", "2025-09-01", "Venue", "Addr", [], ""
        )
        resp = admin_client.get(
            f"/fixtures/seasons/{season.id}/fixtures/{fixture.id}/edit"
        )
        assert resp.status_code == 200
        assert "Round 1" in resp.text

    def test_edit_form_returns_404_for_missing_season(
        self, admin_client: TestClient
    ) -> None:
        resp = admin_client.get(
            "/fixtures/seasons/99999/fixtures/1/edit", follow_redirects=False
        )
        assert resp.status_code == 404

    def test_edit_form_returns_404_for_missing_fixture(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        from website import repository

        season = repository.create_season(test_db, "EditForm-NoFix-Season")
        resp = admin_client.get(
            f"/fixtures/seasons/{season.id}/fixtures/99999/edit",
            follow_redirects=False,
        )
        assert resp.status_code == 404


class TestFixturesUpdateFixture:
    def _get_csrf(self, client: TestClient) -> str:
        resp = client.get("/fixtures")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match
        return match.group(1)

    def test_update_fixture_changes_title(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        import json
        from website import repository

        season = repository.create_season(test_db, "Update-Fixture-Season")
        fixture = repository.create_fixture(
            test_db, season.id, "Old Title", "2025-09-01", "Venue", "Addr", [], ""
        )
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            f"/fixtures/seasons/{season.id}/fixtures/{fixture.id}/edit",
            data={
                "title": "New Title",
                "date": "2025-10-01",
                "location_name": "New Venue",
                "address": "New Addr",
                "timetable_json": json.dumps([]),
                "travel_instructions": "",
                "csrf_token": csrf,
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        updated = repository.get_fixture_by_id(test_db, fixture.id)
        assert updated is not None
        assert updated.title == "New Title"

    def test_update_fixture_returns_404_for_missing_fixture(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        import json
        from website import repository

        season = repository.create_season(test_db, "Update-Missing-Season")
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            f"/fixtures/seasons/{season.id}/fixtures/99999/edit",
            data={
                "title": "Whatever",
                "date": "2025-10-01",
                "location_name": "V",
                "address": "A",
                "timetable_json": json.dumps([]),
                "travel_instructions": "",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 404

    def test_update_fixture_requires_auth(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        import json
        from website import repository

        season = repository.create_season(test_db, "Update-Auth-Season")
        fixture = repository.create_fixture(
            test_db, season.id, "R1", "2025-09-01", "V", "A", [], ""
        )
        resp = test_client.post(
            f"/fixtures/seasons/{season.id}/fixtures/{fixture.id}/edit",
            data={
                "title": "Hacked",
                "date": "2025-10-01",
                "location_name": "V",
                "address": "A",
                "timetable_json": json.dumps([]),
                "travel_instructions": "",
                "csrf_token": "fake",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403)

    def test_copy_submit_creates_fixture_in_target_season(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        import json
        from website import repository

        source_season = repository.create_season(test_db, "Copy-Src-Season")
        target_season = repository.create_season(test_db, "Copy-Tgt-Season")
        from website.models import TimetableEntry

        fixture = repository.create_fixture(
            test_db,
            source_season.id,
            "Original",
            "2025-06-01",
            "Town Hall",
            "1 Main St",
            [TimetableEntry(event="Open", time="10:00")],
            "Bus route 42.",
        )
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            "/fixtures/copy",
            data={
                "season_id": str(target_season.id),
                "title": "Copy of Original",
                "date": "2026-06-01",
                "location_name": "Town Hall",
                "address": "1 Main St",
                "timetable_json": json.dumps([{"event": "Open", "time": "10:00"}]),
                "travel_instructions": "Bus route 42.",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        target_fixtures = repository.list_fixtures_for_season(test_db, target_season.id)
        assert len(target_fixtures) == 1
        assert target_fixtures[0].title == "Copy of Original"
        # source season unchanged
        assert len(repository.list_fixtures_for_season(test_db, source_season.id)) == 1
        assert (
            repository.list_fixtures_for_season(test_db, source_season.id)[0].id
            == fixture.id
        )

    def test_copy_submit_to_full_season_returns_409(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        from website import repository

        source_season = repository.create_season(test_db, "Copy-Full-Src")
        target_season = repository.create_season(test_db, "Copy-Full-Tgt")
        repository.create_fixture(
            test_db, source_season.id, "R0", "2025-01-01", "V", "A", [], ""
        )
        for i in range(5):
            repository.create_fixture(
                test_db,
                target_season.id,
                f"R{i + 1}",
                f"2025-0{i + 1}-01",
                "V",
                "A",
                [],
                "",
            )
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            "/fixtures/copy",
            data={
                "season_id": str(target_season.id),
                "title": "Overflow",
                "date": "2025-07-01",
                "location_name": "V",
                "address": "A",
                "timetable_json": "[]",
                "travel_instructions": "",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 409

    def test_copy_submit_requires_auth(self, test_client: TestClient) -> None:
        resp = test_client.post(
            "/fixtures/copy",
            data={
                "season_id": "1",
                "title": "T",
                "date": "2025-01-01",
                "location_name": "V",
                "address": "A",
                "timetable_json": "[]",
                "travel_instructions": "",
                "csrf_token": "fake",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403)
        if resp.status_code == 302:
            assert resp.headers["location"].startswith("/login")


# ---------------------------------------------------------------------------
# Content Creator Extended Permissions (Rules, Administration, Standings, Admin Data)
# ---------------------------------------------------------------------------


class TestContentCreatorExtendedPermissions:
    def _get_csrf(
        self, client: TestClient, path: str = "/rules-and-constitution"
    ) -> str:
        resp = client.get(path)
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match, f"CSRF token not found on {path}"
        return match.group(1)

    def test_rules_and_constitution_edit_accessible_to_content_creator(
        self, content_creator_client: TestClient
    ) -> None:
        resp = content_creator_client.get("/rules-and-constitution/edit")
        assert resp.status_code == 200
        assert "Rules and Constitution" in resp.text

    def test_rules_and_constitution_edit_submit_by_content_creator(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        csrf = self._get_csrf(content_creator_client, "/rules-and-constitution/edit")
        resp = content_creator_client.post(
            "/rules-and-constitution/edit",
            data={
                "csrf_token": csrf,
                "content": "<h2>Updated Rules</h2><p>New text</p>",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        page = repository.get_static_page(test_db, "rules-and-constitution")
        assert page is not None
        assert "Updated Rules" in page.content

    def test_administration_manage_by_content_creator(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        resp = content_creator_client.get("/administration/manage")
        assert resp.status_code == 200
        csrf = self._get_csrf(content_creator_client, "/administration/manage")
        create_resp = content_creator_client.post(
            "/administration/manage/sections",
            data={
                "title": "Creator Section",
                "slug": "creator-section",
                "description": "Added by creator",
                "csrf_token": csrf,
            },
        )
        assert create_resp.status_code == 200
        sections = repository.list_administration_sections(test_db)
        assert any(s.slug == "creator-section" for s in sections)

    def test_standings_recalculate_by_content_creator(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        season = repository.create_season(test_db, "Standings-Recalc-Season")
        resp = content_creator_client.get(f"/standings?season_id={season.id}")
        assert resp.status_code == 200
        assert "Calculate standings" in resp.text

        csrf = self._get_csrf(
            content_creator_client, f"/standings?season_id={season.id}"
        )
        post_resp = content_creator_client.post(
            "/standings/recalculate",
            data={"season_id": str(season.id), "csrf_token": csrf},
            follow_redirects=False,
        )
        assert post_resp.status_code == 303
        assert post_resp.headers["location"] == f"/standings?season_id={season.id}"

    def test_clubs_management_by_content_creator(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        resp = content_creator_client.get("/admin/clubs")
        assert resp.status_code == 200
        csrf = self._get_csrf(content_creator_client, "/admin/clubs/new")
        create_resp = content_creator_client.post(
            "/admin/clubs",
            data={
                "name": "Creator Harriers",
                "oxl_code": "CRTR",
                "ea_club_id": "99991",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert create_resp.status_code == 303
        clubs = repository.list_clubs(test_db)
        assert any(c.oxl_code == "CRTR" and c.name == "Creator Harriers" for c in clubs)

    def test_links_management_by_content_creator(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        resp = content_creator_client.get("/admin/links")
        assert resp.status_code == 200
        csrf = self._get_csrf(content_creator_client, "/admin/links/new")
        create_resp = content_creator_client.post(
            "/admin/links",
            data={
                "title": "Creator Link",
                "url": "https://example.com/creator",
                "category": "national",
                "description": "Test link",
                "sort_order": "1",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert create_resp.status_code == 303
        links = repository.list_external_links(test_db)
        assert any(link.title == "Creator Link" for link in links)

    def test_divisions_management_by_content_creator(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        season = repository.create_season(test_db, "Div-Season")
        club = repository.create_club(test_db, "Div Club", "DVC", "12345")
        resp = content_creator_client.get("/admin/divisions")
        assert resp.status_code == 200
        csrf = self._get_csrf(content_creator_client, "/admin/divisions")
        create_resp = content_creator_client.post(
            "/admin/divisions",
            data={
                "season_id": str(season.id),
                "club_id": str(club.id),
                "gender": "men",
                "division": "1",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert create_resp.status_code == 303
        assignments = repository.list_division_assignments(test_db, season.id)
        assert len(assignments) == 1

    def test_winners_management_by_content_creator(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        season = repository.create_season(test_db, "Win-Season")
        resp = content_creator_client.get("/admin/winners")
        assert resp.status_code == 200
        csrf = self._get_csrf(content_creator_client, "/admin/winners")
        create_resp = content_creator_client.post(
            "/admin/winners",
            data={
                "season_id": str(season.id),
                "winner_type": "individual",
                "category": "Senior Men",
                "winner_name": "Fast Runner",
                "club": "Running Club",
                "total_score": "10",
                "note": "",
                "mode": "replace",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert create_resp.status_code == 303
        winners = repository.list_winner_overrides(test_db)
        assert any(w.winner_name == "Fast Runner" for w in winners)

    def test_club_managers_and_entries_still_forbidden_for_content_creator(
        self, content_creator_client: TestClient
    ) -> None:
        assert content_creator_client.get(
            "/admin/club-managers", follow_redirects=False
        ).status_code in (302, 403)
        assert content_creator_client.get(
            "/admin/entries", follow_redirects=False
        ).status_code in (302, 403)


# ---------------------------------------------------------------------------
# Website Content In-Page Editing & Navigation Tests (Divisions, Winners, Clubs, Links)
# ---------------------------------------------------------------------------


class TestWebsiteContentNavigation:
    def test_admin_sidebar_and_account_have_management_links(
        self, admin_client: TestClient
    ) -> None:
        resp = admin_client.get("/news")
        assert resp.status_code == 200
        assert "Website Content" in resp.text
        assert "/admin/clubs" in resp.text
        assert "/admin/divisions" in resp.text
        assert "/admin/winners" in resp.text
        assert "/admin/links" in resp.text
        assert "/administration/manage" in resp.text
        assert "/admin/club-managers" in resp.text
        assert "/admin/entries" in resp.text

        account_resp = admin_client.get("/account")
        assert account_resp.status_code == 200
        assert "Website Content Quick Links" in account_resp.text
        assert "Member Clubs" in account_resp.text

    def test_content_creator_sidebar_has_content_management_links(
        self, content_creator_client: TestClient
    ) -> None:
        resp = content_creator_client.get("/news")
        assert resp.status_code == 200
        assert "Website Content" in resp.text
        assert "/admin/clubs" in resp.text
        assert "/admin/divisions" in resp.text
        assert "/admin/winners" in resp.text
        assert "/admin/links" in resp.text
        assert "/administration/manage" in resp.text
        assert "/admin/club-managers" not in resp.text
        assert "/admin/entries" not in resp.text

    def test_anonymous_sidebar_lacks_website_content_management(
        self, test_client: TestClient
    ) -> None:
        anon_resp = test_client.get("/news")
        assert "Website Content" not in anon_resp.text
        assert "/admin/clubs" not in anon_resp.text

    def test_manager_sidebar_lacks_website_content_management(
        self, club_manager_client: TestClient
    ) -> None:
        mgr_resp = club_manager_client.get("/news")
        assert "Website Content" not in mgr_resp.text
        assert "/admin/clubs" not in mgr_resp.text

    def test_admin_pages_contain_view_public_page_links(
        self, admin_client: TestClient
    ) -> None:
        for path in (
            "/admin/clubs",
            "/admin/divisions",
            "/admin/winners",
            "/admin/links",
        ):
            resp = admin_client.get(path)
            assert resp.status_code == 200
            assert "View public page" in resp.text


class TestClubsInPageEditing:
    def _csrf(self, client: TestClient, path: str = "/clubs") -> str:
        resp = client.get(path)
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match, f"CSRF token not found on {path}"
        return match.group(1)

    def test_public_view_has_no_edit_controls(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        repository.create_club(test_db, "Public Club", "PUB", "123")
        resp = test_client.get("/clubs")
        assert resp.status_code == 200
        assert "Public Club" in resp.text
        assert "+ Add Club" not in resp.text
        assert 'hx-get="/clubs/' not in resp.text

    def test_inline_add_club_by_staff(
        self,
        content_creator_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        csrf = self._csrf(content_creator_client, "/clubs")
        resp = content_creator_client.post(
            "/clubs/inline-add",
            data={
                "name": "Inline Harriers",
                "oxl_code": "INL",
                "ea_club_id": "8888",
                "opentrack_code": "INLH",
                "website_url": "https://example.com/inl",
                "is_oxfordshire_member": "on",
                "csrf_token": csrf,
            },
        )
        assert resp.status_code == 200
        assert "Inline Harriers" in resp.text
        assert 'id="club-row-' in resp.text
        row = test_db.execute("SELECT id FROM clubs WHERE oxl_code='INL'").fetchone()
        assert row is not None
        club = repository.get_club_by_id(test_db, row[0])
        assert club is not None
        assert club.name == "Inline Harriers"

    def test_inline_edit_and_toggle_club(
        self,
        content_creator_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        club = repository.create_club(test_db, "Toggle Club", "TGL", "777")
        form_resp = content_creator_client.get(f"/clubs/{club.id}/inline-form")
        assert form_resp.status_code == 200
        assert "Edit Toggle Club" in form_resp.text

        row_resp = content_creator_client.get(f"/clubs/{club.id}/inline-row")
        assert row_resp.status_code == 200
        assert "Toggle Club" in row_resp.text

        csrf = self._csrf(content_creator_client, "/clubs")
        edit_resp = content_creator_client.post(
            f"/clubs/{club.id}/inline-edit",
            data={
                "name": "Updated Club Name",
                "oxl_code": "TGL",
                "ea_club_id": "777",
                "opentrack_code": "",
                "website_url": "",
                "is_oxfordshire_member": "off",
                "is_active": "on",
                "csrf_token": csrf,
            },
        )
        assert edit_resp.status_code == 200
        assert "Updated Club Name" in edit_resp.text

        toggle_resp = content_creator_client.post(
            f"/clubs/{club.id}/inline-toggle",
            data={"csrf_token": csrf},
        )
        assert toggle_resp.status_code == 200
        updated = repository.get_club_by_id(test_db, club.id)
        assert updated is not None
        assert updated.is_active is False

    def test_anonymous_club_inline_access_rejected(
        self,
        test_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        club = repository.create_club(test_db, "Auth Club", "ATH", "666")
        assert test_client.get(
            f"/clubs/{club.id}/inline-form", follow_redirects=False
        ).status_code in (302, 403)

    def test_club_manager_inline_access_rejected(
        self,
        club_manager_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        club = repository.create_club(test_db, "Auth Club 2", "ATH2", "667")
        assert club_manager_client.get(
            f"/clubs/{club.id}/inline-form", follow_redirects=False
        ).status_code in (302, 403)


class TestLinksInPageEditing:
    def _csrf(self, client: TestClient, path: str = "/links") -> str:
        resp = client.get(path)
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match, f"CSRF token not found on {path}"
        return match.group(1)

    def test_public_view_has_no_edit_controls(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        repository.create_external_link(
            test_db,
            "Public Org",
            "https://example.com/org",
            "national",
            "Desc",
            0,
        )
        resp = test_client.get("/links")
        assert resp.status_code == 200
        assert "Public Org" in resp.text
        assert "+ Add Link" not in resp.text
        assert 'hx-get="/links/' not in resp.text

    def test_inline_add_and_edit_and_delete_link(
        self,
        content_creator_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        csrf = self._csrf(content_creator_client, "/links")
        add_resp = content_creator_client.post(
            "/links/inline-add",
            data={
                "title": "Inline Link",
                "url": "https://example.com/inline",
                "category": "national",
                "description": "Added inline",
                "sort_order": "2",
                "is_active": "on",
                "csrf_token": csrf,
            },
        )
        assert add_resp.status_code == 200
        assert "Inline Link" in add_resp.text
        link = next(
            link
            for link in repository.list_external_links(test_db)
            if link.title == "Inline Link"
        )

        form_resp = content_creator_client.get(f"/links/{link.id}/inline-form")
        assert form_resp.status_code == 200
        assert "Edit Link" in form_resp.text

        edit_resp = content_creator_client.post(
            f"/links/{link.id}/inline-edit",
            data={
                "title": "Updated Link Title",
                "url": "https://example.com/updated",
                "category": "national",
                "description": "Updated desc",
                "sort_order": "3",
                "is_active": "on",
                "csrf_token": csrf,
            },
        )
        assert edit_resp.status_code == 200
        assert "Updated Link Title" in edit_resp.text

        toggle_resp = content_creator_client.post(
            f"/links/{link.id}/inline-toggle",
            data={"csrf_token": csrf},
        )
        assert toggle_resp.status_code == 200
        assert "Hidden" in toggle_resp.text

        del_resp = content_creator_client.post(
            f"/links/{link.id}/inline-delete",
            data={"csrf_token": csrf},
        )
        assert del_resp.status_code == 200
        assert repository.get_external_link(test_db, link.id) is None


class TestDivisionsInPageEditing:
    def _csrf(self, client: TestClient, path: str = "/divisions") -> str:
        resp = client.get(path)
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match, f"CSRF token not found on {path}"
        return match.group(1)

    def test_divisions_inline_operations(
        self,
        content_creator_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        season = repository.create_season(test_db, "Inline Div Season")
        club = repository.create_club(test_db, "Assign Club", "ASC", "1212")

        panel_resp = content_creator_client.get(
            f"/divisions/panel?season_id={season.id}"
        )
        assert panel_resp.status_code == 200
        assert "Division 1" in panel_resp.text

        csrf = self._csrf(content_creator_client, f"/divisions?season_id={season.id}")
        assign_resp = content_creator_client.post(
            "/divisions/inline-assign",
            data={
                "season_id": str(season.id),
                "club_id": str(club.id),
                "gender": "women",
                "division": "2",
                "csrf_token": csrf,
            },
        )
        assert assign_resp.status_code == 200
        assert "Assign Club" in assign_resp.text

        assignments = repository.list_division_assignments(test_db, season.id)
        assert len(assignments) == 1
        assign_id = assignments[0].id

        move_resp = content_creator_client.post(
            f"/divisions/assignments/{assign_id}/inline-move",
            data={
                "division": "1",
                "season_id": str(season.id),
                "csrf_token": csrf,
            },
        )
        assert move_resp.status_code == 200
        updated = repository.get_division_assignment(test_db, assign_id)
        assert updated is not None
        assert updated.division == 1

        del_resp = content_creator_client.post(
            f"/divisions/assignments/{assign_id}/inline-delete",
            data={
                "season_id": str(season.id),
                "csrf_token": csrf,
            },
        )
        assert del_resp.status_code == 200
        assert len(repository.list_division_assignments(test_db, season.id)) == 0


class TestWinnersInPageEditing:
    def _csrf(self, client: TestClient, path: str = "/winners") -> str:
        resp = client.get(path)
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match, f"CSRF token not found on {path}"
        return match.group(1)

    def test_winners_inline_operations(
        self,
        content_creator_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        season = repository.create_season(test_db, "Inline Win Season")

        panel_resp = content_creator_client.get("/winners/tables-panel")
        assert panel_resp.status_code == 200
        assert "Individual winners" in panel_resp.text

        csrf = self._csrf(content_creator_client, "/winners")
        add_resp = content_creator_client.post(
            "/winners/inline-add",
            data={
                "season_id": str(season.id),
                "winner_type": "individual",
                "category": "Senior Women",
                "winner_name": "Champion Athlete",
                "club": "Oxford City AC",
                "total_score": "4",
                "note": "Inline created",
                "mode": "replace",
                "csrf_token": csrf,
            },
        )
        assert add_resp.status_code == 200
        assert "Champion Athlete" in add_resp.text
        assert "Admin record" in add_resp.text

        override = next(
            o
            for o in repository.list_winner_overrides(test_db)
            if o.winner_name == "Champion Athlete"
        )
        form_resp = content_creator_client.get(
            f"/winners/overrides/{override.id}/inline-form"
        )
        assert form_resp.status_code == 200
        assert "Edit Winner Record" in form_resp.text

        edit_resp = content_creator_client.post(
            f"/winners/overrides/{override.id}/inline-edit",
            data={
                "season_id": str(season.id),
                "winner_type": "individual",
                "category": "Senior Women",
                "winner_name": "Updated Champion",
                "club": "Oxford City AC",
                "total_score": "3",
                "note": "Updated inline",
                "mode": "replace",
                "csrf_token": csrf,
            },
        )
        assert edit_resp.status_code == 200
        assert "Updated Champion" in edit_resp.text

        del_resp = content_creator_client.post(
            f"/winners/overrides/{override.id}/inline-delete",
            data={"csrf_token": csrf},
        )
        assert del_resp.status_code == 200
        assert repository.get_winner_override(test_db, override.id) is None
