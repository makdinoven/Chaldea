"""
FEAT-103 Task #13 — QA Tests for cosmetics endpoints in user-service.

Covers:
- Catalog endpoints: GET /users/cosmetics/frames, GET /users/cosmetics/backgrounds
- User collection: GET /users/cosmetics/my/frames, GET /users/cosmetics/my/backgrounds
- Equip frame: PUT /users/cosmetics/my/frame
- Equip background: PUT /users/cosmetics/my/background
- Admin CRUD: POST/PUT/DELETE /users/admin/cosmetics/frames and backgrounds
- Admin grant: POST /users/admin/cosmetics/grant
- Internal unlock: POST /users/internal/{user_id}/cosmetics/unlock
- Profile settings integration: PUT /users/me/settings with avatar_frame / chat_background
"""

import pytest
from fastapi.testclient import TestClient

from database import Base, get_db
from main import app
from auth import get_current_user
import models


# ---------------------------------------------------------------------------
# RBAC seed data
# ---------------------------------------------------------------------------

def _seed_cosmetics_permissions(db):
    """Seed RBAC permissions for cosmetics module so admin gets access."""
    for action in ("read", "create", "update", "delete"):
        db.add(models.Permission(module="cosmetics", action=action))
    db.commit()


# ---------------------------------------------------------------------------
# Cosmetic seed data
# ---------------------------------------------------------------------------

DEFAULT_FRAMES = [
    {"name": "Золотое свечение", "slug": "gold-glow", "type": "css", "css_class": "frame-gold-glow", "rarity": "common", "is_default": True},
    {"name": "Серебряное мерцание", "slug": "silver-shimmer", "type": "css", "css_class": "frame-silver-shimmer", "rarity": "common", "is_default": True},
    {"name": "Радужный контур", "slug": "rainbow-border", "type": "css", "css_class": "frame-rainbow-border", "rarity": "rare", "is_default": True},
]

NON_DEFAULT_FRAME = {
    "name": "Огненная пульсация", "slug": "fire-pulse", "type": "css",
    "css_class": "frame-fire-pulse", "rarity": "epic", "is_default": False, "is_seasonal": True,
}

DEFAULT_BACKGROUNDS = [
    {"name": "Тёмно-синий градиент", "slug": "dark-blue-gradient", "type": "css", "css_class": "bg-dark-blue", "rarity": "common", "is_default": True},
    {"name": "Фиолетовый туман", "slug": "purple-mist", "type": "css", "css_class": "bg-purple-mist", "rarity": "common", "is_default": True},
    {"name": "Золотой блик", "slug": "golden-flare", "type": "css", "css_class": "bg-golden-flare", "rarity": "rare", "is_default": True},
]

NON_DEFAULT_BACKGROUND = {
    "name": "Ночное небо", "slug": "night-sky", "type": "css",
    "css_class": "bg-night-sky", "rarity": "epic", "is_default": False,
}


def _seed_frames(db, frames=None):
    """Seed cosmetic frames into the DB. Returns list of ORM objects."""
    if frames is None:
        frames = DEFAULT_FRAMES
    objs = []
    for f in frames:
        obj = models.CosmeticFrame(**f)
        db.add(obj)
        objs.append(obj)
    db.commit()
    for o in objs:
        db.refresh(o)
    return objs


def _seed_backgrounds(db, backgrounds=None):
    """Seed cosmetic backgrounds into the DB. Returns list of ORM objects."""
    if backgrounds is None:
        backgrounds = DEFAULT_BACKGROUNDS
    objs = []
    for b in backgrounds:
        obj = models.CosmeticBackground(**b)
        db.add(obj)
        objs.append(obj)
    db.commit()
    for o in objs:
        db.refresh(o)
    return objs


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------

