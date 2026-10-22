"""
Tests for the account Settings page backend: privacy settings, site background,
and enforcement of the privacy rules.

Covers:
- GET/PUT /users/me/privacy (defaults, partial update, validation, security)
- PUT /users/me/settings site_background_url (+ GET /users/me)
- Wall view/post rules (all/friends/nobody, anonymous/friend/stranger/owner, blocks)
- Friends list visibility
- Friend request rules (nobody, blocks)
- show_online hiding in /online, /stats, /all, /{id}/friends, /{id}/profile
- viewer_permissions in GET /users/{id}/profile
- GET /users/{id}/presence-visibility
"""

from datetime import datetime

import pytest

import models
from auth import create_access_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db, user_id, username, **fields):
    user = models.User(
        id=user_id,
        email=f"{username}@test.com",
        username=username,
        hashed_password="fakehash",
        role="user",
        **fields,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _h(user):
    token = create_access_token(data={"sub": user.email}, role=user.role)
    return {"Authorization": f"Bearer {token}"}


def _set(db, user, **fields):
    for k, v in fields.items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)


def _befriend(db, a, b, status="accepted"):
    db.add(models.Friendship(user_id=a.id, friend_id=b.id, status=status))
    db.commit()


def _block(db, blocker, blocked):
    db.add(models.UserBlock(user_id=blocker.id, blocked_user_id=blocked.id))
    db.commit()


def _post(client, author, owner_id, content="<p>Привет</p>"):
    return client.post(
        f"/users/{owner_id}/wall/posts", json={"content": content}, headers=_h(author)
    )


@pytest.fixture()
def owner(db_session):
    return _make_user(db_session, 1, "owner")


@pytest.fixture()
def friend(db_session, owner):
    f = _make_user(db_session, 2, "friend")
    _befriend(db_session, f, owner)
    return f


@pytest.fixture()
def stranger(db_session):
    return _make_user(db_session, 3, "stranger")


# ===========================================================================
# GET / PUT /users/me/privacy
# ===========================================================================

