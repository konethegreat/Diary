"""Security headers cover authentication failures as well as accepted requests."""
import pytest
from fastapi.testclient import TestClient
from helpers import OWNER, make_session_cookie


@pytest.mark.parametrize("path,email,status", [
    ("/login", None, 200),
    ("/api/reminders", None, 401),
    ("/", None, 307),
    ("/", "other@example.test", 403),
    ("/", OWNER, 200),
])
def test_headers_cover_success_redirects_and_denials(remote_client, path, email, status):
    client = TestClient(remote_client.app, base_url="https://testserver",
                        client=("203.0.113.7", 50000), follow_redirects=False)
    headers = {"Cookie": f"session={make_session_cookie(email)}"} if email else {}
    response = client.get(path, headers=headers)
    assert response.status_code == status
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert "max-age=" in response.headers["Strict-Transport-Security"]


def test_spoofed_forwarded_address_cannot_enable_local_login(remote_client):
    response = remote_client.get("/api/reminders", headers={"X-Forwarded-For": "127.0.0.1"})
    assert response.status_code == 401


def test_tampered_session_is_rejected(remote_client):
    response = remote_client.get("/api/reminders", headers={
        "Cookie": f"session={make_session_cookie(OWNER)}tampered"
    })
    assert response.status_code == 401
