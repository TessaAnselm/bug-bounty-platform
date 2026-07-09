"""Repeater response 'pretty' view — pretty-print JSON, fall back to raw."""
import json

from src.api.routers.repeater import _pretty_body


def test_pretty_prints_json_object():
    out = _pretty_body('{"a":1,"b":{"c":2}}', {"Content-Type": "application/json"})
    assert out is not None
    assert '"a": 1' in out and "\n" in out          # indented
    assert json.loads(out) == {"a": 1, "b": {"c": 2}}


def test_pretty_detects_json_without_content_type():
    # detected by the leading '{' / '[' even if header is missing/generic
    assert _pretty_body('[1,2,3]', {}) == "[\n  1,\n  2,\n  3\n]"


def test_html_body_returns_none():
    assert _pretty_body("<!DOCTYPE html><html></html>", {"Content-Type": "text/html"}) is None


def test_invalid_json_returns_none():
    assert _pretty_body("{not valid json", {"Content-Type": "application/json"}) is None


def test_empty_body_returns_none():
    assert _pretty_body("", {}) is None
