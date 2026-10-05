"""Route tests: fixture licence and assessment uploads, and copy-from-fixture."""

import io
import re
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pikepdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from website import repository
from website.main import app
from website.models import FixtureDocumentType
from website.services.uploads import (
    FIXTURE_DOC_POLICY,
    IMAGE_POLICY,
    FileStore,
)
from website.web.deps import get_fixture_doc_store, get_image_store


def _pdf() -> bytes:
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(595, 842))
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.effect_noise((600, 600), 50).convert("RGB").save(out, format="JPEG")
    return out.getvalue()


def _csrf(client: TestClient) -> str:
    match = re.search(
        r'name="csrf_token"\s+value="([^"]+)"', client.get("/fixtures").text
    )
    assert match
    return match.group(1)


@pytest.fixture
def doc_dir(tmp_path: Path) -> Iterator[Path]:
    directory = tmp_path / "docs"
    app.dependency_overrides[get_fixture_doc_store] = lambda: FileStore(
        directory, FIXTURE_DOC_POLICY
    )
    yield directory
    app.dependency_overrides.pop(get_fixture_doc_store, None)


@pytest.fixture
def fixture_ids(test_db: duckdb.DuckDBPyConnection) -> tuple[int, int]:
    season = repository.create_season(test_db, "Docs Season")
    fixture = repository.create_fixture(
        test_db, season.id, "Docs Round", "2025-09-01", "Venue", "Addr", [], ""
    )
    return season.id, fixture.id


def _url(ids: tuple[int, int], tail: str = "") -> str:
    return f"/fixtures/seasons/{ids[0]}/fixtures/{ids[1]}/documents{tail}"