def _create_user(db, email="player@test.com", username="player", role="user"):
    """Create a user directly in DB."""
    user = models.User(
        email=email,
        username=username,
        hashed_password="hashed",
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_admin(db, email="admin@test.com", username="admin"):
    return _create_user(db, email=email, username=username, role="admin")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(test_engine, test_session_local):
    """DB session with tables created; tears down after test."""
    Base.metadata.create_all(bind=test_engine)
    session = test_session_local()
    _seed_cosmetics_permissions(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def user_client(db):
    """TestClient authenticated as regular user."""
    user = _create_user(db)

    def override_get_db():
        yield db

    def override_auth():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_auth
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_client(db):
    """TestClient authenticated as admin user."""
    admin = _create_admin(db)

    def override_get_db():
        yield db

    def override_auth():
        return admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_auth
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def anon_client(db):
    """TestClient without authentication (default dependency)."""
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    # Do NOT override get_current_user — it will require a token
    yield TestClient(app)
    app.dependency_overrides.clear()


# ===========================================================================
# 1. CATALOG ENDPOINTS
# ===========================================================================

class TestCatalogFrames:

    def test_list_frames_empty(self, user_client, db):
        """When no frames exist, returns empty list."""
        resp = user_client.get("/users/cosmetics/frames")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_list_frames_returns_seeded(self, user_client, db):
        """Returns all seeded frames."""
        _seed_frames(db)
        resp = user_client.get("/users/cosmetics/frames")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == len(DEFAULT_FRAMES)
        slugs = {item["slug"] for item in items}
        for f in DEFAULT_FRAMES:
            assert f["slug"] in slugs

    def test_list_frames_includes_non_default(self, user_client, db):
        """Non-default frames appear in the catalog too."""
        _seed_frames(db, DEFAULT_FRAMES + [NON_DEFAULT_FRAME])
        resp = user_client.get("/users/cosmetics/frames")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == len(DEFAULT_FRAMES) + 1

    def test_list_frames_response_structure(self, user_client, db):
        """Verify response item fields."""
        _seed_frames(db)
        resp = user_client.get("/users/cosmetics/frames")
        item = resp.json()["items"][0]
        for field in ("id", "name", "slug", "type", "css_class", "rarity", "is_default", "is_seasonal"):
            assert field in item


class TestCatalogBackgrounds:

    def test_list_backgrounds_empty(self, user_client, db):
        resp = user_client.get("/users/cosmetics/backgrounds")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_list_backgrounds_returns_seeded(self, user_client, db):
        _seed_backgrounds(db)
        resp = user_client.get("/users/cosmetics/backgrounds")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == len(DEFAULT_BACKGROUNDS)

    def test_list_backgrounds_response_structure(self, user_client, db):
        _seed_backgrounds(db)
        resp = user_client.get("/users/cosmetics/backgrounds")
        item = resp.json()["items"][0]
        for field in ("id", "name", "slug", "type", "css_class", "rarity", "is_default"):
            assert field in item


# ===========================================================================
# 2. USER COLLECTION
# ===========================================================================

class TestUserFrameCollection:

    def test_my_frames_returns_defaults(self, user_client, db):
        """New user sees all default frames."""
        _seed_frames(db, DEFAULT_FRAMES + [NON_DEFAULT_FRAME])
        resp = user_client.get("/users/cosmetics/my/frames")
        assert resp.status_code == 200
        data = resp.json()
        # Should see only the default frames (3), not the non-default one
        assert len(data["items"]) == len(DEFAULT_FRAMES)
        assert data["active_slug"] is None

    def test_my_frames_after_unlock(self, user_client, db):
        """After unlocking a non-default frame, it appears in my collection."""
        frames = _seed_frames(db, DEFAULT_FRAMES + [NON_DEFAULT_FRAME])
        non_default = [f for f in frames if f.slug == NON_DEFAULT_FRAME["slug"]][0]
        user = db.query(models.User).filter(models.User.role == "user").first()

        # Grant the non-default frame
        unlock = models.UserUnlockedFrame(user_id=user.id, frame_id=non_default.id, source="admin")
        db.add(unlock)
        db.commit()

        resp = user_client.get("/users/cosmetics/my/frames")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == len(DEFAULT_FRAMES) + 1
        slugs = {i["slug"] for i in items}
        assert NON_DEFAULT_FRAME["slug"] in slugs

    def test_my_frames_default_source(self, user_client, db):
        """Default frames have source='default'."""
        _seed_frames(db)
        resp = user_client.get("/users/cosmetics/my/frames")
        for item in resp.json()["items"]:
            assert item["source"] == "default"


class TestUserBackgroundCollection:

    def test_my_backgrounds_returns_defaults(self, user_client, db):
        _seed_backgrounds(db, DEFAULT_BACKGROUNDS + [NON_DEFAULT_BACKGROUND])
        resp = user_client.get("/users/cosmetics/my/backgrounds")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == len(DEFAULT_BACKGROUNDS)
        assert data["active_slug"] is None

    def test_my_backgrounds_after_unlock(self, user_client, db):
        bgs = _seed_backgrounds(db, DEFAULT_BACKGROUNDS + [NON_DEFAULT_BACKGROUND])
        non_default = [b for b in bgs if b.slug == NON_DEFAULT_BACKGROUND["slug"]][0]
        user = db.query(models.User).filter(models.User.role == "user").first()

        unlock = models.UserUnlockedBackground(user_id=user.id, background_id=non_default.id, source="admin")
        db.add(unlock)
        db.commit()

        resp = user_client.get("/users/cosmetics/my/backgrounds")
        items = resp.json()["items"]
        assert len(items) == len(DEFAULT_BACKGROUNDS) + 1
        slugs = {i["slug"] for i in items}
        assert NON_DEFAULT_BACKGROUND["slug"] in slugs


# ===========================================================================
# 3. EQUIP FRAME
# ===========================================================================

class TestEquipFrame:

    def test_equip_default_frame(self, user_client, db):
        """Equipping a default frame succeeds."""
        _seed_frames(db)
        resp = user_client.put("/users/cosmetics/my/frame", json={"slug": "gold-glow"})
        assert resp.status_code == 200
        assert resp.json()["active_frame"] == "gold-glow"

    def test_equip_unlocked_frame(self, user_client, db):
        """Equipping an unlocked non-default frame succeeds."""
        frames = _seed_frames(db, DEFAULT_FRAMES + [NON_DEFAULT_FRAME])
        non_default = [f for f in frames if f.slug == NON_DEFAULT_FRAME["slug"]][0]
        user = db.query(models.User).filter(models.User.role == "user").first()

        db.add(models.UserUnlockedFrame(user_id=user.id, frame_id=non_default.id, source="admin"))
        db.commit()

        resp = user_client.put("/users/cosmetics/my/frame", json={"slug": "fire-pulse"})
        assert resp.status_code == 200
        assert resp.json()["active_frame"] == "fire-pulse"

    def test_unequip_frame_with_null(self, user_client, db):
        """Sending slug=null unequips the frame."""
        _seed_frames(db)
        # First equip
        user_client.put("/users/cosmetics/my/frame", json={"slug": "gold-glow"})
        # Then unequip
        resp = user_client.put("/users/cosmetics/my/frame", json={"slug": None})
        assert resp.status_code == 200
        assert resp.json()["active_frame"] is None

    def test_equip_nonexistent_frame(self, user_client, db):
        """Equipping a slug that doesn't exist in the DB returns 404."""
        _seed_frames(db)
        resp = user_client.put("/users/cosmetics/my/frame", json={"slug": "nonexistent-frame"})
        assert resp.status_code == 404

    def test_equip_non_default_not_unlocked(self, user_client, db):
        """Equipping a non-default frame the user hasn't unlocked returns 403."""
        _seed_frames(db, DEFAULT_FRAMES + [NON_DEFAULT_FRAME])
        resp = user_client.put("/users/cosmetics/my/frame", json={"slug": "fire-pulse"})
        assert resp.status_code == 403


# ===========================================================================
# 4. EQUIP BACKGROUND
# ===========================================================================

class TestEquipBackground:

    def test_equip_default_background(self, user_client, db):
        _seed_backgrounds(db)
        resp = user_client.put("/users/cosmetics/my/background", json={"slug": "dark-blue-gradient"})
        assert resp.status_code == 200
        assert resp.json()["active_background"] == "dark-blue-gradient"

    def test_equip_unlocked_background(self, user_client, db):
        bgs = _seed_backgrounds(db, DEFAULT_BACKGROUNDS + [NON_DEFAULT_BACKGROUND])
        non_default = [b for b in bgs if b.slug == NON_DEFAULT_BACKGROUND["slug"]][0]
        user = db.query(models.User).filter(models.User.role == "user").first()

        db.add(models.UserUnlockedBackground(user_id=user.id, background_id=non_default.id, source="admin"))
        db.commit()

        resp = user_client.put("/users/cosmetics/my/background", json={"slug": "night-sky"})
        assert resp.status_code == 200
        assert resp.json()["active_background"] == "night-sky"

    def test_unequip_background_with_null(self, user_client, db):
        _seed_backgrounds(db)
        user_client.put("/users/cosmetics/my/background", json={"slug": "dark-blue-gradient"})
        resp = user_client.put("/users/cosmetics/my/background", json={"slug": None})
        assert resp.status_code == 200
        assert resp.json()["active_background"] is None

    def test_equip_nonexistent_background(self, user_client, db):
        _seed_backgrounds(db)
        resp = user_client.put("/users/cosmetics/my/background", json={"slug": "nonexistent-bg"})
        assert resp.status_code == 404

    def test_equip_non_default_not_unlocked(self, user_client, db):
        _seed_backgrounds(db, DEFAULT_BACKGROUNDS + [NON_DEFAULT_BACKGROUND])
        resp = user_client.put("/users/cosmetics/my/background", json={"slug": "night-sky"})
        assert resp.status_code == 403


# ===========================================================================
# 5. ADMIN CRUD — FRAMES
# ===========================================================================

class TestAdminCrudFrames:

    def test_create_frame(self, admin_client, db):
        resp = admin_client.post("/users/admin/cosmetics/frames", json={
            "name": "Новая рамка",
            "slug": "new-frame",
            "type": "css",
            "css_class": "frame-new",
            "rarity": "rare",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["slug"] == "new-frame"
        assert data["name"] == "Новая рамка"
        assert data["id"] is not None

    def test_create_frame_duplicate_slug(self, admin_client, db):
        _seed_frames(db)
        resp = admin_client.post("/users/admin/cosmetics/frames", json={
            "name": "Duplicate",
            "slug": "gold-glow",
            "type": "css",
            "css_class": "frame-dup",
            "rarity": "common",
        })
        assert resp.status_code == 409

    def test_update_frame(self, admin_client, db):
        frames = _seed_frames(db)
        frame_id = frames[0].id
        resp = admin_client.put(f"/users/admin/cosmetics/frames/{frame_id}", json={
            "name": "Обновлённая рамка",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Обновлённая рамка"

    def test_update_frame_not_found(self, admin_client, db):
        resp = admin_client.put("/users/admin/cosmetics/frames/99999", json={
            "name": "No such frame",
        })
        assert resp.status_code == 404

    def test_delete_frame(self, admin_client, db):
        frames = _seed_frames(db)
        frame_id = frames[0].id
        resp = admin_client.delete(f"/users/admin/cosmetics/frames/{frame_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # Verify it's gone
        assert db.query(models.CosmeticFrame).filter(models.CosmeticFrame.id == frame_id).first() is None

    def test_delete_frame_not_found(self, admin_client, db):
        resp = admin_client.delete("/users/admin/cosmetics/frames/99999")
        assert resp.status_code == 404

    def test_non_admin_cannot_create_frame(self, user_client, db):
        resp = user_client.post("/users/admin/cosmetics/frames", json={
            "name": "Hacker frame",
            "slug": "hacker",
            "type": "css",
            "css_class": "frame-hacker",
            "rarity": "common",
        })
        assert resp.status_code == 403

    def test_non_admin_cannot_update_frame(self, user_client, db):
        frames = _seed_frames(db)
        resp = user_client.put(f"/users/admin/cosmetics/frames/{frames[0].id}", json={
            "name": "Hacked",
        })
        assert resp.status_code == 403

    def test_non_admin_cannot_delete_frame(self, user_client, db):
        frames = _seed_frames(db)
        resp = user_client.delete(f"/users/admin/cosmetics/frames/{frames[0].id}")
        assert resp.status_code == 403


# ===========================================================================
# 6. ADMIN CRUD — BACKGROUNDS
# ===========================================================================

class TestAdminCrudBackgrounds:

    def test_create_background(self, admin_client, db):
        resp = admin_client.post("/users/admin/cosmetics/backgrounds", json={
            "name": "Новая подложка",
            "slug": "new-bg",
            "type": "css",
            "css_class": "bg-new",
            "rarity": "rare",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["slug"] == "new-bg"
        assert data["id"] is not None

    def test_create_background_duplicate_slug(self, admin_client, db):
        _seed_backgrounds(db)
        resp = admin_client.post("/users/admin/cosmetics/backgrounds", json={
            "name": "Duplicate",
            "slug": "dark-blue-gradient",
            "type": "css",
            "css_class": "bg-dup",
            "rarity": "common",
        })
        assert resp.status_code == 409

    def test_update_background(self, admin_client, db):
        bgs = _seed_backgrounds(db)
        bg_id = bgs[0].id
        resp = admin_client.put(f"/users/admin/cosmetics/backgrounds/{bg_id}", json={
            "name": "Обновлённая подложка",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Обновлённая подложка"

    def test_update_background_not_found(self, admin_client, db):
        resp = admin_client.put("/users/admin/cosmetics/backgrounds/99999", json={
            "name": "No such bg",
        })
        assert resp.status_code == 404

    def test_delete_background(self, admin_client, db):
        bgs = _seed_backgrounds(db)
        bg_id = bgs[0].id
        resp = admin_client.delete(f"/users/admin/cosmetics/backgrounds/{bg_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        assert db.query(models.CosmeticBackground).filter(models.CosmeticBackground.id == bg_id).first() is None

    def test_delete_background_not_found(self, admin_client, db):
        resp = admin_client.delete("/users/admin/cosmetics/backgrounds/99999")
        assert resp.status_code == 404

    def test_non_admin_cannot_create_background(self, user_client, db):
        resp = user_client.post("/users/admin/cosmetics/backgrounds", json={
            "name": "Hacker bg",
            "slug": "hacker-bg",
            "type": "css",
            "css_class": "bg-hacker",
            "rarity": "common",
        })
        assert resp.status_code == 403

    def test_non_admin_cannot_delete_background(self, user_client, db):
        bgs = _seed_backgrounds(db)
        resp = user_client.delete(f"/users/admin/cosmetics/backgrounds/{bgs[0].id}")
        assert resp.status_code == 403


# ===========================================================================
# 7. ADMIN GRANT
# ===========================================================================

class TestAdminGrant:

    def test_grant_frame_to_user(self, admin_client, db):
        """Admin can grant a frame to a user."""
        _seed_frames(db, [NON_DEFAULT_FRAME])
        user = _create_user(db, email="grantee@test.com", username="grantee")

        resp = admin_client.post("/users/admin/cosmetics/grant", json={
            "user_id": user.id,
            "cosmetic_type": "frame",
            "cosmetic_slug": "fire-pulse",
        })
        assert resp.status_code == 200
        assert resp.json()["granted"] is True

        # Verify user now has the frame unlocked
        unlock = db.query(models.UserUnlockedFrame).filter(
            models.UserUnlockedFrame.user_id == user.id,
        ).first()
        assert unlock is not None
        assert unlock.source == "admin"

    def test_grant_duplicate_is_idempotent(self, admin_client, db):
        """Granting same cosmetic twice doesn't error."""
        _seed_frames(db, [NON_DEFAULT_FRAME])
        user = _create_user(db, email="grantee@test.com", username="grantee")

        # Grant first time
        admin_client.post("/users/admin/cosmetics/grant", json={
            "user_id": user.id,
            "cosmetic_type": "frame",
            "cosmetic_slug": "fire-pulse",
        })
        # Grant second time — should not error
        resp = admin_client.post("/users/admin/cosmetics/grant", json={
            "user_id": user.id,
            "cosmetic_type": "frame",
            "cosmetic_slug": "fire-pulse",
        })
        assert resp.status_code == 200

    def test_grant_background_to_user(self, admin_client, db):
        _seed_backgrounds(db, [NON_DEFAULT_BACKGROUND])
        user = _create_user(db, email="grantee@test.com", username="grantee")

        resp = admin_client.post("/users/admin/cosmetics/grant", json={
            "user_id": user.id,
            "cosmetic_type": "background",
            "cosmetic_slug": "night-sky",
        })
        assert resp.status_code == 200
        assert resp.json()["granted"] is True

    def test_grant_nonexistent_user(self, admin_client, db):
        _seed_frames(db, [NON_DEFAULT_FRAME])
        resp = admin_client.post("/users/admin/cosmetics/grant", json={
            "user_id": 999999,
            "cosmetic_type": "frame",
            "cosmetic_slug": "fire-pulse",
        })
        assert resp.status_code == 404

    def test_grant_nonexistent_slug(self, admin_client, db):
        user = _create_user(db, email="grantee@test.com", username="grantee")
        resp = admin_client.post("/users/admin/cosmetics/grant", json={
            "user_id": user.id,
            "cosmetic_type": "frame",
            "cosmetic_slug": "nonexistent",
        })
        assert resp.status_code == 404

    def test_non_admin_cannot_grant(self, user_client, db):
        _seed_frames(db, [NON_DEFAULT_FRAME])
        user = db.query(models.User).filter(models.User.role == "user").first()
        resp = user_client.post("/users/admin/cosmetics/grant", json={
            "user_id": user.id,
            "cosmetic_type": "frame",
            "cosmetic_slug": "fire-pulse",
        })
        assert resp.status_code == 403


# ===========================================================================
# 8. INTERNAL UNLOCK
# ===========================================================================

class TestInternalUnlock:

    def test_unlock_frame(self, db):
        """Internal endpoint unlocks a frame for a user."""
        _seed_frames(db, [NON_DEFAULT_FRAME])
        user = _create_user(db)

        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        resp = client.post(f"/users/internal/{user.id}/cosmetics/unlock", json={
            "cosmetic_type": "frame",
            "cosmetic_slug": "fire-pulse",
            "source": "battlepass",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["unlocked"] is True
        assert data["reason"] is None

        # Verify in DB
        unlock = db.query(models.UserUnlockedFrame).filter(
            models.UserUnlockedFrame.user_id == user.id,
        ).first()
        assert unlock is not None
        assert unlock.source == "battlepass"

        app.dependency_overrides.clear()

    def test_unlock_background(self, db):
        _seed_backgrounds(db, [NON_DEFAULT_BACKGROUND])
        user = _create_user(db)

        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        resp = client.post(f"/users/internal/{user.id}/cosmetics/unlock", json={
            "cosmetic_type": "background",
            "cosmetic_slug": "night-sky",
            "source": "battlepass",
        })
        assert resp.status_code == 200
        assert resp.json()["unlocked"] is True

        app.dependency_overrides.clear()

    def test_unlock_duplicate_is_idempotent(self, db):
        """Unlocking the same cosmetic twice returns unlocked=False, no error."""
        _seed_frames(db, [NON_DEFAULT_FRAME])
        user = _create_user(db)

        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        # First unlock
        client.post(f"/users/internal/{user.id}/cosmetics/unlock", json={
            "cosmetic_type": "frame",
            "cosmetic_slug": "fire-pulse",
            "source": "battlepass",
        })
        # Second unlock
        resp = client.post(f"/users/internal/{user.id}/cosmetics/unlock", json={
            "cosmetic_type": "frame",
            "cosmetic_slug": "fire-pulse",
            "source": "battlepass",
        })
        assert resp.status_code == 200
        assert resp.json()["unlocked"] is False
        assert resp.json()["reason"] == "already_unlocked"

        app.dependency_overrides.clear()

    def test_unlock_nonexistent_slug(self, db):
        user = _create_user(db)

        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        resp = client.post(f"/users/internal/{user.id}/cosmetics/unlock", json={
            "cosmetic_type": "frame",
            "cosmetic_slug": "nonexistent",
            "source": "battlepass",
        })
        assert resp.status_code == 404

        app.dependency_overrides.clear()

    def test_unlock_nonexistent_user(self, db):
        _seed_frames(db, [NON_DEFAULT_FRAME])

        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        resp = client.post("/users/internal/999999/cosmetics/unlock", json={
            "cosmetic_type": "frame",
            "cosmetic_slug": "fire-pulse",
            "source": "battlepass",
        })
        assert resp.status_code == 404

        app.dependency_overrides.clear()


# ===========================================================================
# 9. PROFILE SETTINGS INTEGRATION
# ===========================================================================

class TestProfileSettingsCosmetics:

    def test_settings_with_valid_frame(self, user_client, db):
        """PUT /me/settings with a valid default frame slug succeeds."""
        _seed_frames(db)
        resp = user_client.put("/users/me/settings", json={"avatar_frame": "gold-glow"})
        assert resp.status_code == 200
        assert resp.json()["avatar_frame"] == "gold-glow"

    def test_settings_with_invalid_frame(self, user_client, db):
        """PUT /me/settings with a nonexistent frame slug returns 422."""
        _seed_frames(db)
        resp = user_client.put("/users/me/settings", json={"avatar_frame": "nonexistent"})
        assert resp.status_code == 422

    def test_settings_with_non_owned_frame(self, user_client, db):
        """PUT /me/settings with a non-default, non-unlocked frame returns 403."""
        _seed_frames(db, DEFAULT_FRAMES + [NON_DEFAULT_FRAME])
        resp = user_client.put("/users/me/settings", json={"avatar_frame": "fire-pulse"})
        assert resp.status_code == 403

    def test_settings_with_valid_background(self, user_client, db):
        """PUT /me/settings with a valid default background slug succeeds."""
        _seed_backgrounds(db)
        resp = user_client.put("/users/me/settings", json={"chat_background": "dark-blue-gradient"})
        assert resp.status_code == 200
        assert resp.json()["chat_background"] == "dark-blue-gradient"

    def test_settings_with_invalid_background(self, user_client, db):
        _seed_backgrounds(db)
        resp = user_client.put("/users/me/settings", json={"chat_background": "nonexistent"})
        assert resp.status_code == 422

    def test_settings_with_non_owned_background(self, user_client, db):
        _seed_backgrounds(db, DEFAULT_BACKGROUNDS + [NON_DEFAULT_BACKGROUND])
        resp = user_client.put("/users/me/settings", json={"chat_background": "night-sky"})
        assert resp.status_code == 403


# ===========================================================================
# 10. SCHEMA VALIDATION (negative cases)
# ===========================================================================

class TestSchemaValidation:

    def test_create_frame_invalid_type(self, admin_client, db):
        """Invalid frame type should return 422."""
        resp = admin_client.post("/users/admin/cosmetics/frames", json={
            "name": "Bad", "slug": "bad", "type": "invalid", "css_class": "x", "rarity": "common",
        })
        assert resp.status_code == 422

    def test_create_frame_invalid_rarity(self, admin_client, db):
        resp = admin_client.post("/users/admin/cosmetics/frames", json={
            "name": "Bad", "slug": "bad", "type": "css", "css_class": "x", "rarity": "mythic",
        })
        assert resp.status_code == 422

    def test_create_frame_css_type_missing_css_class(self, admin_client, db):
        """CSS frame without css_class should return 422."""
        resp = admin_client.post("/users/admin/cosmetics/frames", json={
            "name": "Bad", "slug": "bad", "type": "css", "rarity": "common",
        })
        assert resp.status_code == 422

    def test_create_frame_image_type_missing_url(self, admin_client, db):
        """Image frame without image_url should return 422."""
        resp = admin_client.post("/users/admin/cosmetics/frames", json={
            "name": "Bad", "slug": "bad", "type": "image", "rarity": "common",
        })
        assert resp.status_code == 422

    def test_create_background_invalid_type(self, admin_client, db):
        resp = admin_client.post("/users/admin/cosmetics/backgrounds", json={
            "name": "Bad", "slug": "bad", "type": "combo", "css_class": "x", "rarity": "common",
        })
        assert resp.status_code == 422

    def test_grant_invalid_cosmetic_type(self, admin_client, db):
        """Grant with invalid cosmetic_type returns 422."""
        resp = admin_client.post("/users/admin/cosmetics/grant", json={
            "user_id": 1,
            "cosmetic_type": "hat",
            "cosmetic_slug": "x",
        })
        assert resp.status_code == 422

    def test_unlock_invalid_cosmetic_type(self, db):
        user = _create_user(db)

        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        resp = client.post(f"/users/internal/{user.id}/cosmetics/unlock", json={
            "cosmetic_type": "hat",
            "cosmetic_slug": "x",
            "source": "battlepass",
        })
        assert resp.status_code == 422

        app.dependency_overrides.clear()


# ===========================================================================
# 11. EDGE CASES & SECURITY
# ===========================================================================

class TestEdgeCases:

    def test_delete_frame_unequips_active_users(self, admin_client, db):
        """When an admin deletes a frame, users who had it equipped get unequipped."""
        frames = _seed_frames(db, [NON_DEFAULT_FRAME])
        frame = frames[0]

        # Create a user who has this frame equipped
        user = _create_user(db, email="equipped@test.com", username="equipped")
        db.add(models.UserUnlockedFrame(user_id=user.id, frame_id=frame.id, source="admin"))
        user.avatar_frame = frame.slug
        db.commit()

        # Admin deletes the frame
        resp = admin_client.delete(f"/users/admin/cosmetics/frames/{frame.id}")
        assert resp.status_code == 200

        # Verify user's frame is now None
        db.refresh(user)
        assert user.avatar_frame is None

    def test_delete_background_unequips_active_users(self, admin_client, db):
        """When an admin deletes a background, users who had it equipped get unequipped."""
        bgs = _seed_backgrounds(db, [NON_DEFAULT_BACKGROUND])
        bg = bgs[0]

        user = _create_user(db, email="equipped@test.com", username="equipped")
        db.add(models.UserUnlockedBackground(user_id=user.id, background_id=bg.id, source="admin"))
        user.chat_background = bg.slug
        db.commit()

        resp = admin_client.delete(f"/users/admin/cosmetics/backgrounds/{bg.id}")
        assert resp.status_code == 200

        db.refresh(user)
        assert user.chat_background is None

    def test_sql_injection_in_frame_slug(self, user_client, db):
        """SQL injection attempt in slug should not crash."""
        _seed_frames(db)
        resp = user_client.put("/users/cosmetics/my/frame", json={"slug": "'; DROP TABLE cosmetic_frames; --"})
        assert resp.status_code in (404, 422)

    def test_update_frame_slug_uniqueness(self, admin_client, db):
        """Updating a frame's slug to an existing slug should return 409."""
        frames = _seed_frames(db)
        frame_id = frames[1].id
        existing_slug = frames[0].slug
        resp = admin_client.put(f"/users/admin/cosmetics/frames/{frame_id}", json={
            "slug": existing_slug,
        })
        assert resp.status_code == 409

    def test_update_background_slug_uniqueness(self, admin_client, db):
        bgs = _seed_backgrounds(db)
        bg_id = bgs[1].id
        existing_slug = bgs[0].slug
        resp = admin_client.put(f"/users/admin/cosmetics/backgrounds/{bg_id}", json={
            "slug": existing_slug,
        })
        assert resp.status_code == 409
