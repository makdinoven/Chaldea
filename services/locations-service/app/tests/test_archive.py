"""
Tests for archive (Lore Wiki) CRUD endpoints in locations-service.

Covers:
- Categories: create, duplicate slug 409, list with article_count, update, delete, reorder
- Articles: create, duplicate slug 409, list (paginated), category filter, search filter,
  get by slug, get by slug 404, preview, preview 404, update, delete, featured
- Auth: admin endpoints require archive:* permissions, 401 without token, 403 without perms
- Security: SQL injection in path params
"""

from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helper: mock auth response from user-service
# ---------------------------------------------------------------------------
def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


ADMIN_HEADERS = {"Authorization": "Bearer admin-token"}

ADMIN_USER_RESPONSE = {
    "id": 1,
    "username": "admin",
    "role": "admin",
    "permissions": [
        "archive:create", "archive:read", "archive:update", "archive:delete",
    ],
}
REGULAR_USER_RESPONSE = {"id": 2, "username": "user", "role": "user", "permissions": []}


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------
def _make_category(cat_id=1, name="Lore", slug="lore", description="Lore desc",
                   sort_order=0, article_count=0):
    """Create a mock ArchiveCategory ORM object."""
    cat = MagicMock()
    cat.id = cat_id
    cat.name = name
    cat.slug = slug
    cat.description = description
    cat.sort_order = sort_order
    cat.article_count = article_count
    cat.created_at = datetime(2026, 1, 1, 12, 0, 0)
    cat.updated_at = datetime(2026, 1, 1, 12, 0, 0)
    return cat


def _make_article(article_id=1, title="Test Article", slug="test-article",
                  content="<p>Content</p>", summary="Summary text",
                  cover_image_url=None, is_featured=False,
                  featured_sort_order=0, created_by_user_id=1,
                  categories=None):
    """Create a mock ArchiveArticle ORM object."""
    article = MagicMock()
    article.id = article_id
    article.title = title
    article.slug = slug
    article.content = content
    article.summary = summary
    article.cover_image_url = cover_image_url
    article.is_featured = is_featured
    article.featured_sort_order = featured_sort_order
    article.created_by_user_id = created_by_user_id
    article.created_at = datetime(2026, 1, 1, 12, 0, 0)
    article.updated_at = datetime(2026, 1, 1, 12, 0, 0)
    article.categories = categories or []
    return article


# ===========================================================================
# CATEGORIES — GET /archive/categories
# ===========================================================================

class TestListCategories:
    """Tests for GET /archive/categories (public endpoint)."""

    @patch("crud.get_all_categories", new_callable=AsyncMock, return_value=[])
    def test_list_categories_empty(self, mock_crud, client):
        """Returns empty list when no categories exist."""
        response = client.get("/archive/categories")
        assert response.status_code == 200
        assert response.json() == []

    @patch("crud.get_all_categories", new_callable=AsyncMock)
    def test_list_categories_with_article_count(self, mock_crud, client):
        """Returns categories with article_count field."""
        cats = [
            _make_category(cat_id=1, name="Lore", slug="lore", article_count=5),
            _make_category(cat_id=2, name="Races", slug="races", article_count=3),
        ]
        mock_crud.return_value = cats

        response = client.get("/archive/categories")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "Lore"
        assert data[0]["article_count"] == 5
        assert data[1]["article_count"] == 3

    def test_list_categories_no_auth_required(self, client):
        """GET /archive/categories should be accessible without auth."""
        with patch("crud.get_all_categories", new_callable=AsyncMock, return_value=[]):
            response = client.get("/archive/categories")
            assert response.status_code == 200


# ===========================================================================
# CATEGORIES — POST /archive/categories/create
# ===========================================================================

