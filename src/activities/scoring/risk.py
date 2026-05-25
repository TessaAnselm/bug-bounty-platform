"""
Asset risk scorer — assigns a 0-100 priority score to each asset.

Higher score = more interesting to investigate first.
Used to populate the triage queue in the dashboard.
"""

# Keywords in the asset value that suggest high-value targets.
# Grouped by signal strength so scores are additive but bounded.
_HIGH_VALUE_KEYWORDS = [
    "admin", "administrator", "superuser", "root",
    "internal", "intranet", "corp", "corporate",
    "staging", "stage", "stg", "uat", "preprod", "pre-prod",
    "dev", "develop", "development", "sandbox",
    "api", "rest", "graphql", "grpc", "rpc",
    "auth", "login", "signin", "sso", "oauth", "saml",
    "upload", "file", "files", "media", "cdn",
    "billing", "payment", "pay", "checkout", "invoice",
    "secret", "config", "config", "vault", "key", "token",
    "backup", "bak", "old", "legacy", "archive",
    "debug", "test", "testing", "demo",
    "vpn", "gateway", "proxy", "mgmt", "management",
]

_HIGH_VALUE_TECH = [
    "jenkins", "gitlab", "jira", "confluence", "grafana",
    "kibana", "elasticsearch", "redis", "mongodb",
    "phpMyAdmin", "adminer", "wordpress", "drupal",
    "spring", "django", "flask", "rails",
    "jwt", "oauth", "ldap", "saml",
]


def calculate_risk_score(
    value: str,
    asset_type: str,
    http_status: int | None,
    technologies: list[str],
) -> int:
    """
    Returns an integer 0–100.

    Scoring breakdown:
      - High-value keyword in asset name  +15 per match (capped at +45)
      - Asset type signals                +10–20
      - HTTP status signals               +5–20
      - Technology stack signals          +10 per match (capped at +20)
    """
    score = 0
    value_lower = value.lower()

    # Keyword signals — more matches = higher score, capped at 45
    keyword_hits = sum(1 for kw in _HIGH_VALUE_KEYWORDS if kw in value_lower)
    score += min(45, keyword_hits * 15)

    # Asset type signals
    type_scores = {
        "api_endpoint": 20,
        "url": 10,
        "subdomain": 8,
        "ip": 5,
        "other": 0,
        "mobile": 0,
    }
    score += type_scores.get(asset_type, 0)

    # HTTP status signals
    if http_status:
        if http_status == 200:
            score += 5    # alive and accessible
        elif http_status == 403:
            score += 15   # gated — worth probing for bypass
        elif http_status == 401:
            score += 12   # auth required — worth testing auth flows
        elif http_status == 500:
            score += 20   # server error — likely interesting behavior
        elif http_status == 302:
            score += 8    # redirect — may expose internal endpoints

    # Technology stack signals
    if technologies:
        tech_lower = [t.lower() for t in technologies]
        tech_hits = sum(1 for t in _HIGH_VALUE_TECH if any(t in s for s in tech_lower))
        score += min(20, tech_hits * 10)

    return min(100, score)


def auto_tag(value: str, asset_type: str, technologies: list[str]) -> list[str]:
    """
    Returns a list of tags based on asset value and tech stack.
    These are the starting tags — humans can add/remove from the dashboard.
    """
    tags = []
    value_lower = value.lower()
    tech_lower = [t.lower() for t in (technologies or [])]

    if any(kw in value_lower for kw in ["admin", "administrator", "superuser"]):
        tags.append("admin")
    if any(kw in value_lower for kw in ["api", "rest", "graphql", "grpc", "rpc"]):
        tags.append("api")
    if any(kw in value_lower for kw in ["auth", "login", "signin", "sso", "oauth", "saml"]):
        tags.append("auth")
    if any(kw in value_lower for kw in ["staging", "stage", "stg", "uat", "preprod"]):
        tags.append("staging")
    if any(kw in value_lower for kw in ["dev", "develop", "development", "sandbox", "debug"]):
        tags.append("dev")
    if any(kw in value_lower for kw in ["upload", "file", "files", "media"]):
        tags.append("upload")
    if any(kw in value_lower for kw in ["billing", "payment", "pay", "checkout", "invoice"]):
        tags.append("billing")
    if any(kw in value_lower for kw in ["internal", "intranet", "corp", "vpn", "mgmt"]):
        tags.append("internal")
    if any(kw in value_lower for kw in ["backup", "bak", "old", "legacy", "archive"]):
        tags.append("legacy")
    if asset_type == "api_endpoint":
        if "api" not in tags:
            tags.append("api")

    # Tech stack tags
    if any(t in " ".join(tech_lower) for t in ["jwt", "oauth", "saml", "ldap"]):
        if "auth" not in tags:
            tags.append("auth")
    if any(t in " ".join(tech_lower) for t in ["wordpress", "drupal", "joomla"]):
        tags.append("cms")
    if any(t in " ".join(tech_lower) for t in ["jenkins", "gitlab", "jira", "confluence"]):
        tags.append("devtools")

    return tags
