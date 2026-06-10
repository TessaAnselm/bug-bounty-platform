from src.activities.scoring.risk import calculate_risk_score, auto_tag


def test_risk_score_prioritizes_high_value_api_asset():
    score = calculate_risk_score(
        "admin-api.example.com",
        "subdomain",
        403,
        ["Django", "JWT"],
    )

    assert score >= 60


def test_risk_score_is_capped_at_100():
    score = calculate_risk_score(
        "admin-internal-staging-api-auth-billing-backup.example.com",
        "api_endpoint",
        500,
        ["Jenkins", "GitLab", "Jira", "JWT"],
    )

    assert score == 100


def test_auto_tag_combines_value_and_technology_signals():
    tags = auto_tag("billing-api.example.com", "subdomain", ["OAuth"])

    assert "billing" in tags
    assert "api" in tags
    assert "auth" in tags