class TestPrivacySettingsEndpoints:

    def test_defaults(self, client, owner):
        resp = client.get("/users/me/privacy", headers=_h(owner))
        assert resp.status_code == 200
        assert resp.json() == {
            "message_privacy": "all",
            "wall_view_privacy": "all",
            "wall_post_privacy": "all",
            "friends_list_privacy": "all",
            "friend_request_privacy": "all",
            "show_online": True,
        }

    def test_partial_update_changes_only_sent_fields(self, client, owner):
        resp = client.put(
            "/users/me/privacy",
            json={"wall_view_privacy": "friends", "show_online": False},
            headers=_h(owner),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["wall_view_privacy"] == "friends"
        assert body["show_online"] is False
        assert body["wall_post_privacy"] == "all"
        assert body["message_privacy"] == "all"

        again = client.get("/users/me/privacy", headers=_h(owner)).json()
        assert again == body

    def test_update_all_fields(self, client, owner):
        payload = {
            "message_privacy": "nobody",
            "wall_view_privacy": "nobody",
            "wall_post_privacy": "friends",
            "friends_list_privacy": "friends",
            "friend_request_privacy": "nobody",
            "show_online": False,
        }
        resp = client.put("/users/me/privacy", json=payload, headers=_h(owner))
        assert resp.status_code == 200
        assert resp.json() == payload

    def test_message_privacy_shared_with_legacy_endpoint(self, client, owner):
        client.put("/users/me/privacy", json={"message_privacy": "friends"}, headers=_h(owner))
        assert client.get("/users/1/message-privacy").json()["message_privacy"] == "friends"
        # Legacy endpoint keeps working and is reflected in the new one
        resp = client.put(
            "/users/me/message-privacy", json={"message_privacy": "nobody"}, headers=_h(owner)
        )
        assert resp.status_code == 200
        assert client.get("/users/me/privacy", headers=_h(owner)).json()["message_privacy"] == "nobody"

    @pytest.mark.parametrize("field", [
        "message_privacy", "wall_view_privacy", "wall_post_privacy",
        "friends_list_privacy", "friend_request_privacy",
    ])
    def test_invalid_value_rejected(self, client, owner, field):
        resp = client.put("/users/me/privacy", json={field: "everyone"}, headers=_h(owner))
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Недопустимое значение настройки приватности"

    def test_friend_request_privacy_rejects_friends(self, client, owner):
        resp = client.put(
            "/users/me/privacy", json={"friend_request_privacy": "friends"}, headers=_h(owner)
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Недопустимое значение настройки приватности"

    def test_null_value_rejected(self, client, owner):
        resp = client.put("/users/me/privacy", json={"wall_view_privacy": None}, headers=_h(owner))
        assert resp.status_code == 422
        resp = client.put("/users/me/privacy", json={"show_online": None}, headers=_h(owner))
        assert resp.status_code == 422

    def test_show_online_must_be_boolean(self, client, owner):
        resp = client.put("/users/me/privacy", json={"show_online": "yes"}, headers=_h(owner))
        assert resp.status_code == 422

    def test_invalid_value_does_not_partially_apply(self, client, owner):
        resp = client.put(
            "/users/me/privacy",
            json={"wall_view_privacy": "nobody", "wall_post_privacy": "bad"},
            headers=_h(owner),
        )
        assert resp.status_code == 422
        assert client.get("/users/me/privacy", headers=_h(owner)).json()["wall_view_privacy"] == "all"

    def test_sql_injection_like_value_rejected(self, client, owner):
        resp = client.put(
            "/users/me/privacy",
            json={"wall_view_privacy": "all'; DROP TABLE users; --"},
            headers=_h(owner),
        )
        assert resp.status_code == 422
        assert client.get("/users/me/privacy", headers=_h(owner)).status_code == 200

    def test_unauthenticated_get_rejected(self, client, owner):
        assert client.get("/users/me/privacy").status_code in (401, 403)

    def test_unauthenticated_put_rejected(self, client, owner):
        resp = client.put("/users/me/privacy", json={"wall_view_privacy": "nobody"})
        assert resp.status_code in (401, 403)

    def test_invalid_token_rejected(self, client, owner):
        resp = client.put(
            "/users/me/privacy",
            json={"wall_view_privacy": "nobody"},
            headers={"Authorization": "Bearer not-a-token"},
        )
        assert resp.status_code == 401


# ===========================================================================
# Site background (PUT /users/me/settings, GET /users/me)
# ===========================================================================

class TestSiteBackground:

    URL = "https://example.com/bg.webp"

    def test_set_and_returned_in_settings_and_me(self, client, owner):
        resp = client.put("/users/me/settings", json={"site_background_url": self.URL}, headers=_h(owner))
        assert resp.status_code == 200
        assert resp.json()["site_background_url"] == self.URL

        me = client.get("/users/me", headers=_h(owner))
        assert me.status_code == 200
        assert me.json()["site_background_url"] == self.URL

    def test_me_returns_null_when_unset(self, client, owner):
        me = client.get("/users/me", headers=_h(owner))
        assert me.json()["site_background_url"] is None

    @pytest.mark.parametrize("empty", ["", "   ", None])
    def test_clear(self, client, owner, empty):
        client.put("/users/me/settings", json={"site_background_url": self.URL}, headers=_h(owner))
        resp = client.put("/users/me/settings", json={"site_background_url": empty}, headers=_h(owner))
        assert resp.status_code == 200
        assert resp.json()["site_background_url"] is None
        assert client.get("/users/me", headers=_h(owner)).json()["site_background_url"] is None

    def test_other_settings_update_keeps_background(self, client, owner):
        client.put("/users/me/settings", json={"site_background_url": self.URL}, headers=_h(owner))
        resp = client.put("/users/me/settings", json={"post_color": "#fff"}, headers=_h(owner))
        assert resp.json()["site_background_url"] == self.URL

    @pytest.mark.parametrize("bad", [
        "javascript:alert(1)",
        "ftp://example.com/a.png",
        "data:image/png;base64,AAAA",
        "example.com/bg.png",
    ])
    def test_invalid_scheme_rejected(self, client, owner, bad):
        resp = client.put("/users/me/settings", json={"site_background_url": bad}, headers=_h(owner))
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Ссылка на фон сайта должна начинаться с http:// или https://"

    def test_css_breaking_characters_rejected(self, client, owner):
        resp = client.put(
            "/users/me/settings",
            json={"site_background_url": "https://example.com/a.png\");background:url(evil"},
            headers=_h(owner),
        )
        assert resp.status_code == 422

    def test_too_long_rejected(self, client, owner):
        url = "https://example.com/" + "a" * 600
        resp = client.put("/users/me/settings", json={"site_background_url": url}, headers=_h(owner))
        assert resp.status_code == 422

    def test_http_allowed(self, client, owner):
        resp = client.put(
            "/users/me/settings", json={"site_background_url": "http://example.com/x.jpg"}, headers=_h(owner)
        )
        assert resp.status_code == 200

    def test_unauthenticated_rejected(self, client, owner):
        resp = client.put("/users/me/settings", json={"site_background_url": self.URL})
        assert resp.status_code in (401, 403)


# ===========================================================================
# Wall view
# ===========================================================================

class TestWallView:

    def _get(self, client, viewer=None):
        headers = _h(viewer) if viewer else {}
        return client.get("/users/1/wall/posts", headers=headers)

    def test_all_visible_to_everyone(self, client, owner, friend, stranger):
        assert self._get(client).status_code == 200
        assert self._get(client, stranger).status_code == 200
        assert self._get(client, friend).status_code == 200

    def test_friends_only(self, client, db_session, owner, friend, stranger):
        _set(db_session, owner, wall_view_privacy="friends")
        resp = self._get(client)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Пользователь скрыл свою стену"
        assert self._get(client, stranger).status_code == 403
        assert self._get(client, friend).status_code == 200
        assert self._get(client, owner).status_code == 200

    def test_pending_friendship_is_not_friendship(self, client, db_session, owner, stranger):
        _befriend(db_session, stranger, owner, status="pending")
        _set(db_session, owner, wall_view_privacy="friends")
        assert self._get(client, stranger).status_code == 403

    def test_friendship_either_direction(self, client, db_session, owner, stranger):
        _befriend(db_session, owner, stranger)  # owner was the sender
        _set(db_session, owner, wall_view_privacy="friends")
        assert self._get(client, stranger).status_code == 200

    def test_nobody(self, client, db_session, owner, friend, stranger):
        _set(db_session, owner, wall_view_privacy="nobody")
        assert self._get(client).status_code == 403
        assert self._get(client, stranger).status_code == 403
        assert self._get(client, friend).status_code == 403
        assert self._get(client, owner).status_code == 200

    def test_no_admin_bypass(self, client, db_session, owner):
        admin = _make_user(db_session, 9, "admin9")
        _set(db_session, admin, role="admin")
        _set(db_session, owner, wall_view_privacy="nobody")
        assert self._get(client, admin).status_code == 403

    def test_missing_user_still_404(self, client, owner):
        assert client.get("/users/999/wall/posts").status_code == 404


# ===========================================================================
# Wall post
# ===========================================================================

class TestWallPost:

    def test_all_allows_stranger(self, client, owner, stranger):
        assert _post(client, stranger, 1).status_code == 200

    def test_anonymous_cannot_post(self, client, owner):
        resp = client.post("/users/1/wall/posts", json={"content": "<p>x</p>"})
        assert resp.status_code in (401, 403)

    def test_friends_only(self, client, db_session, owner, friend, stranger):
        _set(db_session, owner, wall_post_privacy="friends")
        resp = _post(client, stranger, 1)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Пользователь ограничил записи на своей стене"
        assert _post(client, friend, 1).status_code == 200
        assert _post(client, owner, 1).status_code == 200

    def test_nobody(self, client, db_session, owner, friend, stranger):
        _set(db_session, owner, wall_post_privacy="nobody")
        assert _post(client, friend, 1).status_code == 403
        assert _post(client, stranger, 1).status_code == 403
        assert _post(client, owner, 1).status_code == 200

    def test_owner_blocked_author(self, client, db_session, owner, friend):
        _block(db_session, owner, friend)
        resp = _post(client, friend, 1)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Вы не можете писать на стене этого пользователя"

    def test_author_blocked_owner(self, client, db_session, owner, stranger):
        _block(db_session, stranger, owner)
        resp = _post(client, stranger, 1)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Вы не можете писать на стене этого пользователя"

    def test_block_message_wins_over_audience(self, client, db_session, owner, stranger):
        _set(db_session, owner, wall_post_privacy="nobody")
        _block(db_session, owner, stranger)
        resp = _post(client, stranger, 1)
        assert resp.json()["detail"] == "Вы не можете писать на стене этого пользователя"

    def test_xss_still_sanitized(self, client, owner, stranger):
        resp = _post(client, stranger, 1, content="<p>hi</p><script>alert(1)</script>")
        assert resp.status_code == 200
        assert "<script>" not in resp.json()["content"]


# ===========================================================================
# Friends list
# ===========================================================================

class TestFriendsListVisibility:

    def _get(self, client, viewer=None):
        return client.get("/users/1/friends", headers=_h(viewer) if viewer else {})

    def test_all(self, client, owner, friend):
        resp = self._get(client)
        assert resp.status_code == 200
        assert [f["id"] for f in resp.json()] == [2]

    def test_friends_only(self, client, db_session, owner, friend, stranger):
        _set(db_session, owner, friends_list_privacy="friends")
        resp = self._get(client)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Пользователь скрыл список друзей"
        assert self._get(client, stranger).status_code == 403
        assert self._get(client, friend).status_code == 200
        assert self._get(client, owner).status_code == 200

    def test_nobody(self, client, db_session, owner, friend):
        _set(db_session, owner, friends_list_privacy="nobody")
        assert self._get(client, friend).status_code == 403
        assert self._get(client, owner).status_code == 200


# ===========================================================================
# Friend requests
# ===========================================================================

class TestFriendRequestRules:

    def _send(self, client, sender, target_id):
        return client.post("/users/friends/request", json={"friend_id": target_id}, headers=_h(sender))

    def test_default_allowed(self, client, owner, stranger):
        assert self._send(client, stranger, 1).status_code == 200

    def test_nobody(self, client, db_session, owner, stranger):
        _set(db_session, owner, friend_request_privacy="nobody")
        resp = self._send(client, stranger, 1)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Пользователь не принимает заявки в друзья"

    def test_target_blocked_sender(self, client, db_session, owner, stranger):
        _block(db_session, owner, stranger)
        resp = self._send(client, stranger, 1)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Нельзя отправить заявку этому пользователю"

    def test_sender_blocked_target(self, client, db_session, owner, stranger):
        _block(db_session, stranger, owner)
        resp = self._send(client, stranger, 1)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Нельзя отправить заявку этому пользователю"

    def test_existing_errors_kept(self, client, owner, friend, stranger):
        assert self._send(client, stranger, 3).status_code == 400   # self
        assert self._send(client, stranger, 999).status_code == 404  # missing
        assert self._send(client, friend, 1).status_code == 400      # already friends


# ===========================================================================
# show_online
# ===========================================================================

class TestShowOnline:

    @pytest.fixture()
    def hidden(self, db_session):
        return _make_user(
            db_session, 5, "hidden", show_online=False, last_active_at=datetime.utcnow()
        )

    @pytest.fixture()
    def visible(self, db_session):
        return _make_user(db_session, 6, "visible", last_active_at=datetime.utcnow())

    def test_online_list_excludes_hidden(self, client, hidden, visible):
        resp = client.get("/users/online")
        ids = [u["id"] for u in resp.json()["items"]]
        assert ids == [6]
        assert resp.json()["total"] == 1

    def test_stats_does_not_count_hidden(self, client, hidden, visible):
        body = client.get("/users/stats").json()
        assert body["online_users"] == 1
        assert body["total_users"] == 2

    def test_all_hides_last_active(self, client, hidden, visible):
        items = {u["id"]: u for u in client.get("/users/all").json()["items"]}
        assert items[5]["last_active_at"] is None
        assert items[6]["last_active_at"] is not None

    def test_all_owner_sees_own(self, client, hidden):
        items = {u["id"]: u for u in client.get("/users/all", headers=_h(hidden)).json()["items"]}
        assert items[5]["last_active_at"] is not None

    def test_friends_hides_last_active(self, client, db_session, hidden, visible, stranger):
        _befriend(db_session, hidden, visible)
        # list of `visible`'s friends contains `hidden`
        anon = {f["id"]: f for f in client.get("/users/6/friends").json()}
        assert anon[5]["last_active_at"] is None
        other = {f["id"]: f for f in client.get("/users/6/friends", headers=_h(stranger)).json()}
        assert other[5]["last_active_at"] is None
        # `hidden` still sees their own entry
        own = {f["id"]: f for f in client.get("/users/6/friends", headers=_h(hidden)).json()}
        assert own[5]["last_active_at"] is not None

    def test_profile_hides_last_active(self, client, hidden, stranger):
        assert client.get("/users/5/profile").json()["last_active_at"] is None
        assert client.get("/users/5/profile", headers=_h(stranger)).json()["last_active_at"] is None

    def test_profile_owner_sees_own(self, client, hidden):
        assert client.get("/users/5/profile", headers=_h(hidden)).json()["last_active_at"] is not None

    def test_profile_visible_user(self, client, visible):
        assert client.get("/users/6/profile").json()["last_active_at"] is not None


# ===========================================================================
# viewer_permissions in profile
# ===========================================================================

class TestViewerPermissions:

    def _vp(self, client, viewer=None, user_id=1):
        resp = client.get(f"/users/{user_id}/profile", headers=_h(viewer) if viewer else {})
        assert resp.status_code == 200
        return resp.json()

    def test_anonymous_defaults(self, client, owner):
        body = self._vp(client)
        assert body["viewer_permissions"] == {
            "can_view_wall": True,
            "can_post_wall": False,
            "can_view_friends": True,
            "can_send_friend_request": False,
        }
        assert body["post_stats"] is not None

    def test_stranger_defaults(self, client, owner, stranger):
        assert self._vp(client, stranger)["viewer_permissions"] == {
            "can_view_wall": True,
            "can_post_wall": True,
            "can_view_friends": True,
            "can_send_friend_request": True,
        }

    def test_owner_on_own_profile(self, client, db_session, owner):
        _set(db_session, owner, wall_view_privacy="nobody", wall_post_privacy="nobody",
             friends_list_privacy="nobody", friend_request_privacy="nobody")
        body = self._vp(client, owner)
        assert body["viewer_permissions"] == {
            "can_view_wall": True,
            "can_post_wall": True,
            "can_view_friends": True,
            "can_send_friend_request": False,
        }
        assert body["post_stats"] is not None

    def test_friend_with_friends_settings(self, client, db_session, owner, friend, stranger):
        _set(db_session, owner, wall_view_privacy="friends", wall_post_privacy="friends",
             friends_list_privacy="friends")
        vp_friend = self._vp(client, friend)["viewer_permissions"]
        assert vp_friend["can_view_wall"] is True
        assert vp_friend["can_post_wall"] is True
        assert vp_friend["can_view_friends"] is True
        assert vp_friend["can_send_friend_request"] is False  # already friends

        body = self._vp(client, stranger)
        assert body["viewer_permissions"]["can_view_wall"] is False
        assert body["viewer_permissions"]["can_post_wall"] is False
        assert body["viewer_permissions"]["can_view_friends"] is False
        assert body["post_stats"] is None

    def test_post_stats_hidden_for_anonymous_when_nobody(self, client, db_session, owner):
        _set(db_session, owner, wall_view_privacy="nobody")
        body = self._vp(client)
        assert body["post_stats"] is None
        assert body["viewer_permissions"]["can_view_wall"] is False

    def test_block_disables_post_and_request(self, client, db_session, owner, stranger):
        _block(db_session, owner, stranger)
        vp = self._vp(client, stranger)["viewer_permissions"]
        assert vp["can_post_wall"] is False
        assert vp["can_send_friend_request"] is False
        assert vp["can_view_wall"] is True

    def test_request_disabled_by_setting(self, client, db_session, owner, stranger):
        _set(db_session, owner, friend_request_privacy="nobody")
        assert self._vp(client, stranger)["viewer_permissions"]["can_send_friend_request"] is False

    def test_pending_request_disables_new_request(self, client, db_session, owner, stranger):
        _befriend(db_session, owner, stranger, status="pending")
        assert self._vp(client, stranger)["viewer_permissions"]["can_send_friend_request"] is False


# ===========================================================================
# GET /users/{id}/presence-visibility
# ===========================================================================

class TestPresenceVisibility:

    def test_default_true(self, client, owner):
        resp = client.get("/users/1/presence-visibility")
        assert resp.status_code == 200
        assert resp.json() == {"show_online": True}

    def test_hidden(self, client, db_session, owner):
        _set(db_session, owner, show_online=False)
        assert client.get("/users/1/presence-visibility").json() == {"show_online": False}

    def test_missing_user_404(self, client):
        assert client.get("/users/999/presence-visibility").status_code == 404

    def test_non_numeric_id_rejected(self, client):
        assert client.get("/users/1%20OR%201=1/presence-visibility").status_code == 422
