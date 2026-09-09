import uuid

import pytest

from app.core.security import create_access_token
from starlette.websockets import WebSocketDisconnect


def _room_name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _token(username: str) -> str:
    return create_access_token(username)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def room_with_two(client, register_user, get_token, auth_headers):
    def _make():
        creator, member = "alice", "bob"
        register_user(creator)
        register_user(member)
        creator_token = get_token(creator)
        member_token = get_token(member)
        creator_headers = auth_headers(creator_token)

        resp = client.post("/rooms/", json={"name": _room_name("room")}, headers=creator_headers)
        assert resp.status_code == 201, resp.text
        room_id = resp.json()["id"]

        resp = client.post(
            f"/rooms/{room_id}/invite",
            json={"username": member},
            headers=creator_headers,
        )
        assert resp.status_code == 201, resp.text
        return room_id, creator_token, member_token, creator_headers

    return _make


def test_ws_welcome_and_broadcast_messages(client, room_with_two, ws_connect):
    room_id, creator_token, member_token, _ = room_with_two()

    with ws_connect(room_id, creator_token) as ws_a, ws_connect(room_id, member_token) as ws_b:
        welcome_a = ws_a.receive_json()
        welcome_b = ws_b.receive_json()
        assert welcome_a["type"] == "welcome"
        assert welcome_a["room"]["id"] == room_id
        assert welcome_b["type"] == "welcome"

        ws_a.send_json({"type": "send_message", "content": "hello from alice"})
        event_a = ws_a.receive_json()
        event_b = ws_b.receive_json()
        assert event_a["type"] == event_b["type"] == "new_message"
        assert event_a["content"] == event_b["content"] == "hello from alice"
        assert event_a["username"] == "alice"
        assert event_a["id"] > 0
        assert event_a["room_id"] == room_id

        message_id = event_a["id"]

        ws_a.send_json({"type": "get_messages"})
        history = ws_a.receive_json()
        assert history["type"] == "history"
        assert any(m["id"] == message_id and m["content"] == "hello from alice" for m in history["messages"])


def test_ws_edit_and_delete_permissions(client, room_with_two, ws_connect):
    room_id, creator_token, member_token, _ = room_with_two()

    with ws_connect(room_id, creator_token) as ws_a, ws_connect(room_id, member_token) as ws_b:
        ws_a.receive_json()
        ws_b.receive_json()

        ws_a.send_json({"type": "send_message", "content": "original"})
        event = ws_a.receive_json()
        ws_b.receive_json()
        message_id = event["id"]

        ws_b.send_json({"type": "edit_message", "message_id": message_id, "content": "hacked"})
        err = ws_b.receive_json()
        assert err["type"] == "error" and "author" in err["detail"].lower()

        ws_a.send_json({"type": "edit_message", "message_id": message_id, "content": "edited"})
        edited_a = ws_a.receive_json()
        edited_b = ws_b.receive_json()
        assert edited_a["type"] == edited_b["type"] == "message_edited"
        assert edited_a["content"] == "edited"

        ws_b.send_json({"type": "delete_message", "message_id": message_id})
        err = ws_b.receive_json()
        assert err["type"] == "error" and "delete" in err["detail"].lower()

        ws_a.send_json({"type": "delete_message", "message_id": message_id})
        deleted_a = ws_a.receive_json()
        deleted_b = ws_b.receive_json()
        assert deleted_a["type"] == deleted_b["type"] == "message_deleted"
        assert deleted_a["id"] == message_id


def test_ws_empty_edit_rejected(client, room_with_two, ws_connect):
    room_id, creator_token, _, _ = room_with_two()

    with ws_connect(room_id, creator_token) as ws_a:
        ws_a.receive_json()
        ws_a.send_json({"type": "send_message", "content": "to-edit"})
        event = ws_a.receive_json()
        message_id = event["id"]

        ws_a.send_json({"type": "edit_message", "message_id": message_id, "content": "   "})
        err = ws_a.receive_json()
        assert err["type"] == "error" and "empty" in err["detail"].lower()


def test_ws_members_and_online(client, room_with_two, ws_connect):
    room_id, creator_token, member_token, _ = room_with_two()

    with ws_connect(room_id, creator_token) as ws_a, ws_connect(room_id, member_token) as ws_b:
        ws_a.receive_json()
        ws_b.receive_json()

        ws_a.send_json({"type": "get_members"})
        members = ws_a.receive_json()
        assert members["type"] == "members"
        by_name = {m["username"]: m for m in members["members"]}
        assert set(by_name) == {"alice", "bob"}
        assert all(m["online"] for m in by_name.values())


def test_ws_typing_broadcast(client, room_with_two, ws_connect):
    room_id, creator_token, member_token, _ = room_with_two()

    with ws_connect(room_id, creator_token) as ws_a, ws_connect(room_id, member_token) as ws_b:
        ws_a.receive_json()
        ws_b.receive_json()

        ws_a.send_json({"type": "typing"})
        event_a = ws_a.receive_json()
        event_b = ws_b.receive_json()
        assert event_a["type"] == event_b["type"] == "typing"
        assert event_a["username"] == "alice"


def test_ws_requests_and_approval(client, room_with_two, ws_connect, register_user):
    room_id, creator_token, _, _ = room_with_two()
    register_user("carol")
    carol_token = _token("carol")

    with ws_connect(room_id, creator_token) as ws_a:
        ws_a.receive_json()

        resp = client.post(f"/rooms/{room_id}/request", headers=_bearer(carol_token))
        assert resp.status_code == 201

        ws_a.send_json({"type": "get_requests"})
        requests = ws_a.receive_json()
        assert requests["type"] == "requests"
        carol_request = next(r for r in requests["requests"] if r["username"] == "carol")
        assert carol_request["status"] == "pending"

        ws_a.send_json({"type": "approve_request", "request_id": carol_request["id"]})
        joined = ws_a.receive_json()
        assert joined["type"] == "member_joined"
        assert joined["username"] == "carol"

        ws_a.send_json({"type": "approve_request", "request_id": carol_request["id"]})
        err = ws_a.receive_json()
        assert err["type"] == "error"


