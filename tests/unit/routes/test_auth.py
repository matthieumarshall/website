"""Route tests: Login, logout and redirects for signed-in users."""

import re

from fastapi.testclient import TestClient


class TestLoginPageRoute:
    def test_login_page_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/login").status_code == 200

    def test_login_page_preserves_next_path(self, test_client: TestClient) -> None:
        response = test_client.get("/login?next=/entries")
        assert response.status_code == 200
        assert 'name="next_path" value="/entries"' in response.text


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
