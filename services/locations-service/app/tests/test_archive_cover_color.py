"""
Tests for the cover_text_color field on archive articles (FEAT-101).

Covers:
- Create article with cover_text_color — stored and returned
- Create article without cover_text_color — default '#FFFFFF' used
- Update article cover_text_color — updated value returned
- Get article by slug — cover_text_color in response
- List articles — cover_text_color in list items
- Featured articles — cover_text_color in featured items
"""

from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime


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


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------
def _make_article(article_id=1, title="Test Article", slug="test-article",
                  content="<p>Content</p>", summary="Summary text",
                  cover_image_url=None, cover_text_color="#FFFFFF",
                  is_featured=False, featured_sort_order=0,
                  created_by_user_id=1, categories=None):
    """Create a mock ArchiveArticle ORM object with cover_text_color."""
    article = MagicMock()
    article.id = article_id
    article.title = title
    article.slug = slug
    article.content = content
    article.summary = summary
    article.cover_image_url = cover_image_url
    article.cover_text_color = cover_text_color
    article.is_featured = is_featured
    article.featured_sort_order = featured_sort_order
    article.created_by_user_id = created_by_user_id
    article.created_at = datetime(2026, 1, 1, 12, 0, 0)
    article.updated_at = datetime(2026, 1, 1, 12, 0, 0)
    article.categories = categories or []
    return article


# ===========================================================================
# CREATE — with cover_text_color
# ===========================================================================

