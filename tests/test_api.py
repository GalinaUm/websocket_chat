import pytest


def test_register_and_login_and_me(client, register_user, get_token, auth_headers):
    user = register_user("alice")
    assert user["username"] == "alice"
    assert user["email"] == "alice@example.com"

    token = get_token("alice")
    resp = client.get("/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"

    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_register_duplicate_username(client, register_user):
    register_user("alice")
    resp = client.post(
        "/auth/register",
        json={"email": "other@example.com", "username": "alice", "password": "secret123"},
    )
    assert resp.status_code == 400
    assert "already taken" in resp.json()["detail"]


def test_register_duplicate_email(client, register_user):
    register_user("alice")
    resp = client.post(
        "/auth/register",
        json={"email": "alice@example.com", "username": "alice2", "password": "secret123"},
    )
    assert resp.status_code == 400


def test_login_wrong_password(client, register_user):
    register_user("alice")
    resp = client.post("/auth/login", data={"username": "alice", "password": "wrong-pass"})
    assert resp.status_code == 400


def test_login_unknown_user(client):
    resp = client.post("/auth/login", data={"username": "nobody", "password": "secret123"})
    assert resp.status_code == 400


def test_create_room_and_list(client, register_user, get_token, auth_headers):
    register_user("alice")
    token = get_token("alice")
    headers = auth_headers(token)

    created = client.post("/rooms/", json={"name": "general"}, headers=headers)
    assert created.status_code == 201
    room_id = created.json()["id"]

    rooms = client.get("/rooms").json()
    assert any(r["id"] == room_id and r["name"] == "general" for r in rooms)

    stats = client.get("/rooms/stats", headers=headers).json()
    assert stats["total_rooms"] == 1
    assert stats["my_rooms"] == 1
    assert stats["max_rooms_per_user"] == 3

    assert room_id in client.get("/rooms/mine", headers=headers).json()


def test_create_room_unauthenticated(client):
    resp = client.post("/rooms/", json={"name": "no-token"})
    assert resp.status_code == 401


def test_room_limit_per_user(client, register_user, get_token, auth_headers):
    register_user("alice")
    token = get_token("alice")
    headers = auth_headers(token)

    for i in range(3):
        resp = client.post("/rooms/", json={"name": f"room-{i}"}, headers=headers)
        assert resp.status_code == 201, resp.text

    resp = client.post("/rooms/", json={"name": "room-extra"}, headers=headers)
    assert resp.status_code == 400
    assert "Limited to" in resp.json()["detail"]


def test_invite_member(client, register_user, get_token, auth_headers):
    register_user("alice")
    register_user("bob")
    register_user("carol")
    alice_token = get_token("alice")
    bob_token = get_token("bob")
    alice_headers = auth_headers(alice_token)

    room_id = client.post("/rooms/", json={"name": "team"}, headers=alice_headers).json()["id"]

    resp = client.post(f"/rooms/{room_id}/invite", json={"username": "bob"}, headers=alice_headers)
    assert resp.status_code == 201

    assert room_id in client.get("/rooms/mine", headers=auth_headers(bob_token)).json()

    # не-создатель не может приглашать
    resp = client.post(
        f"/rooms/{room_id}/invite",
        json={"username": "carol"},
        headers=auth_headers(bob_token),
    )
    assert resp.status_code == 403


def test_invite_unknown_user(client, register_user, get_token, auth_headers):
    register_user("alice")
    alice_headers = auth_headers(get_token("alice"))
    room_id = client.post("/rooms/", json={"name": "team"}, headers=alice_headers).json()["id"]

    resp = client.post(
        f"/rooms/{room_id}/invite",
        json={"username": "ghost"},
        headers=alice_headers,
    )
    assert resp.status_code == 404


def test_knock_and_duplicate(client, register_user, get_token, auth_headers):
    register_user("alice")
    register_user("bob")
    alice_headers = auth_headers(get_token("alice"))
    bob_headers = auth_headers(get_token("bob"))

    room_id = client.post("/rooms/", json={"name": "knock"}, headers=alice_headers).json()["id"]

    resp = client.post(f"/rooms/{room_id}/request", headers=bob_headers)
    assert resp.status_code == 201

    resp = client.post(f"/rooms/{room_id}/request", headers=bob_headers)
    assert resp.status_code == 400
    assert "already sent" in resp.json()["detail"]


def test_knock_as_member_complains(client, register_user, get_token, auth_headers):
    register_user("alice")
    register_user("bob")
    alice_headers = auth_headers(get_token("alice"))
    bob_headers = auth_headers(get_token("bob"))

    room_id = client.post("/rooms/", json={"name": "member"}, headers=alice_headers).json()["id"]
    client.post(f"/rooms/{room_id}/invite", json={"username": "bob"}, headers=alice_headers)

    resp = client.post(f"/rooms/{room_id}/request", headers=bob_headers)
    assert resp.status_code == 400
    assert "member" in resp.json()["detail"]


def test_users_search(client, register_user):
    register_user("alice")
    register_user("bob")

    resp = client.get("/users/?q=ali").json()
    assert [u["username"] for u in resp] == ["alice"]

    resp = client.get("/users/?q=bob").json()
    assert [u["username"] for u in resp] == ["bob"]

    resp = client.get("/users/?q=zzz").json()
    assert resp == []