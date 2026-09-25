from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_signup_login_me_flow():
    signup_res = client.post(
        "/auth/signup", json={"email": "test@example.com", "password": "password123"}
    )
    assert signup_res.status_code == 201

    login_res = client.post(
        "/auth/login", json={"email": "test@example.com", "password": "password123"}
    )
    assert login_res.status_code == 200
    tokens = login_res.json()
    assert "access_token" in tokens

    me_res = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "test@example.com"


def test_login_wrong_password_fails():
    client.post(
        "/auth/signup", json={"email": "wrong@example.com", "password": "password123"}
    )
    res = client.post(
        "/auth/login", json={"email": "wrong@example.com", "password": "bad-password"}
    )
    assert res.status_code == 401


def test_me_without_token_fails():
    res = client.get("/auth/me")
    assert res.status_code == 401
