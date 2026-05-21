import fnmatch
import logging

logger = logging.getLogger(__name__)


def validate_target(target: str, scope: list[str], out_of_scope: list[str]) -> bool:
    """
    Returns True if target is in scope and not out of scope.
    Out-of-scope takes priority over scope.
    Supports exact matches and wildcard patterns (*.example.com).
    """
    target = target.strip().lower()

    # Strip protocol if present
    if "://" in target:
        target = target.split("://", 1)[1].split("/")[0]

    def matches_any(value: str, patterns: list[str]) -> bool:
        for pattern in patterns:
            pattern = pattern.strip().lower()
            if "://" in pattern:
                pattern = pattern.split("://", 1)[1].split("/")[0]
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
