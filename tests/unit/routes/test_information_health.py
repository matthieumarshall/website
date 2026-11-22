"""Information editing and health status access tests."""

import re
import time
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from limits import parse

from website import repository
from website.main import app
from website.models.health import DiskMeasurement, Measurements
from website.web.rate_limit import limiter


def token(client, path):
    response = client.get(path)
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text)
    assert match
    return match.group(1)


@pytest.mark.parametrize("slug", ["about", "contact"])
def test_information_defaults_and_editor(slug, test_db, admin_client):
    path = f"/{slug}"
    original = admin_client.get(path)
    assert original.status_code == 200
    assert repository.get_static_page(test_db, slug) is None
    assert f'href="/{slug}/edit"' in original.text
    editor = admin_client.get(f"{path}/edit")
    assert editor.status_code == 200
    assert (
        "committee@oxonxc.org.uk" in editor.text
        if slug == "contact"
        else "Our mission" in editor.text
    )
    assert admin_client.post(f"{path}/edit", data={"content": "x"}).status_code == 403
    csrf = token(admin_client, f"{path}/edit")
    response = admin_client.post(
        f"{path}/edit",
        data={"csrf_token": csrf, "content": "<p>Changed</p><script>alert(1)</script>"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == path
    page = admin_client.get(path).text
    assert "Changed" in page and "<script>alert(1)</script>" not in page
    admin_client.post(f"{path}/edit", data={"csrf_token": csrf, "content": ""})
    empty = admin_client.get(path).text
    assert "Changed" not in empty
    assert (
        "Our mission" not in empty
        if slug == "about"
        else "committee@oxonxc.org.uk" not in empty
    )


@pytest.mark.parametrize("slug", ["about", "contact"])
def test_information_permissions(
    slug, test_client, club_manager_client, content_creator_client
):
    path = f"/{slug}/edit"
    assert test_client.get(path, follow_redirects=False).status_code == 302
    assert club_manager_client.get(path, follow_redirects=False).status_code == 403
    assert (
        club_manager_client.post(
            path, data={"content": "x"}, follow_redirects=False
        ).status_code
        == 403
    )
    assert content_creator_client.get(path).status_code == 200
    csrf = token(content_creator_client, path)
    assert (
        content_creator_client.post(
            path,
            data={"content": "Staff update", "csrf_token": csrf},
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert "Staff update" in test_client.get(f"/{slug}").text


@pytest.fixture
def health_sample(monkeypatch):
    sample = Measurements(
        checked_at=datetime.now(UTC),
        checked_monotonic=time.monotonic(),
        database="available",
        cpu=19.1,
        load_per_cpu=0.2,
        memory=24.2,
        disks=(DiskMeasurement(percent=33.3, used=123456789, free=987654321),),
        database_size=87654321,
        wal_size=34567,
    )
    sampler = Mock()
    sampler.snapshot.return_value = sample
    monkeypatch.setattr(app.state, "health_sampler", sampler, raising=False)
    return sampler


def test_health_public_and_admin_visibility(
    test_client,
    admin_client,
    club_manager_client,
    content_creator_client,
    health_sample,
):
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {
        "status",
        "database",
        "storage",
        "memory",
        "server_load",
        "checked_at",
    }
    assert "123456789" not in response.text
    for client in (test_client, club_manager_client, content_creator_client):
        for path in ("/status", "/status/summary"):
            result = client.get(path)
            assert result.headers["cache-control"] == "no-store"
            assert "Cookie" in result.headers["vary"]
            assert "Administrator details" not in result.text
            assert "123456789" not in result.text
    assert "123456789" in admin_client.get("/status").text
    assert "123456789" not in admin_client.get("/health").text
    assert health_sample.snapshot.call_count == 9


def test_health_unavailable_and_pressure(test_client, health_sample):
    original = health_sample.snapshot.return_value
    health_sample.snapshot.return_value = original.model_copy(update={"memory": 99.0})
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    health_sample.snapshot.return_value = original.model_copy(
        update={"database": "unavailable"}
    )
    assert test_client.get("/health").status_code == 503
    assert test_client.get("/status").status_code == 200
    health_sample.snapshot.return_value = original.model_copy(
        update={"checked_monotonic": time.monotonic() - 46}
    )
    assert test_client.get("/health").status_code == 503
    health_sample.snapshot.return_value = None
    assert test_client.get("/health").status_code == 503
    health_sample.snapshot.return_value = original
    assert test_client.get("/health").status_code == 200


@pytest.fixture
def enabled_limiter(monkeypatch):
    """Exercise the real rate limiter, normally disabled in unit tests."""
    limiter.reset()
    monkeypatch.setattr(limiter, "enabled", True)
    yield
    limiter.reset()


def test_status_rate_limit_is_shared_per_client_and_health_is_independent(
    test_client, health_sample, enabled_limiter
):
    for number in range(120):
        path = "/status" if number % 2 else "/status/summary"
        assert test_client.get(path).status_code == 200
    response = test_client.get("/status")
    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= 60
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["detail"].startswith("Too many requests")
    assert test_client.get("/health").status_code == 200
    other = TestClient(app, client=("203.0.113.10", 1234))
    assert other.get("/status").status_code == 200


def test_global_status_cap_and_health_limit(
    test_client, health_sample, enabled_limiter
):
    limiter.limiter.hit(parse("1800/minute"), "global", "status-global", cost=1800)
    assert test_client.get("/status/summary").status_code == 429
    assert test_client.get("/health").status_code == 200
    for _ in range(119):
        assert test_client.get("/health").status_code == 200
    response = test_client.get("/health")
    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= 60


def test_global_health_cap_does_not_consume_status_budget(
    test_client, health_sample, enabled_limiter
):
    limiter.limiter.hit(parse("3600/minute"), "global", "health-global", cost=3600)
    response = test_client.get("/health")
    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= 60
    assert test_client.get("/status").status_code == 200


def test_login_limit_keeps_login_response_and_retry_header(
    test_client, enabled_limiter
):
    csrf = token(test_client, "/login")
    for _ in range(5):
        result = test_client.post(
            "/login",
            data={"username": "unknown", "password": "invalid", "csrf_token": csrf},
        )
        assert result.status_code == 401
    result = test_client.post(
        "/login",
        data={"username": "unknown", "password": "invalid", "csrf_token": csrf},
    )
    assert result.status_code == 429
    assert "Too many login attempts" in result.text
    assert 1 <= int(result.headers["retry-after"]) <= 900