def test_ws_reject_request(client, room_with_two, ws_connect, register_user):
    room_id, creator_token, _, _ = room_with_two()
    register_user("dave")
    dave_token = _token("dave")

    with ws_connect(room_id, creator_token) as ws_a:
        ws_a.receive_json()
        client.post(f"/rooms/{room_id}/request", headers=_bearer(dave_token))

        ws_a.send_json({"type": "get_requests"})
        requests = ws_a.receive_json()
        dave_request = next(r for r in requests["requests"] if r["username"] == "dave")

        ws_a.send_json({"type": "reject_request", "request_id": dave_request["id"]})
        resolved = ws_a.receive_json()
        assert resolved["type"] == "request_resolved"
        assert resolved["status"] == "rejected"
        assert resolved["username"] == "dave"


def test_ws_only_creator_views_requests(client, room_with_two, ws_connect):
    room_id, _, member_token, _ = room_with_two()

    with ws_connect(room_id, member_token) as ws_b:
        ws_b.receive_json()
        ws_b.send_json({"type": "get_requests"})
        err = ws_b.receive_json()
        assert err["type"] == "error" and "creator" in err["detail"].lower()


def test_ws_leave_room(client, room_with_two, ws_connect):
    room_id, creator_token, member_token, _ = room_with_two()

    with ws_connect(room_id, creator_token) as ws_a, ws_connect(room_id, member_token) as ws_b:
        ws_a.receive_json()
        ws_b.receive_json()

        ws_b.send_json({"type": "leave_room"})
        left_a = ws_a.receive_json()
        left_b = ws_b.receive_json()
        assert left_a["type"] == left_b["type"] == "member_left"
        assert left_a["username"] == "bob"

        ws_b.send_json({"type": "leave_room"})
        err = ws_b.receive_json()
        assert err["type"] == "error" and "member" in err["detail"].lower()

        ws_a.send_json({"type": "leave_room"})
        err = ws_a.receive_json()
        assert err["type"] == "error" and "creator" in err["detail"].lower()


def test_ws_delete_room(client, room_with_two, ws_connect):
    room_id, creator_token, member_token, _ = room_with_two()

    with ws_connect(room_id, creator_token) as ws_a, ws_connect(room_id, member_token) as ws_b:
        ws_a.receive_json()
        ws_b.receive_json()

        ws_a.send_json({"type": "delete_room"})
        deleted_a = ws_a.receive_json()
        deleted_b = ws_b.receive_json()
        assert deleted_a["type"] == deleted_b["type"] == "room_deleted"
        assert deleted_a["room_id"] == room_id

    rooms = client.get("/rooms").json()
    assert all(r["id"] != room_id for r in rooms)


def test_ws_unknown_type(client, room_with_two, ws_connect):
    room_id, creator_token, _, _ = room_with_two()

    with ws_connect(room_id, creator_token) as ws_a:
        ws_a.receive_json()
        ws_a.send_json({"type": "what_is_this"})
        err = ws_a.receive_json()
        assert err["type"] == "error"
        assert "unknown" in err["detail"].lower()


def test_ws_invalid_token_rejected(client, ws_connect):
    with pytest.raises(WebSocketDisconnect):
        with ws_connect(1, "not-a-token"):
            pass


def test_ws_non_member_rejected(client, register_user, get_token, auth_headers, ws_connect):
    register_user("alice")
    register_user("bob")
    alice_headers = auth_headers(get_token("alice"))
    room_id = client.post("/rooms/", json={"name": _room_name("closed")}, headers=alice_headers).json()["id"]

    bob_token = get_token("bob")
    with pytest.raises(WebSocketDisconnect):
        with ws_connect(room_id, bob_token):
            pass


def test_ws_unknown_room_rejected(client, register_user, get_token, ws_connect):
    register_user("alice")
    with pytest.raises(WebSocketDisconnect):
        with ws_connect(999, get_token("alice")):
            pass


def test_rooms_unread(client, room_with_two, ws_connect):
    room_id, creator_token, member_token, _ = room_with_two()
    bob_headers = _bearer(member_token)

    # bob подключается -> last_read_at = now
    with ws_connect(room_id, member_token) as ws_b:
        ws_b.receive_json()
        ws_b.send_json({"type": "get_members"})
        ws_b.receive_json()

    # сообщений ещё нет -> непрочитанных нет
    assert client.get("/rooms/unread", headers=bob_headers).json() == []

    # alice пишет сообщение по ws
    with ws_connect(room_id, creator_token) as ws_a:
        ws_a.receive_json()
        ws_a.send_json({"type": "send_message", "content": "hi bob"})
        ws_a.receive_json()

    # у bob 1 непрочитанное
    unread = client.get("/rooms/unread", headers=bob_headers).json()
    assert any(r["room_id"] == room_id and r["unread"] == 1 for r in unread)

    # bob подключается снова -> отметил прочитанным -> счётчик обнулился
    with ws_connect(room_id, member_token) as ws_b:
        ws_b.receive_json()
        ws_b.send_json({"type": "get_members"})
        ws_b.receive_json()

    assert client.get("/rooms/unread", headers=bob_headers).json() == []