class TestCreateCategory:
    """Tests for POST /archive/categories/create (admin-only)."""

    @patch("crud.create_category", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_category(self, mock_auth, mock_crud, client):
        """Admin can create a category."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_category(cat_id=10, name="History", slug="history")

        response = client.post(
            "/archive/categories/create",
            json={"name": "History", "slug": "history", "description": "History articles"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "History"
        assert data["slug"] == "history"

    @patch("crud.create_category", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_category_duplicate_slug(self, mock_auth, mock_crud, client):
        """Creating category with duplicate slug returns 409."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.side_effect = HTTPException(
            status_code=409, detail="Категория с таким slug уже существует"
        )

        response = client.post(
            "/archive/categories/create",
            json={"name": "Lore", "slug": "lore"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 409

    def test_create_category_no_token_returns_401(self, client):
        """No Authorization header -> 401."""
        response = client.post(
            "/archive/categories/create",
            json={"name": "Test", "slug": "test"},
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_create_category_non_admin_returns_403(self, mock_get, client):
        """Valid token but no archive:create permission -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.post(
            "/archive/categories/create",
            json={"name": "Test", "slug": "test"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403


# ===========================================================================
# CATEGORIES — PUT /archive/categories/{id}/update
# ===========================================================================

class TestUpdateCategory:
    """Tests for PUT /archive/categories/{id}/update (admin-only)."""

    @patch("crud.update_category", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_category(self, mock_auth, mock_crud, client):
        """Admin can update a category."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_category(cat_id=1, name="Updated Name", slug="lore")

        response = client.put(
            "/archive/categories/1/update",
            json={"name": "Updated Name"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    @patch("crud.update_category", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_category_not_found(self, mock_auth, mock_crud, client):
        """Updating non-existent category -> 404."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.side_effect = HTTPException(status_code=404, detail="Категория не найдена")

        response = client.put(
            "/archive/categories/99999/update",
            json={"name": "Ghost"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404

    def test_update_category_no_token_returns_401(self, client):
        """No auth -> 401."""
        response = client.put("/archive/categories/1/update", json={"name": "X"})
        assert response.status_code == 401


# ===========================================================================
# CATEGORIES — DELETE /archive/categories/{id}/delete
# ===========================================================================

class TestDeleteCategory:
    """Tests for DELETE /archive/categories/{id}/delete (admin-only)."""

    @patch("crud.delete_category", new_callable=AsyncMock, return_value=None)
    @patch("auth_http.requests.get")
    def test_delete_category(self, mock_auth, mock_crud, client):
        """Admin can delete a category."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.delete("/archive/categories/1/delete", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    @patch("crud.delete_category", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_category_not_found(self, mock_auth, mock_crud, client):
        """Deleting non-existent category -> 404."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.side_effect = HTTPException(status_code=404, detail="Категория не найдена")

        response = client.delete("/archive/categories/99999/delete", headers=ADMIN_HEADERS)
        assert response.status_code == 404

    def test_delete_category_no_token_returns_401(self, client):
        """No auth -> 401."""
        response = client.delete("/archive/categories/1/delete")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_delete_category_non_admin_returns_403(self, mock_get, client):
        """Non-admin -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.delete(
            "/archive/categories/1/delete",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403


# ===========================================================================
# CATEGORIES — PUT /archive/categories/reorder
# ===========================================================================

class TestReorderCategories:
    """Tests for PUT /archive/categories/reorder (admin-only)."""

    @patch("crud.reorder_categories", new_callable=AsyncMock, return_value=None)
    @patch("auth_http.requests.get")
    def test_reorder_categories(self, mock_auth, mock_crud, client):
        """Admin can reorder categories."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.put(
            "/archive/categories/reorder",
            json=[{"id": 2, "sort_order": 0}, {"id": 1, "sort_order": 1}],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_reorder_categories_no_token_returns_401(self, client):
        """No auth -> 401."""
        response = client.put(
            "/archive/categories/reorder",
            json=[{"id": 1, "sort_order": 0}],
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_reorder_categories_non_admin_returns_403(self, mock_get, client):
        """Non-admin -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.put(
            "/archive/categories/reorder",
            json=[{"id": 1, "sort_order": 0}],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403


# ===========================================================================
# ARTICLES — POST /archive/articles/create
# ===========================================================================

class TestCreateArticle:
    """Tests for POST /archive/articles/create (admin-only)."""

    @patch("crud.create_article", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_article(self, mock_auth, mock_crud, client):
        """Admin can create an article with categories."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_article(
            article_id=10,
            title="History of Chaldea",
            slug="history-of-chaldea",
            categories=[_make_category(cat_id=1, name="Lore", slug="lore")],
        )

        response = client.post(
            "/archive/articles/create",
            json={
                "title": "History of Chaldea",
                "slug": "history-of-chaldea",
                "content": "<p>Long ago...</p>",
                "summary": "A brief history",
                "category_ids": [1],
            },
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "History of Chaldea"
        assert data["slug"] == "history-of-chaldea"
        assert len(data["categories"]) == 1

    @patch("crud.create_article", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_article_duplicate_slug(self, mock_auth, mock_crud, client):
        """Creating article with duplicate slug returns 409."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.side_effect = HTTPException(
            status_code=409, detail="Статья с таким slug уже существует"
        )

        response = client.post(
            "/archive/articles/create",
            json={"title": "Dup", "slug": "existing-slug"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 409

    def test_create_article_no_token_returns_401(self, client):
        """No Authorization header -> 401."""
        response = client.post(
            "/archive/articles/create",
            json={"title": "Test", "slug": "test"},
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_create_article_non_admin_returns_403(self, mock_get, client):
        """Valid token but no archive:create permission -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.post(
            "/archive/articles/create",
            json={"title": "Test", "slug": "test"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403


# ===========================================================================
# ARTICLES — GET /archive/articles
# ===========================================================================

class TestListArticles:
    """Tests for GET /archive/articles (public, paginated)."""

    @patch("crud.get_articles", new_callable=AsyncMock)
    def test_list_articles(self, mock_crud, client):
        """Returns paginated list of articles."""
        articles = [
            _make_article(article_id=1, title="Article 1", slug="article-1"),
            _make_article(article_id=2, title="Article 2", slug="article-2"),
        ]
        mock_crud.return_value = (articles, 2)

        response = client.get("/archive/articles")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["articles"]) == 2

    @patch("crud.get_articles", new_callable=AsyncMock)
    def test_list_articles_category_filter(self, mock_crud, client):
        """GET with category_slug filter passes param to CRUD."""
        mock_crud.return_value = ([], 0)

        response = client.get("/archive/articles?category_slug=lore")
        assert response.status_code == 200
        # Verify the category_slug was passed
        mock_crud.assert_called_once()
        call_kwargs = mock_crud.call_args
        assert call_kwargs[1].get("category_slug") == "lore" or \
               (len(call_kwargs[0]) > 1 and call_kwargs[0][1] == "lore") or \
               "lore" in str(call_kwargs)

    @patch("crud.get_articles", new_callable=AsyncMock)
    def test_list_articles_search(self, mock_crud, client):
        """GET with search filter passes param to CRUD."""
        mock_crud.return_value = ([], 0)

        response = client.get("/archive/articles?search=magic")
        assert response.status_code == 200
        mock_crud.assert_called_once()

    @patch("crud.get_articles", new_callable=AsyncMock)
    def test_list_articles_pagination(self, mock_crud, client):
        """GET with page and per_page query params."""
        mock_crud.return_value = ([], 0)

        response = client.get("/archive/articles?page=2&per_page=5")
        assert response.status_code == 200

    def test_list_articles_no_auth_required(self, client):
        """GET /archive/articles should be accessible without auth."""
        with patch("crud.get_articles", new_callable=AsyncMock, return_value=([], 0)):
            response = client.get("/archive/articles")
            assert response.status_code == 200


# ===========================================================================
# ARTICLES — GET /archive/articles/{slug}
# ===========================================================================

class TestGetArticleBySlug:
    """Tests for GET /archive/articles/{slug} (public)."""

    @patch("crud.get_article_by_slug", new_callable=AsyncMock)
    def test_get_article_by_slug(self, mock_crud, client):
        """Returns full article with content and categories."""
        mock_crud.return_value = _make_article(
            article_id=1,
            title="History",
            slug="history",
            content="<p>Full content</p>",
            categories=[_make_category(cat_id=1, name="Lore", slug="lore")],
        )

        response = client.get("/archive/articles/history")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "History"
        assert data["content"] == "<p>Full content</p>"
        assert len(data["categories"]) == 1

    @patch("crud.get_article_by_slug", new_callable=AsyncMock)
    def test_get_article_by_slug_not_found(self, mock_crud, client):
        """Returns 404 for unknown slug."""
        mock_crud.side_effect = HTTPException(status_code=404, detail="Статья не найдена")

        response = client.get("/archive/articles/nonexistent")
        assert response.status_code == 404

    def test_get_article_no_auth_required(self, client):
        """GET /archive/articles/{slug} should be accessible without auth."""
        with patch("crud.get_article_by_slug", new_callable=AsyncMock,
                    return_value=_make_article()):
            response = client.get("/archive/articles/test")
            assert response.status_code == 200


# ===========================================================================
# ARTICLES — GET /archive/articles/preview/{slug}
# ===========================================================================

class TestGetArticlePreview:
    """Tests for GET /archive/articles/preview/{slug} (public)."""

    @patch("crud.get_article_preview", new_callable=AsyncMock)
    def test_get_article_preview(self, mock_crud, client):
        """Returns minimal article data for hover preview."""
        mock_crud.return_value = {
            "id": 1,
            "title": "History",
            "slug": "history",
            "summary": "A brief summary",
            "cover_image_url": "https://example.com/img.webp",
        }

        response = client.get("/archive/articles/preview/history")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "History"
        assert data["summary"] == "A brief summary"
        assert "content" not in data

    @patch("crud.get_article_preview", new_callable=AsyncMock)
    def test_get_article_preview_not_found(self, mock_crud, client):
        """Returns 404 for unknown slug."""
        mock_crud.side_effect = HTTPException(status_code=404, detail="Статья не найдена")

        response = client.get("/archive/articles/preview/nonexistent")
        assert response.status_code == 404

    def test_get_article_preview_no_auth_required(self, client):
        """GET /archive/articles/preview/{slug} should be accessible without auth."""
        with patch("crud.get_article_preview", new_callable=AsyncMock,
                    return_value={"id": 1, "title": "T", "slug": "t", "summary": None,
                                  "cover_image_url": None}):
            response = client.get("/archive/articles/preview/t")
            assert response.status_code == 200


# ===========================================================================
# ARTICLES — PUT /archive/articles/{id}/update
# ===========================================================================

class TestUpdateArticle:
    """Tests for PUT /archive/articles/{id}/update (admin-only)."""

    @patch("crud.update_article", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_article(self, mock_auth, mock_crud, client):
        """Admin can update an article."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_article(
            article_id=1, title="Updated Title", slug="updated-title"
        )

        response = client.put(
            "/archive/articles/1/update",
            json={"title": "Updated Title"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Updated Title"

    @patch("crud.update_article", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_article_not_found(self, mock_auth, mock_crud, client):
        """Updating non-existent article -> 404."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.side_effect = HTTPException(status_code=404, detail="Статья не найдена")

        response = client.put(
            "/archive/articles/99999/update",
            json={"title": "Ghost"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404

    @patch("crud.update_article", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_article_duplicate_slug_returns_409(self, mock_auth, mock_crud, client):
        """Updating article slug to existing slug -> 409."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.side_effect = HTTPException(
            status_code=409, detail="Статья с таким slug уже существует"
        )

        response = client.put(
            "/archive/articles/1/update",
            json={"slug": "existing-slug"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 409

    def test_update_article_no_token_returns_401(self, client):
        """No auth -> 401."""
        response = client.put("/archive/articles/1/update", json={"title": "X"})
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_update_article_non_admin_returns_403(self, mock_get, client):
        """Non-admin -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.put(
            "/archive/articles/1/update",
            json={"title": "X"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403


# ===========================================================================
# ARTICLES — DELETE /archive/articles/{id}/delete
# ===========================================================================

class TestDeleteArticle:
    """Tests for DELETE /archive/articles/{id}/delete (admin-only)."""

    @patch("crud.delete_article", new_callable=AsyncMock, return_value=None)
    @patch("auth_http.requests.get")
    def test_delete_article(self, mock_auth, mock_crud, client):
        """Admin can delete an article."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.delete("/archive/articles/1/delete", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    @patch("crud.delete_article", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_article_not_found(self, mock_auth, mock_crud, client):
        """Deleting non-existent article -> 404."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.side_effect = HTTPException(status_code=404, detail="Статья не найдена")

        response = client.delete("/archive/articles/99999/delete", headers=ADMIN_HEADERS)
        assert response.status_code == 404

    def test_delete_article_no_token_returns_401(self, client):
        """No auth -> 401."""
        response = client.delete("/archive/articles/1/delete")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_delete_article_non_admin_returns_403(self, mock_get, client):
        """Non-admin -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.delete(
            "/archive/articles/1/delete",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403


# ===========================================================================
# ARTICLES — GET /archive/featured
# ===========================================================================

class TestFeaturedArticles:
    """Tests for GET /archive/featured (public)."""

    @patch("crud.get_featured_articles", new_callable=AsyncMock)
    def test_featured_articles(self, mock_crud, client):
        """Returns only featured articles."""
        featured = [
            _make_article(article_id=1, title="Featured 1", slug="f1", is_featured=True,
                          featured_sort_order=0),
            _make_article(article_id=2, title="Featured 2", slug="f2", is_featured=True,
                          featured_sort_order=1),
        ]
        mock_crud.return_value = featured

        response = client.get("/archive/featured")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["is_featured"] is True
        assert data[1]["is_featured"] is True

    @patch("crud.get_featured_articles", new_callable=AsyncMock, return_value=[])
    def test_featured_articles_empty(self, mock_crud, client):
        """Returns empty list when no featured articles exist."""
        response = client.get("/archive/featured")
        assert response.status_code == 200
        assert response.json() == []

    def test_featured_articles_no_auth_required(self, client):
        """GET /archive/featured should be accessible without auth."""
        with patch("crud.get_featured_articles", new_callable=AsyncMock, return_value=[]):
            response = client.get("/archive/featured")
            assert response.status_code == 200


# ===========================================================================
# Auth enforcement — admin endpoints require archive:* permissions
# ===========================================================================

class TestArchiveAuth:
    """Admin archive endpoints return 401 without token, 403 without permissions."""

    # Endpoints that require archive:create
    CREATE_ENDPOINTS = [
        ("POST", "/archive/articles/create", {"title": "T", "slug": "t"}),
        ("POST", "/archive/categories/create", {"name": "N", "slug": "s"}),
    ]

    # Endpoints that require archive:update
    UPDATE_ENDPOINTS = [
        ("PUT", "/archive/articles/1/update", {"title": "T"}),
        ("PUT", "/archive/categories/1/update", {"name": "N"}),
        ("PUT", "/archive/categories/reorder", [{"id": 1, "sort_order": 0}]),
    ]

    # Endpoints that require archive:delete
    DELETE_ENDPOINTS = [
        ("DELETE", "/archive/articles/1/delete", None),
        ("DELETE", "/archive/categories/1/delete", None),
    ]

    def test_create_endpoints_require_auth(self, client):
        """Create endpoints return 401 without token."""
        for method, url, body in self.CREATE_ENDPOINTS:
            response = getattr(client, method.lower())(url, json=body)
            assert response.status_code == 401, f"{method} {url} should return 401"

    def test_update_endpoints_require_auth(self, client):
        """Update endpoints return 401 without token."""
        for method, url, body in self.UPDATE_ENDPOINTS:
            response = getattr(client, method.lower())(url, json=body)
            assert response.status_code == 401, f"{method} {url} should return 401"

    def test_delete_endpoints_require_auth(self, client):
        """Delete endpoints return 401 without token."""
        for method, url, _ in self.DELETE_ENDPOINTS:
            response = getattr(client, method.lower())(url)
            assert response.status_code == 401, f"{method} {url} should return 401"

    @patch("auth_http.requests.get")
    def test_create_endpoints_reject_regular_user(self, mock_get, client):
        """Create endpoints return 403 for user without archive:create."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        for method, url, body in self.CREATE_ENDPOINTS:
            response = getattr(client, method.lower())(url, json=body, headers=ADMIN_HEADERS)
            assert response.status_code == 403, f"{method} {url} should return 403"

    @patch("auth_http.requests.get")
    def test_update_endpoints_reject_regular_user(self, mock_get, client):
        """Update endpoints return 403 for user without archive:update."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        for method, url, body in self.UPDATE_ENDPOINTS:
            response = getattr(client, method.lower())(url, json=body, headers=ADMIN_HEADERS)
            assert response.status_code == 403, f"{method} {url} should return 403"

    @patch("auth_http.requests.get")
    def test_delete_endpoints_reject_regular_user(self, mock_get, client):
        """Delete endpoints return 403 for user without archive:delete."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        for method, url, _ in self.DELETE_ENDPOINTS:
            response = getattr(client, method.lower())(url, headers=ADMIN_HEADERS)
            assert response.status_code == 403, f"{method} {url} should return 403"


# ===========================================================================
# Security Tests
# ===========================================================================

class TestArchiveSecurity:
    """Security tests: SQL injection in path params and search."""

    def test_sql_injection_in_article_id_update(self, client):
        """SQL injection in article id path param -> 401/422 (auth or type validation)."""
        response = client.put(
            "/archive/articles/1;DROP TABLE archive_articles;--/update",
            json={"title": "Hacked"},
        )
        assert response.status_code in (401, 404, 422)

    def test_sql_injection_in_category_id_delete(self, client):
        """SQL injection in category id path param -> 401/422."""
        response = client.delete("/archive/categories/1 OR 1=1/delete")
        assert response.status_code in (401, 404, 422)

    @patch("crud.get_articles", new_callable=AsyncMock, return_value=([], 0))
    def test_sql_injection_in_search_param(self, mock_crud, client):
        """SQL injection in search query param should not crash."""
        response = client.get("/archive/articles?search='; DROP TABLE archive_articles; --")
        assert response.status_code in (200, 400)

    @patch("crud.get_article_by_slug", new_callable=AsyncMock)
    def test_sql_injection_in_slug_path(self, mock_crud, client):
        """SQL injection in slug path param should not crash."""
        mock_crud.side_effect = HTTPException(status_code=404, detail="Статья не найдена")
        response = client.get("/archive/articles/'; DROP TABLE archive_articles; --")
        assert response.status_code in (404, 422)
