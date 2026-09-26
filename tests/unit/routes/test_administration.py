"""Route tests: Administration documents and editable guide pages."""

import re
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from website import repository
from website.main import app
from website.services.uploads import DOCUMENT_POLICY, FileStore
from website.web.deps import get_document_store


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