class TestUploadDocument:
    @pytest.mark.parametrize("client_name", ["admin_client", "content_creator_client"])
    def test_staff_can_upload(
        self,
        client_name: str,
        request: pytest.FixtureRequest,
        fixture_ids: tuple[int, int],
        doc_dir: Path,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        client: TestClient = request.getfixturevalue(client_name)
        response = client.post(
            _url(fixture_ids),
            data={"doc_type": "event_licence", "csrf_token": _csrf(client)},
            files={"file": ("licence.pdf", _pdf(), "application/pdf")},
        )
        assert response.status_code == 200
        assert "Event licence" in response.text
        docs = repository.list_fixture_documents(test_db, fixture_ids[1])
        assert [d.doc_type for d in docs] == [FixtureDocumentType.event_licence]
        assert (doc_dir / docs[0].filename).exists()
        assert docs[0].uploaded_by_id is not None

    def test_reupload_replaces_and_removes_old_file(
        self,
        admin_client: TestClient,
        fixture_ids: tuple[int, int],
        doc_dir: Path,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        csrf = _csrf(admin_client)
        for name, body in (("a.pdf", _pdf()), ("b.jpg", _jpeg())):
            admin_client.post(
                _url(fixture_ids),
                data={"doc_type": "risk_assessment", "csrf_token": csrf},
                files={"file": (name, body, "application/octet-stream")},
            )
        docs = repository.list_fixture_documents(test_db, fixture_ids[1])
        assert len(docs) == 1
        assert docs[0].original_name == "b.jpg"
        assert len(list(doc_dir.iterdir())) == 1

    def test_rejects_disguised_executable(
        self, admin_client: TestClient, fixture_ids: tuple[int, int], doc_dir: Path
    ) -> None:
        response = admin_client.post(
            _url(fixture_ids),
            data={"doc_type": "medical_assessment", "csrf_token": _csrf(admin_client)},
            files={"file": ("evil.pdf", b"MZ\x90\x00 binary", "application/pdf")},
        )
        assert response.status_code == 400
        assert not doc_dir.exists() or not list(doc_dir.iterdir())

    def test_rejects_wrong_extension(
        self, admin_client: TestClient, fixture_ids: tuple[int, int], doc_dir: Path
    ) -> None:
        response = admin_client.post(
            _url(fixture_ids),
            data={"doc_type": "event_licence", "csrf_token": _csrf(admin_client)},
            files={"file": ("notes.docx", _pdf(), "application/pdf")},
        )
        assert response.status_code == 400

    def test_unknown_doc_type_is_rejected(
        self, admin_client: TestClient, fixture_ids: tuple[int, int], doc_dir: Path
    ) -> None:
        response = admin_client.post(
            _url(fixture_ids),
            data={"doc_type": "nonsense", "csrf_token": _csrf(admin_client)},
            files={"file": ("a.pdf", _pdf(), "application/pdf")},
        )
        assert response.status_code == 422

    def test_unknown_fixture_returns_404(
        self, admin_client: TestClient, doc_dir: Path
    ) -> None:
        response = admin_client.post(
            "/fixtures/seasons/1/fixtures/9999/documents",
            data={"doc_type": "event_licence", "csrf_token": _csrf(admin_client)},
            files={"file": ("a.pdf", _pdf(), "application/pdf")},
        )
        assert response.status_code == 404

    def test_club_manager_is_denied(
        self,
        club_manager_client: TestClient,
        fixture_ids: tuple[int, int],
        doc_dir: Path,
    ) -> None:
        response = club_manager_client.post(
            _url(fixture_ids),
            data={"doc_type": "event_licence", "csrf_token": "x"},
            files={"file": ("a.pdf", _pdf(), "application/pdf")},
            follow_redirects=False,
        )
        assert response.status_code in (302, 403)

    def test_anonymous_is_denied(
        self,
        test_client: TestClient,
        fixture_ids: tuple[int, int],
        doc_dir: Path,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        response = test_client.post(
            _url(fixture_ids),
            data={"doc_type": "event_licence", "csrf_token": "x"},
            files={"file": ("a.pdf", _pdf(), "application/pdf")},
            follow_redirects=False,
        )
        assert response.status_code in (302, 403)
        assert not repository.list_fixture_documents(test_db, fixture_ids[1])

    def test_requires_csrf(
        self, admin_client: TestClient, fixture_ids: tuple[int, int], doc_dir: Path
    ) -> None:
        response = admin_client.post(
            _url(fixture_ids),
            data={"doc_type": "event_licence", "csrf_token": "wrong"},
            files={"file": ("a.pdf", _pdf(), "application/pdf")},
        )
        assert response.status_code == 403


class TestDeleteAndDisplay:
    def _seed(
        self,
        client: TestClient,
        ids: tuple[int, int],
    ) -> None:
        client.post(
            _url(ids),
            data={"doc_type": "event_licence", "csrf_token": _csrf(client)},
            files={"file": ("licence.pdf", _pdf(), "application/pdf")},
        )

    def test_delete_removes_record_and_file(
        self,
        admin_client: TestClient,
        fixture_ids: tuple[int, int],
        doc_dir: Path,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        self._seed(admin_client, fixture_ids)
        doc = repository.list_fixture_documents(test_db, fixture_ids[1])[0]
        response = admin_client.post(
            _url(fixture_ids, f"/{doc.id}/delete"),
            data={"csrf_token": _csrf(admin_client)},
        )
        assert response.status_code == 200
        assert not repository.list_fixture_documents(test_db, fixture_ids[1])
        assert not list(doc_dir.iterdir())

    def test_delete_ignores_document_from_another_fixture(
        self,
        admin_client: TestClient,
        fixture_ids: tuple[int, int],
        doc_dir: Path,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        self._seed(admin_client, fixture_ids)
        other = repository.create_fixture(
            test_db, fixture_ids[0], "Other", "2025-10-01", "V", "A", [], ""
        )
        doc = repository.list_fixture_documents(test_db, fixture_ids[1])[0]
        admin_client.post(
            f"/fixtures/seasons/{fixture_ids[0]}/fixtures/{other.id}/documents/{doc.id}/delete",
            data={"csrf_token": _csrf(admin_client)},
        )
        assert repository.list_fixture_documents(test_db, fixture_ids[1])

    def test_public_sees_link_but_no_controls(
        self,
        admin_client: TestClient,
        fixture_ids: tuple[int, int],
        doc_dir: Path,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        self._seed(admin_client, fixture_ids)
        filename = repository.list_fixture_documents(test_db, fixture_ids[1])[
            0
        ].filename
        anon = TestClient(app, headers={"X-Forwarded-For": "203.0.113.9"})
        html = anon.get(f"/fixtures/fixture-detail?fixture_id={fixture_ids[1]}").text
        assert f"/fixture-docs/{filename}" in html
        assert "Event licence" in html
        assert "doc-upload-" not in html
        assert "Not uploaded" not in html

    def test_staff_sees_upload_slots(
        self, admin_client: TestClient, fixture_ids: tuple[int, int]
    ) -> None:
        html = admin_client.get(
            f"/fixtures/fixture-detail?fixture_id={fixture_ids[1]}"
        ).text
        assert "doc-upload-event_licence" in html
        assert "doc-upload-risk_assessment" in html
        assert "doc-upload-medical_assessment" in html

    def test_public_sees_no_heading_when_empty(
        self, test_client: TestClient, fixture_ids: tuple[int, int]
    ) -> None:
        html = test_client.get(
            f"/fixtures/fixture-detail?fixture_id={fixture_ids[1]}"
        ).text
        assert "Event Documents" not in html

    def test_deleting_fixture_removes_documents(
        self,
        admin_client: TestClient,
        fixture_ids: tuple[int, int],
        doc_dir: Path,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        self._seed(admin_client, fixture_ids)
        admin_client.post(
            f"/fixtures/seasons/{fixture_ids[0]}/fixtures/{fixture_ids[1]}/delete",
            data={"csrf_token": _csrf(admin_client)},
        )
        assert repository.get_fixture_by_id(test_db, fixture_ids[1]) is None


class TestCopyFromFixture:
    @pytest.fixture
    def source(
        self, test_db: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> Iterator[tuple[int, int]]:
        from website.models import TimetableEntry

        old = repository.create_season(test_db, "2024-2025")
        fixture = repository.create_fixture(
            test_db,
            old.id,
            "Old Round",
            "2024-09-01",
            "Old Park",
            "1 Old Road",
            [TimetableEntry(event="Senior race", time="11:00")],
            "Take the bus",
        )
        maps = tmp_path / "maps"
        maps.mkdir()
        (maps / "map.jpg").write_bytes(b"map-bytes")
        repository.create_fixture_image(test_db, fixture.id, "map.jpg")
        app.dependency_overrides[get_image_store] = lambda: FileStore(
            maps, IMAGE_POLICY
        )
        yield old.id, fixture.id
        app.dependency_overrides.pop(get_image_store, None)

    def _new_season(self, test_db: duckdb.DuckDBPyConnection) -> int:
        return repository.create_season(test_db, "2025-2026").id

    def test_picker_lists_fixtures_from_every_season(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        source: tuple[int, int],
    ) -> None:
        new_id = self._new_season(test_db)
        html = admin_client.get(f"/fixtures/seasons/{new_id}/fixtures/new").text
        assert 'optgroup label="2024-2025"' in html
        assert "Old Round" in html

    def test_prefill_copies_details_but_not_date(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        source: tuple[int, int],
    ) -> None:
        new_id = self._new_season(test_db)
        html = admin_client.get(
            f"/fixtures/seasons/{new_id}/fixtures/new?copy_from={source[1]}"
        ).text
        assert 'value="Old Park"' in html
        assert "Take the bus" in html
        assert "Senior race" in html
        assert 'value="2024-09-01"' not in html
        assert f'name="copy_from_fixture_id" value="{source[1]}"' in html

    def test_prefill_respects_unchecked_parts(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        source: tuple[int, int],
    ) -> None:
        new_id = self._new_season(test_db)
        html = admin_client.get(
            f"/fixtures/seasons/{new_id}/fixtures/new?copy_from={source[1]}&parts=timetable"
        ).text
        assert "Senior race" in html
        assert "Take the bus" not in html
        assert 'value="Old Park"' not in html

    def test_prefill_unknown_source_returns_404(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        new_id = self._new_season(test_db)
        response = admin_client.get(
            f"/fixtures/seasons/{new_id}/fixtures/new?copy_from=9999"
        )
        assert response.status_code == 404

    def test_picker_requires_staff(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        new_id = self._new_season(test_db)
        response = test_client.get(
            f"/fixtures/seasons/{new_id}/fixtures/new", follow_redirects=False
        )
        assert response.status_code in (302, 403)

    def test_create_with_copy_maps_duplicates_files(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        source: tuple[int, int],
        tmp_path: Path,
    ) -> None:
        new_id = self._new_season(test_db)
        response = admin_client.post(
            f"/fixtures/seasons/{new_id}/fixtures",
            data={
                "title": "New Round",
                "date": "2025-09-06",
                "location_name": "Old Park",
                "address": "1 Old Road",
                "csrf_token": _csrf(admin_client),
                "copy_from_fixture_id": str(source[1]),
                "copy_maps": "true",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        created = repository.list_fixtures_for_season(test_db, new_id)[0]
        copied = repository.list_fixture_images(test_db, created.id)
        original = repository.list_fixture_images(test_db, source[1])
        assert len(copied) == 1
        assert copied[0].filename != original[0].filename
        assert (tmp_path / "maps" / copied[0].filename).read_bytes() == b"map-bytes"

    def test_create_without_copy_maps_skips_files(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        source: tuple[int, int],
    ) -> None:
        new_id = self._new_season(test_db)
        admin_client.post(
            f"/fixtures/seasons/{new_id}/fixtures",
            data={
                "title": "New Round",
                "date": "2025-09-06",
                "location_name": "V",
                "address": "A",
                "csrf_token": _csrf(admin_client),
                "copy_from_fixture_id": str(source[1]),
            },
        )
        created = repository.list_fixtures_for_season(test_db, new_id)[0]
        assert not repository.list_fixture_images(test_db, created.id)

    def test_existing_copy_button_flow_copies_maps(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        source: tuple[int, int],
    ) -> None:
        new_id = self._new_season(test_db)
        page = admin_client.get(
            f"/fixtures/seasons/{source[0]}/fixtures/{source[1]}/copy"
        ).text
        assert 'name="copy_maps"' in page
        admin_client.post(
            "/fixtures/copy",
            data={
                "season_id": str(new_id),
                "title": "Copied",
                "date": "2025-09-06",
                "location_name": "Old Park",
                "address": "1 Old Road",
                "csrf_token": _csrf(admin_client),
                "copy_from_fixture_id": str(source[1]),
                "copy_maps": "true",
            },
        )
        created = repository.list_fixtures_for_season(test_db, new_id)[0]
        assert len(repository.list_fixture_images(test_db, created.id)) == 1
