"""§2.4 — the MCP exchanges resource must mask stored secrets before AI review.
The redaction functions are tested elsewhere; this pins the resource's own
mapping so a future refactor can't silently expose raw tokens to Claude Code."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from src.mcp.resources.exchanges import _exchange_dict


def _ex(**kw):
    base = dict(
        id=uuid4(),
        request_method="POST",
        request_url="https://api.example.com/login",
        request_headers={"Cookie": "sess=SECRET_COOKIE", "Authorization": "Bearer TOKEN123", "User-Agent": "ua"},
        request_body='{"password":"hunter2"}',
        response_status=200,
        response_time_ms=42,
        response_body='{"access_token":"abcXYZ","email":"a@b.com"}',
        label="acct A",
        note=None,
        created_at=datetime.now(timezone.utc),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_request_headers_are_masked():
    d = _exchange_dict(_ex())
    assert d["request_headers"]["Cookie"] == "<redacted>"
    assert d["request_headers"]["Authorization"] == "<redacted>"
    assert d["request_headers"]["User-Agent"] == "ua"
    # no raw secret leaks anywhere in the serialized view
    assert "SECRET_COOKIE" not in str(d)
    assert "TOKEN123" not in str(d)


def test_request_and_response_bodies_are_scrubbed():
    d = _exchange_dict(_ex())
    assert "hunter2" not in d["request_body"]        # password value scrubbed
    assert "abcXYZ" not in d["response_excerpt"]      # access_token value scrubbed


def test_response_excerpt_is_capped():
    big = "A" * 10000
    d = _exchange_dict(_ex(response_body=big))
    assert len(d["response_excerpt"]) <= 4000
