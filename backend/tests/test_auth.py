from fastapi.testclient import TestClient

from app.main import app


def _csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/auth/csrf")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def _signup_and_login(
    client: TestClient, *, email: str = "test@example.com", remember_me: bool = False
) -> tuple[object, str]:
    headers = _csrf_headers(client)
    signup = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123"},
        headers=headers,
    )
    assert signup.status_code == 201

    login = client.post(
        "/auth/login",
        json={"email": email, "password": "password123", "remember_me": remember_me},
        headers=headers,
    )
    assert login.status_code == 200
    return login, client.cookies.get("refresh_token")


def test_login_uses_httponly_cookies_and_me_reads_the_access_cookie():
    client = TestClient(app)

    response, _ = _signup_and_login(client)
    body = response.json()

    assert body["email"] == "test@example.com"
    assert "access_token" not in body
    assert "refresh_token" not in body
    set_cookies = "\n".join(response.headers.get_list("set-cookie"))
    assert "access_token=" in set_cookies and "HttpOnly" in set_cookies
    assert "refresh_token=" in set_cookies and "HttpOnly" in set_cookies
    assert client.get("/auth/me").json()["email"] == "test@example.com"


def test_state_changing_auth_requests_require_a_matching_csrf_token():
    client = TestClient(app)
    _signup_and_login(client)

    assert client.post("/auth/logout").status_code == 403
    assert client.post("/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.post("/auth/logout", headers=_csrf_headers(client)).status_code == 204


def test_refresh_rotates_the_server_stored_session_and_rejects_the_old_cookie():
    client = TestClient(app)
    _, original_refresh = _signup_and_login(client)

    refreshed = client.post("/auth/refresh", headers=_csrf_headers(client))
    assert refreshed.status_code == 200
    rotated_refresh = client.cookies.get("refresh_token")
    assert rotated_refresh != original_refresh

    replay = TestClient(app)
    replay.cookies.set("refresh_token", original_refresh)
    replay.cookies.set("csrf_token", "replay-csrf")
    assert replay.post("/auth/refresh", headers={"X-CSRF-Token": "replay-csrf"}).status_code == 401


def test_logout_revokes_the_refresh_session_and_clears_authenticated_access():
    client = TestClient(app)
    _, refresh_token = _signup_and_login(client)

    assert client.post("/auth/logout", headers=_csrf_headers(client)).status_code == 204
    assert client.get("/auth/me").status_code == 401

    replay = TestClient(app)
    replay.cookies.set("refresh_token", refresh_token)
    replay.cookies.set("csrf_token", "logout-csrf")
    assert replay.post("/auth/refresh", headers={"X-CSRF-Token": "logout-csrf"}).status_code == 401


def test_remember_me_controls_the_refresh_cookie_lifetime():
    remembered_client = TestClient(app)
    _signup_and_login(remembered_client, email="remembered@example.com", remember_me=True)
    remembered = remembered_client.cookies.jar._cookies["testserver.local"]["/"]["refresh_token"]
    assert remembered.expires is not None

    session_client = TestClient(app)
    _signup_and_login(session_client, email="session@example.com", remember_me=False)
    session_cookie = session_client.cookies.jar._cookies["testserver.local"]["/"]["refresh_token"]
    assert session_cookie.expires is None
    assert session_client.post("/auth/refresh", headers=_csrf_headers(session_client)).status_code == 200
    rotated_session_cookie = session_client.cookies.jar._cookies["testserver.local"]["/"]["refresh_token"]
    assert rotated_session_cookie.expires is None


def test_login_wrong_password_fails():
    client = TestClient(app)
    headers = _csrf_headers(client)
    client.post("/auth/signup", json={"email": "wrong@example.com", "password": "password123"}, headers=headers)

    response = client.post(
        "/auth/login",
        json={"email": "wrong@example.com", "password": "bad-password"},
        headers=headers,
    )

    assert response.status_code == 401


def test_me_without_access_cookie_fails():
    assert TestClient(app).get("/auth/me").status_code == 401
