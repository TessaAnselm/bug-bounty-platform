import fnmatch
import logging

logger = logging.getLogger(__name__)


def _host(x: str) -> str:
    """Normalize a target or scope pattern to a bare host for matching.

    Strips (in order): surrounding space + case, scheme, path, and a trailing
    :port. Dropping the port is important — an in-scope asset surfaced as
    `api.example.com:8443` must still match a `api.example.com` / `*.example.com`
    scope entry (and the MITM proxy captures host:port from real traffic).
    """
    x = x.strip().lower()
    if "://" in x:
        x = x.split("://", 1)[1]
    x = x.split("/", 1)[0]            # drop path
    # drop a trailing numeric :port (host:8443 -> host); leaves bare hosts and
    # wildcards untouched (they have no `:digits` suffix).
    if ":" in x and x.rsplit(":", 1)[1].isdigit():
        x = x.rsplit(":", 1)[0]
    return x


def validate_target(target: str, scope: list[str], out_of_scope: list[str]) -> bool:
    """
    Returns True if target is in scope and not out of scope.
    Out-of-scope takes priority over scope.
    Supports exact matches and wildcard patterns (*.example.com).
    """
    target = _host(target)

    def matches_any(value: str, patterns: list[str]) -> bool:
        for pattern in patterns:
            pattern = _host(pattern)
            if fnmatch.fnmatch(value, pattern):
                return True
            # apex match: example.com in scope covers example.com itself
            if value == pattern:
                return True
        return False

    if not scope:
        logger.warning("validate_target: program has no scope defined — rejecting %s", target)
        return False

    if matches_any(target, out_of_scope):
        logger.info("validate_target: %s is out of scope — rejected", target)
        return False

    if matches_any(target, scope):
        return True

    logger.info("validate_target: %s not in scope — rejected", target)
    return False
