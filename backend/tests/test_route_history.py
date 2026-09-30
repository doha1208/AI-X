from fastapi.testclient import TestClient

from app.main import app


def csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.get("/auth/csrf").json()["csrf_token"]}


def login(client: TestClient, email: str) -> None:
    headers = csrf(client)
    assert client.post("/auth/signup", json={"email": email, "password": "password123"}, headers=headers).status_code == 201
    assert client.post("/auth/login", json={"email": email, "password": "password123", "remember_me": False}, headers=headers).status_code == 200


def route(index: int) -> dict:
    return {"start": {"label": f"출발 {index}", "lat": 37.5 + index / 1000, "lng": 127.0}, "end": {"label": f"도착 {index}", "lat": 37.6, "lng": 127.1 + index / 1000}}


def test_history_is_user_scoped_and_newest_first():
    first, second = TestClient(app), TestClient(app)
    login(first, "first@example.com")
    login(second, "second@example.com")
    assert first.post("/me/route-history", json=route(1), headers=csrf(first)).status_code == 200
    assert second.post("/me/route-history", json=route(2), headers=csrf(second)).status_code == 200
    history = first.get("/me/route-history")
    assert history.status_code == 200
    assert [item["start"]["label"] for item in history.json()["items"]] == ["출발 1"]


def test_history_upserts_caps_at_ten_and_respects_opt_out():
    client = TestClient(app)
    login(client, "history@example.com")
    for index in range(11):
        assert client.post("/me/route-history", json=route(index), headers=csrf(client)).status_code == 200
    assert len(client.get("/me/route-history").json()["items"]) == 10
    assert client.patch("/me/route-history/settings", json={"remember_route_history": False}, headers=csrf(client)).status_code == 200
    assert client.post("/me/route-history", json=route(99), headers=csrf(client)).status_code == 200
    labels = [item["start"]["label"] for item in client.get("/me/route-history").json()["items"]]
    assert "출발 99" not in labels


def test_history_mutations_require_csrf_and_delete_only_current_user():
    client = TestClient(app)
    login(client, "delete@example.com")
    assert client.post("/me/route-history", json=route(1)).status_code == 403
    assert client.post("/me/route-history", json=route(1), headers=csrf(client)).status_code == 200
    assert client.delete("/me/route-history", headers=csrf(client)).status_code == 204
    assert client.get("/me/route-history").json()["items"] == []
