from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


client = TestClient(app)

VALID_PROFILE = {
    "version": "pilot-v1",
    "name": "야간 보안등 우선",
    "description": "시연용 정책",
    "weights": {
        "day": {
            "cctv_count": 0.25,
            "streetlight_count": 0.10,
            "crime_rate": 0.30,
            "police_dist_m": 0.10,
            "store_count": 0.15,
            "bell_dist_m": 0.10,
        },
        "night": {
            "cctv_count": 0.15,
            "streetlight_count": 0.25,
            "crime_rate": 0.25,
            "police_dist_m": 0.10,
            "store_count": 0.10,
            "bell_dist_m": 0.15,
        },
    },
    "unknown_score": 50.0,
}


def _csrf_headers() -> dict[str, str]:
    response = client.get("/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def _authenticated_headers(email: str) -> dict[str, str]:
    csrf = _csrf_headers()
    assert client.post("/auth/signup", json={"email": email, "password": "password123"}, headers=csrf).status_code == 201
    assert client.post("/auth/login", json={"email": email, "password": "password123"}, headers=csrf).status_code == 200
    return _csrf_headers()


def test_anonymous_user_cannot_read_scoring_profiles():
    assert client.get("/admin/scoring-profiles").status_code == 401


def test_non_admin_cannot_create_scoring_profile(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "admin@example.com")
    headers = _authenticated_headers("member@example.com")

    response = client.post(
        "/admin/scoring-profiles",
        headers=headers,
        json=VALID_PROFILE,
    )

    assert response.status_code == 403


def test_admin_can_save_and_read_a_scoring_profile_draft(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "ADMIN@example.com")
    headers = _authenticated_headers("admin@example.com")

    created = client.post(
        "/admin/scoring-profiles",
        headers=headers,
        json=VALID_PROFILE,
    )

    assert created.status_code == 201
    assert created.json()["status"] == "draft"
    assert created.json()["created_by"] == "admin@example.com"

    listed = client.get(
        "/admin/scoring-profiles",
        headers=headers,
    )
    assert listed.status_code == 200
    assert [profile["version"] for profile in listed.json()] == ["pilot-v1"]

    active = client.get(
        "/admin/scoring-profiles/active",
        headers=headers,
    )
    assert active.status_code == 200
    assert active.json() is None


def test_invalid_profile_is_rejected_without_creating_a_draft(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "admin@example.com")
    headers = _authenticated_headers("admin@example.com")
    invalid = {
        **VALID_PROFILE,
        "weights": {
            **VALID_PROFILE["weights"],
            "day": {**VALID_PROFILE["weights"]["day"], "cctv_count": 0.26},
        },
    }

    created = client.post(
        "/admin/scoring-profiles",
        headers=headers,
        json=invalid,
    )
    listed = client.get(
        "/admin/scoring-profiles",
        headers=headers,
    )

    assert created.status_code == 422
    assert listed.json() == []


def test_admin_can_queue_a_draft_for_application(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "admin@example.com")
    headers = _authenticated_headers("admin@example.com")
    draft = client.post("/admin/scoring-profiles", headers=headers, json=VALID_PROFILE)

    queued = client.post(
        f"/admin/scoring-profiles/{draft.json()['id']}/apply",
        headers=headers,
    )

    assert queued.status_code == 202
    assert queued.json()["status"] == "queued"
    assert queued.json()["profile_id"] == draft.json()["id"]


def test_admin_apply_returns_complete_queued_build_lifecycle(monkeypatch):
    """An admin must be able to poll a new job without guessing missing state."""
    monkeypatch.setattr(settings, "admin_emails", "admin@example.com")
    headers = _authenticated_headers("admin@example.com")
    draft = client.post(
        "/admin/scoring-profiles",
        headers=headers,
        json=VALID_PROFILE,
    ).json()

    queued = client.post(
        f"/admin/scoring-profiles/{draft['id']}/apply",
        headers=headers,
    )

    assert queued.status_code == 202
    body = queued.json()
    assert body["profile_id"] == draft["id"]
    assert body["profile_version"] == "pilot-v1"
    assert body["status"] == "queued"
    assert body["artifact_version"] is None
    assert body["error_code"] is None
    assert body["created_at"]
    assert body["started_at"] is None
    assert body["finished_at"] is None


def test_non_admin_cannot_read_scoring_build_status(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "admin@example.com")
    headers = _authenticated_headers("member@example.com")

    response = client.get(
        "/admin/scoring-profiles/builds",
        headers=headers,
    )

    assert response.status_code == 403


def test_admin_can_read_build_list_and_404_for_missing_build(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "admin@example.com")
    headers = _authenticated_headers("admin@example.com")

    assert client.get("/admin/scoring-profiles/builds", headers=headers).json() == []
    assert client.get("/admin/scoring-profiles/builds/999", headers=headers).status_code == 404
