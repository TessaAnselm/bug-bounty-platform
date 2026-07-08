from src.activities.storage.scope import validate_target


def test_empty_scope_rejects_everything():
    assert validate_target("example.com", [], []) is False


def test_exact_scope_allows_exact_target():
    assert validate_target("api.example.com", ["api.example.com"], []) is True


def test_wildcard_scope_allows_matching_subdomain():
    assert validate_target("api.example.com", ["*.example.com"], []) is True


def test_wildcard_scope_does_not_allow_unrelated_domain():
    assert validate_target("api.evil.com", ["*.example.com"], []) is False


def test_out_of_scope_overrides_in_scope():
    assert validate_target(
        "admin.example.com",
        ["*.example.com"],
        ["admin.example.com"],
    ) is False


def test_url_target_is_normalized_before_matching():
    assert validate_target(
        "https://api.example.com/v1/users",
        ["api.example.com"],
        [],
    ) is True


def test_url_scope_pattern_is_normalized_before_matching():
    assert validate_target(
        "api.example.com",
        ["https://api.example.com/path"],
        [],
    ) is True


# ── §2.2 — port must be stripped before matching (in-scope host:port must match) ──
def test_target_with_port_matches_exact_scope():
    assert validate_target("api.example.com:8443", ["api.example.com"], []) is True


def test_target_with_port_matches_wildcard_scope():
    assert validate_target("api.example.com:8443", ["*.example.com"], []) is True


def test_url_with_port_and_path_normalized():
    assert validate_target("https://api.example.com:8443/v1", ["*.example.com"], []) is True


def test_out_of_scope_with_port_still_rejected():
    assert validate_target(
        "admin.example.com:9000", ["*.example.com"], ["admin.example.com"]
    ) is False


# ── mixed case (already handled — pin it so a refactor can't drop it) ──
def test_matching_is_case_insensitive():
    assert validate_target("API.Example.COM", ["*.example.com"], []) is True
