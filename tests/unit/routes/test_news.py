"""Route tests: News posts: listing, pagination, create, edit and delete."""

import re

import duckdb
from fastapi.testclient import TestClient


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
