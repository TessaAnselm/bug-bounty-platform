from temporalio import activity
from temporalio.exceptions import ApplicationError
from sqlalchemy.orm import Session
from src.db.session import engine
from src.db.models import Program, ProgramScore


def _payout_score(max_payout: int | None) -> float:
    if not max_payout:
        return 30.0
    if max_payout >= 50000:
        return 100.0
    if max_payout >= 10000:
        return 80.0
    if max_payout >= 5000:
        return 65.0
    if max_payout >= 1000:
        return 50.0
    return 40.0


def _scope_score(scope: list) -> float:
    if not scope:
        return 0.0
    score = min(50.0, len(scope) * 5.0)
    scope_strs = [str(s).lower() for s in scope]
    if any("*" in s for s in scope_strs):
        score += 30.0
    types = set()
    for s in scope_strs:
        if "." in s:
            types.add("domain")
        if "api" in s:
            types.add("api")
        if s.startswith("http"):
            types.add("url")
    score += len(types) * 5.0
    return min(100.0, score)


def _fit_score(scope: list, platform: str) -> float:
    scope_str = " ".join(str(s) for s in scope).lower()
    score = 50.0

    if any(kw in scope_str for kw in ["ai", "ml", "llm", "model", "claude", "gpt", "openai"]):
        score += 35.0
    if any(kw in scope_str for kw in ["api", "rest", "graphql", "grpc"]):
        score += 30.0
    if any(kw in scope_str for kw in ["oauth", "sso", "auth", "saml", "login"]):
        score += 25.0
    if any(kw in scope_str for kw in ["aws", "gcp", "azure", "cloud", "s3"]):
        score += 15.0
    if any(kw in scope_str for kw in ["mobile", "ios", "android"]):
        score += 10.0

    if any(kw in scope_str for kw in ["ai", "ml", "llm", "anthropic", "openai"]):
        score *= 1.3

    return min(100.0, score)


@activity.defn
async def score_program(program_id: str) -> dict:
    with Session(engine) as session:
        program = session.get(Program, program_id)
        if not program:
            raise ApplicationError(f"Program {program_id} not found", non_retryable=True)

        payout = _payout_score(program.max_payout)
        scope = _scope_score(program.scope or [])
        competition = 50.0
        fit = _fit_score(program.scope or [], program.platform)
        momentum = 50.0

        total = (
            payout * 0.20
            + scope * 0.20
            + competition * 0.25
            + fit * 0.25
            + momentum * 0.10
        )

        top_signals = []
        scope_str = " ".join(str(s) for s in (program.scope or [])).lower()
        if any(kw in scope_str for kw in ["ai", "ml", "llm"]):
            top_signals.append("AI/LLM scope")
        if any(kw in scope_str for kw in ["api", "graphql"]):
            top_signals.append("API scope")
        if any(kw in scope_str for kw in ["oauth", "sso"]):
            top_signals.append("Auth scope")

        score = ProgramScore(
            program_id=program_id,
            total_score=round(total, 2),
            payout_score=round(payout, 2),
            scope_score=round(scope, 2),
            competition_score=round(competition, 2),
            fit_score=round(fit, 2),
            momentum_score=round(momentum, 2),
            top_signals=top_signals,
            scoring_version="1.0",
        )
        session.add(score)
        session.commit()

        return {"total_score": score.total_score, "top_signals": top_signals}
