import hashlib
import importlib


def _load_auth(monkeypatch, raw_key: str):
    monkeypatch.setenv("DASHBOARD_API_KEY", hashlib.sha256(raw_key.encode()).hexdigest())
    import src.api.auth as auth

    return importlib.reload(auth)


def test_key_matches_valid_key(monkeypatch):
    auth = _load_auth(monkeypatch, "test-secret")

    assert auth.key_matches("test-secret") is True


def test_key_rejects_invalid_key(monkeypatch):
    auth = _load_auth(monkeypatch, "test-secret")

    assert auth.key_matches("wrong-secret") is False


def test_session_token_round_trip(monkeypatch):
    auth = _load_auth(monkeypatch, "test-secret")

    token = auth.create_session_token()

    assert auth.verify_session_token(token) is True
    assert "test-secret" not in token


def test_tampered_session_token_is_rejected(monkeypatch):
    auth = _load_auth(monkeypatch, "test-secret")
    token = auth.create_session_token()
    payload, signature = token.split(".", 1)

    assert auth.verify_session_token(f"{payload}x.{signature}") is False


def test_expired_session_token_is_rejected(monkeypatch):
    auth = _load_auth(monkeypatch, "test-secret")
    monkeypatch.setattr(auth.time, "time", lambda: 1_000)
    token = auth.create_session_token()

    monkeypatch.setattr(auth.time, "time", lambda: 1_000 + auth.SESSION_MAX_AGE + 1)

    assert auth.verify_session_token(token) is False


def test_empty_config_fails_closed(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_KEY", "")
    import src.api.auth as auth

    auth = importlib.reload(auth)

    assert auth.key_matches("anything") is False
    assert auth.verify_session_token(auth.create_session_token()) is False