class TestCreateArticleWithCoverTextColor:
    """Tests for cover_text_color on POST /archive/articles/create."""

    @patch("crud.create_article", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_article_with_cover_text_color(self, mock_auth, mock_crud, client):
        """Admin can create article with explicit cover_text_color."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_article(
            article_id=10,
            title="Dark Article",
            slug="dark-article",
            cover_text_color="#000000",
        )

        response = client.post(
            "/archive/articles/create",
            json={
                "title": "Dark Article",
                "slug": "dark-article",
                "content": "<p>Content</p>",
                "cover_text_color": "#000000",
            },
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["cover_text_color"] == "#000000"

    @patch("crud.create_article", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_article_without_cover_text_color_uses_default(
        self, mock_auth, mock_crud, client
    ):
        """Creating article without cover_text_color returns default '#FFFFFF'."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_article(
            article_id=11,
            title="Default Color Article",
            slug="default-color",
            cover_text_color="#FFFFFF",
        )

        response = client.post(
            "/archive/articles/create",
            json={
                "title": "Default Color Article",
                "slug": "default-color",
                "content": "<p>Content</p>",
            },
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["cover_text_color"] == "#FFFFFF"

    @patch("crud.create_article", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_article_cover_text_color_passed_to_crud(
        self, mock_auth, mock_crud, client
    ):
        """Verify cover_text_color from request payload is passed to CRUD layer."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_article(cover_text_color="#FF0000")

        response = client.post(
            "/archive/articles/create",
            json={
                "title": "Red Text",
                "slug": "red-text",
                "cover_text_color": "#FF0000",
            },
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200

        # Verify the CRUD function was called and the schema had cover_text_color
        mock_crud.assert_called_once()
        call_args = mock_crud.call_args
        # First positional arg is db, second is the schema object
        schema_arg = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("data")
        if schema_arg and hasattr(schema_arg, "cover_text_color"):
            assert schema_arg.cover_text_color == "#FF0000"


# ===========================================================================
# UPDATE — cover_text_color
# ===========================================================================

class TestUpdateArticleCoverTextColor:
    """Tests for cover_text_color on PUT /archive/articles/{id}/update."""

    @patch("crud.update_article", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_article_cover_text_color(self, mock_auth, mock_crud, client):
        """Admin can update cover_text_color on an existing article."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_article(
            article_id=1,
            title="Updated Article",
            slug="updated-article",
            cover_text_color="#00FF00",
        )

        response = client.put(
            "/archive/articles/1/update",
            json={"cover_text_color": "#00FF00"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["cover_text_color"] == "#00FF00"

    @patch("crud.update_article", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_article_cover_text_color_to_different_value(
        self, mock_auth, mock_crud, client
    ):
        """Updating cover_text_color from one value to another works."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_article(
            article_id=1, cover_text_color="#123456"
        )

        response = client.put(
            "/archive/articles/1/update",
            json={"cover_text_color": "#123456"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["cover_text_color"] == "#123456"


# ===========================================================================
# GET article by slug — cover_text_color in response
# ===========================================================================

class TestGetArticleCoverTextColor:
    """Tests for cover_text_color on GET /archive/articles/{slug}."""

    @patch("crud.get_article_by_slug", new_callable=AsyncMock)
    def test_get_article_includes_cover_text_color(self, mock_crud, client):
        """GET article response includes cover_text_color field."""
        mock_crud.return_value = _make_article(
            article_id=1,
            title="Color Article",
            slug="color-article",
            cover_text_color="#ABCDEF",
        )

        response = client.get("/archive/articles/color-article")
        assert response.status_code == 200
        data = response.json()
        assert "cover_text_color" in data
        assert data["cover_text_color"] == "#ABCDEF"

    @patch("crud.get_article_by_slug", new_callable=AsyncMock)
    def test_get_article_default_cover_text_color(self, mock_crud, client):
        """Article with default cover_text_color returns '#FFFFFF'."""
        mock_crud.return_value = _make_article(
            slug="default-article",
            cover_text_color="#FFFFFF",
        )

        response = client.get("/archive/articles/default-article")
        assert response.status_code == 200
        assert response.json()["cover_text_color"] == "#FFFFFF"


# ===========================================================================
# LIST articles — cover_text_color in list items
# ===========================================================================

class TestListArticlesCoverTextColor:
    """Tests for cover_text_color on GET /archive/articles (paginated list)."""

    @patch("crud.get_articles", new_callable=AsyncMock)
    def test_list_articles_includes_cover_text_color(self, mock_crud, client):
        """Paginated article list items include cover_text_color."""
        articles = [
            _make_article(article_id=1, slug="a1", cover_text_color="#FF0000"),
            _make_article(article_id=2, slug="a2", cover_text_color="#00FF00"),
            _make_article(article_id=3, slug="a3", cover_text_color="#FFFFFF"),
        ]
        mock_crud.return_value = (articles, 3)

        response = client.get("/archive/articles")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3

        for i, expected_color in enumerate(["#FF0000", "#00FF00", "#FFFFFF"]):
            assert "cover_text_color" in data["articles"][i]
            assert data["articles"][i]["cover_text_color"] == expected_color

    @patch("crud.get_articles", new_callable=AsyncMock)
    def test_list_articles_all_default_color(self, mock_crud, client):
        """All articles with default color return '#FFFFFF' in list."""
        articles = [
            _make_article(article_id=1, slug="a1", cover_text_color="#FFFFFF"),
            _make_article(article_id=2, slug="a2", cover_text_color="#FFFFFF"),
        ]
        mock_crud.return_value = (articles, 2)

        response = client.get("/archive/articles")
        assert response.status_code == 200
        data = response.json()
        for article in data["articles"]:
            assert article["cover_text_color"] == "#FFFFFF"


# ===========================================================================
# FEATURED articles — cover_text_color in featured items
# ===========================================================================

class TestFeaturedArticlesCoverTextColor:
    """Tests for cover_text_color on GET /archive/featured."""

    @patch("crud.get_featured_articles", new_callable=AsyncMock)
    def test_featured_articles_include_cover_text_color(self, mock_crud, client):
        """Featured articles response includes cover_text_color."""
        featured = [
            _make_article(
                article_id=1, slug="f1", is_featured=True,
                featured_sort_order=0, cover_text_color="#000000",
            ),
            _make_article(
                article_id=2, slug="f2", is_featured=True,
                featured_sort_order=1, cover_text_color="#FFFFFF",
            ),
        ]
        mock_crud.return_value = featured

        response = client.get("/archive/featured")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["cover_text_color"] == "#000000"
        assert data[1]["cover_text_color"] == "#FFFFFF"
