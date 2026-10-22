"""
Tests for social bell notifications published by user-service to the
`general_notifications` queue (category "social"):

- friend request sent      -> target gets `friend_request`
- friend request accepted  -> requester gets `friend_accepted`
- someone posts on a wall  -> wall owner gets `wall_post` (not for own posts)
- a failing publisher never fails the HTTP request
- payload shape built by producer.send_social_notification
"""

from unittest.mock import patch

import pytest

import models
from auth import create_access_token


def _make_user(db, user_id, username):
    user = models.User(
        id=user_id,
        email=f"{username}@test.com",
        username=username,
        hashed_password="fakehash",
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _h(user):
    token = create_access_token(data={"sub": user.email}, role=user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def alice(db_session):
    return _make_user(db_session, 1, "alice")


@pytest.fixture()
def bob(db_session):
    return _make_user(db_session, 2, "bob")


# ---------------------------------------------------------------------------
# Endpoint triggers
# ---------------------------------------------------------------------------

class TestFriendRequestNotification:

    def test_request_notifies_target(self, client, alice, bob, social_notify_mock):
        resp = client.post("/users/friends/request", json={"friend_id": bob.id}, headers=_h(alice))
        assert resp.status_code == 200
        friendship_id = resp.json()["id"]
        social_notify_mock.assert_called_once_with(
            bob.id,
            "alice хочет добавить вас в друзья",
            "friend_request",
            {"from_user_id": alice.id, "from_username": "alice", "friendship_id": friendship_id},
        )

    def test_failed_request_does_not_notify(self, client, alice, social_notify_mock):
        resp = client.post("/users/friends/request", json={"friend_id": alice.id}, headers=_h(alice))
        assert resp.status_code == 400
        social_notify_mock.assert_not_called()

    def test_accept_notifies_requester(self, client, db_session, alice, bob, social_notify_mock):
        resp = client.post("/users/friends/request", json={"friend_id": bob.id}, headers=_h(alice))
        friendship_id = resp.json()["id"]
        social_notify_mock.reset_mock()

        resp = client.put(f"/users/friends/request/{friendship_id}/accept", headers=_h(bob))
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"
        social_notify_mock.assert_called_once_with(
            alice.id,
            "bob теперь у вас в друзьях",
            "friend_accepted",
            {"user_id": bob.id, "username": "bob"},
        )

    def test_accept_by_wrong_user_does_not_notify(self, client, alice, bob, social_notify_mock):
        resp = client.post("/users/friends/request", json={"friend_id": bob.id}, headers=_h(alice))
        friendship_id = resp.json()["id"]
        social_notify_mock.reset_mock()
        resp = client.put(f"/users/friends/request/{friendship_id}/accept", headers=_h(alice))
        assert resp.status_code == 403
        social_notify_mock.assert_not_called()


class TestWallPostNotification:

    def test_post_on_other_wall_notifies_owner(self, client, alice, bob, social_notify_mock):
        resp = client.post(f"/users/{bob.id}/wall/posts", json={"content": "<p>Привет</p>"}, headers=_h(alice))
        assert resp.status_code == 200
        post_id = resp.json()["id"]
        social_notify_mock.assert_called_once_with(
            bob.id,
            "Новая запись на вашей стене от alice",
            "wall_post",
            {"author_id": alice.id, "author_username": "alice", "post_id": post_id},
        )

    def test_own_wall_post_does_not_notify(self, client, alice, social_notify_mock):
        resp = client.post(f"/users/{alice.id}/wall/posts", json={"content": "<p>Моё</p>"}, headers=_h(alice))
        assert resp.status_code == 200
        social_notify_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Publisher failures never break the request
# ---------------------------------------------------------------------------

class TestPublisherFailureIsolated:

    @pytest.fixture()
    def real_sender_broken_rabbit(self):
        """Use the real send_social_notification with RabbitMQ failing."""
        import producer
        with patch("main.send_social_notification", producer.send_social_notification), \
                patch("producer._publish_general", side_effect=ConnectionError("rabbitmq down")) as pub:
            yield pub

    def test_friend_request_survives(self, client, alice, bob, real_sender_broken_rabbit):
        resp = client.post("/users/friends/request", json={"friend_id": bob.id}, headers=_h(alice))
        assert resp.status_code == 200
        real_sender_broken_rabbit.assert_called_once()

    def test_accept_survives(self, client, alice, bob, real_sender_broken_rabbit):
        fid = client.post("/users/friends/request", json={"friend_id": bob.id}, headers=_h(alice)).json()["id"]
        resp = client.put(f"/users/friends/request/{fid}/accept", headers=_h(bob))
        assert resp.status_code == 200
        assert real_sender_broken_rabbit.call_count == 2

    def test_wall_post_survives(self, client, alice, bob, real_sender_broken_rabbit):
        resp = client.post(f"/users/{bob.id}/wall/posts", json={"content": "<p>x</p>"}, headers=_h(alice))
        assert resp.status_code == 200
        real_sender_broken_rabbit.assert_called_once()


# ---------------------------------------------------------------------------
# Payload shape
# ---------------------------------------------------------------------------

def test_send_social_notification_payload():
    import producer
    with patch("producer._publish_general") as pub:
        producer.send_social_notification(5, "msg", "friend_request", {"from_user_id": 1})
    pub.assert_called_once_with({
        "target_type": "user",
        "target_value": 5,
        "message": "msg",
        "category": "social",
        "ws_type": "friend_request",
        "ws_data": {"from_user_id": 1},
    })


def test_send_social_notification_swallows_errors():
    import producer
    with patch("producer._publish_general", side_effect=RuntimeError("boom")):
        producer.send_social_notification(5, "msg", "wall_post", {})  # must not raise
