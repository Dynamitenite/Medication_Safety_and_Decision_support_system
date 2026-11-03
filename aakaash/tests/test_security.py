# SOURCE: NOT IN PAPERS. FIXTURES ONLY. Cookie flags, headers and what error bodies leave out.
from fastapi.testclient import TestClient

from api import auth
from api.app import app

from test_accounts import PW, env  # noqa: F401  (env is a fixture)


def _login(client, password=PW):
    return client.post("/api/auth/login", json={"email": "a@example.com", "password": password})


def test_session_cookie_is_http_only_same_site_and_not_secure_over_plain_http(env):
    cookie = _login(TestClient(app)).headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie and "max-age=1209600" in cookie
    assert "secure" not in cookie


def test_session_cookie_is_secure_over_https_or_when_forced(env, monkeypatch):
    assert "secure" in _login(TestClient(app, base_url="https://testserver")).headers["set-cookie"].lower()
    monkeypatch.setenv("MEDSAFE_COOKIE_SECURE", "1")
    assert "secure" in _login(TestClient(app)).headers["set-cookie"].lower()


def test_validation_error_does_not_echo_the_password(env):
    r = _login(TestClient(app), "pw-7ch")
    assert r.status_code == 422
    assert "pw-7ch" not in r.text and "input" not in r.text
    assert r.json()["detail"][0]["loc"] == ["body", "password"]


def test_wrong_password_and_rate_limit_messages_name_no_internals(env):
    c = TestClient(app)
    _login(c)
    other = TestClient(app)
    for _ in range(auth.MAX_FAILURES):
        assert _login(other, "wrong password here").status_code == 401
    r = _login(other, "wrong password here")
    assert r.status_code == 429 and "Retry-After" in r.headers
    assert "argon" not in r.text.lower() and "sqlalchemy" not in r.text.lower() and "traceback" not in r.text.lower()


def test_api_responses_carry_basic_security_headers(env):
    r = TestClient(app).get("/api/auth/me")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"


def test_cors_only_allows_the_dev_server_origin(env):
    c = TestClient(app)
    ok = c.options("/api/profile", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    bad = c.options("/api/profile", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in bad.headers


def test_there_is_no_upload_endpoint():
    for path, ops in app.openapi()["paths"].items():
        for op in ops.values():
            assert "multipart/form-data" not in str(op.get("requestBody", "")), path
