"""Route tests: serving documents that are stored gzipped at rest."""

from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from website import repository
from website.config import Settings
from website.main import app
from website.services.archive import write_archived
from website.web.deps import get_settings
from website.web.stored_files import StoredFiles

_PDF = b"%PDF-1.4\n" + b"1 0 obj << /Type /Catalog >> endobj\n" * 400 + b"%%EOF"


@pytest.fixture
def files_client(tmp_path: Path) -> TestClient:
    static = FastAPI()
    static.mount("/files", StoredFiles(directory=str(tmp_path)), name="files")
    return TestClient(static)


class TestStoredFiles:
    def test_archive_is_served_gzip_encoded(
        self, files_client: TestClient, tmp_path: Path
    ) -> None:
        write_archived(tmp_path / "doc.pdf", _PDF)
        response = files_client.get("/files/doc.pdf")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["content-encoding"] == "gzip"
        assert response.headers["vary"] == "Accept-Encoding"
        assert "accept-ranges" not in response.headers
        assert response.content == _PDF  # httpx decodes the gzip body

    def test_range_requests_get_the_whole_file(
        self, files_client: TestClient, tmp_path: Path
    ) -> None:
        write_archived(tmp_path / "doc.pdf", _PDF)
        response = files_client.get("/files/doc.pdf", headers={"Range": "bytes=0-9"})
        assert response.status_code == 200
        assert response.content == _PDF

    def test_client_without_gzip_gets_identity(
        self, files_client: TestClient, tmp_path: Path
    ) -> None:
        write_archived(tmp_path / "doc.pdf", _PDF)
        response = files_client.get(
            "/files/doc.pdf", headers={"Accept-Encoding": "identity"}
        )
        assert response.status_code == 200
        assert "content-encoding" not in response.headers
        assert response.content == _PDF

    def test_conditional_request_is_not_modified(
        self, files_client: TestClient, tmp_path: Path
    ) -> None:
        write_archived(tmp_path / "doc.pdf", _PDF)
        etag = files_client.get("/files/doc.pdf").headers["etag"]
        response = files_client.get("/files/doc.pdf", headers={"If-None-Match": etag})
        assert response.status_code == 304

    def test_plain_files_are_served_unchanged(
        self, files_client: TestClient, tmp_path: Path
    ) -> None:
        (tmp_path / "map.png").write_bytes(b"png")
        response = files_client.get("/files/map.png")
        assert response.status_code == 200
        assert "content-encoding" not in response.headers
        assert response.content == b"png"

    def test_missing_file_is_404(self, files_client: TestClient) -> None:
        assert files_client.get("/files/none.pdf").status_code == 404
        assert files_client.get("/files/none.pdf.gz").status_code == 404


@pytest.fixture
def pdf_root(tmp_path: Path) -> Iterator[Path]:
    app.dependency_overrides[get_settings] = lambda: Settings(results_pdf_root=tmp_path)
    yield tmp_path
    app.dependency_overrides.pop(get_settings, None)


class TestResultsSourcePdf:
    def _fixture_with_pdf(self, db: duckdb.DuckDBPyConnection, name: str) -> int:
        season = repository.create_season(db, "PDF Season")
        fixture = repository.create_fixture(
            db, season.id, "Round 1", "2025-10-01", "Venue", "Addr", [], ""
        )
        repository.set_fixture_source_pdf(db, fixture.id, name)
        return fixture.id

    def test_archived_pdf_is_served_as_download(
        self,
        test_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        pdf_root: Path,
    ) -> None:
        (pdf_root / "results" / "1").mkdir(parents=True)
        write_archived(pdf_root / "results" / "1" / "round1.pdf", _PDF)
        fixture_id = self._fixture_with_pdf(test_db, "results/1/round1.pdf")
        response = test_client.get(f"/results/source-pdf?fixture_id={fixture_id}")
        assert response.status_code == 200
        assert response.headers["content-encoding"] == "gzip"
        assert response.headers["content-type"] == "application/pdf"
        assert "round1.pdf" in response.headers["content-disposition"]
        assert response.content == _PDF

    def test_archived_pdf_without_gzip_support(
        self,
        test_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        pdf_root: Path,
    ) -> None:
        write_archived(pdf_root / "round1.pdf", _PDF)
        fixture_id = self._fixture_with_pdf(test_db, "round1.pdf")
        response = test_client.get(
            f"/results/source-pdf?fixture_id={fixture_id}",
            headers={"Accept-Encoding": "identity"},
        )
        assert response.status_code == 200
        assert "content-encoding" not in response.headers
        assert "round1.pdf" in response.headers["content-disposition"]
        assert response.content == _PDF

    def test_plain_pdf_is_still_served(
        self,
        test_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        pdf_root: Path,
    ) -> None:
        (pdf_root / "round1.pdf").write_bytes(b"%PDF-tiny")
        fixture_id = self._fixture_with_pdf(test_db, "round1.pdf")
        response = test_client.get(f"/results/source-pdf?fixture_id={fixture_id}")
        assert response.status_code == 200
        assert "content-encoding" not in response.headers
        assert response.content == b"%PDF-tiny"

    def test_missing_pdf_is_404(
        self,
        test_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        pdf_root: Path,
    ) -> None:
        fixture_id = self._fixture_with_pdf(test_db, "gone.pdf")
        response = test_client.get(f"/results/source-pdf?fixture_id={fixture_id}")
        assert response.status_code == 404
