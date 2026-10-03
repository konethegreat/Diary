"""The single-user gatekeeper (CLAUDE.md invariants 1, 3 and 4).

The repository is public, so these tests pin down who may reach what.
"""
import re

import pytest
from fastapi.testclient import TestClient

from backend.auth import PUBLIC_PATHS, PUBLIC_PREFIXES
from backend.config import settings
from helpers import OWNER, make_session_cookie

INTRUDER = "someone.else@example.com"


def _cookie(email: str) -> dict:
    return {"Cookie": f"session={make_session_cookie(email)}"}


def test_visitor_without_a_session_is_sent_to_login(remote_client):
    response = remote_client.get("/")
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/login"


def test_api_paths_answer_401_json_instead_of_redirecting(remote_client):
    response = remote_client.get("/api/reminders")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_dev_auto_login_is_limited_to_loopback(client, remote_client):
    assert client.get("/").status_code == 200  # owner on loopback is signed in
    assert remote_client.get("/").status_code in (302, 307)  # same mode, public address


@pytest.mark.parametrize("address", ["100.101.102.103", "fd7a:115c:a1e0::1234"])
def test_tailnet_addresses_are_trusted_only_when_opted_in(address, monkeypatch):
    from backend.main import app

    tailnet_client = TestClient(app, client=(address, 50000), follow_redirects=False)
    assert tailnet_client.get("/").status_code in (302, 307)  # TRUST_TAILNET is off

    monkeypatch.setattr(settings, "TRUST_TAILNET", True)
    assert tailnet_client.get("/").status_code == 200


def test_oauth_mode_never_auto_logs_in_anyone(client, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "oauth")
    response = TestClient(client.app, follow_redirects=False).get("/")
    assert response.status_code in (302, 307)


def test_a_session_for_another_account_is_rejected_with_403(remote_client):
    response = remote_client.get("/", headers=_cookie(INTRUDER))
    assert response.status_code == 403
    assert "single-user" in response.json()["detail"]


def test_the_owner_session_works_from_any_address(remote_client):
    assert remote_client.get("/", headers=_cookie(OWNER)).status_code == 200


def test_session_email_comparison_ignores_case_and_whitespace(remote_client):
    assert remote_client.get("/", headers=_cookie(f"  {OWNER.upper()} ")).status_code == 200


def test_public_paths_need_no_session(remote_client):
    for path in ("/login", "/manifest.json", "/sw.js", "/static/app.css"):
        assert remote_client.get(path).status_code == 200, path


def _all_routes(app):
    """(method, path) of every route, including those FastAPI nests in routers."""
    found = set()
    for path, operations in app.openapi()["paths"].items():
        found.update((method.upper(), path) for method in operations)
    for route in app.routes:  # also the ones left out of the schema (docs, PWA files)
        path = getattr(route, "path", "")
        for method in getattr(route, "methods", None) or ():
            if method not in ("HEAD", "OPTIONS"):
                found.add((method, path))
    return found


def test_every_route_is_closed_to_visitors_without_a_session(remote_client):
    checked = 0
    for method, path in sorted(_all_routes(remote_client.app)):
        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            continue
        url = re.sub(r"\{[^}]+\}", "1", path)  # fill in path parameters
        response = remote_client.request(method, url)
        assert response.status_code in (302, 307, 401), f"{method} {path}: {response.status_code}"
        checked += 1
    assert checked > 25  # guard: the sweep really found the application's routes


def test_pages_carry_the_security_headers(client, remote_client):
    for response in (client.get("/"), remote_client.get("/login")):
        headers = response.headers
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Referrer-Policy"] == "same-origin"
        assert "camera=()" in headers["Permissions-Policy"]
        csp = headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "unsafe-eval" not in csp
        script_src = re.search(r"script-src ([^;]*)", csp).group(1)
        assert "'unsafe-inline'" not in script_src  # no inline scripts


def test_hsts_is_sent_only_over_https(client):
    assert "Strict-Transport-Security" not in client.get("/").headers

    secure_client = TestClient(client.app, base_url="https://testserver")
    assert secure_client.get("/").headers["Strict-Transport-Security"].startswith("max-age=")
