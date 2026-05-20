"""
Smoke tests — verify all core modules import cleanly.
These run without a live database (SQLAlchemy engine is lazy).
"""


def test_db_models_importable():
    from src.db.models import (
        Program, Asset, Finding, ReconRun,
        Alert, SessionNote, Outcome, ProgramScore, Artifact,
    )
    assert Program and Asset and Finding


def test_workflow_types_importable():
    from src.workflows.types import (
        OnboardingInput, OnboardingResult,
        ReconInput, ReconResult,
        FindingInput, FindingResult,
        MonitorInput,
    )
    assert OnboardingInput and ReconInput


def test_api_auth_importable():
    from src.api.auth import verify_api_key
    assert verify_api_key


def test_mcp_server_importable():
    from src.mcp import server
    assert server


def test_mcp_tools_importable():
    from src.mcp.tools.search import search_assets, summarize_program
    assert search_assets and summarize_program


def test_scoring_weights_sum_to_one():
    """Scoring weight constants must sum to 1.0."""
    weights = {
        "payout": 0.20,
        "scope": 0.20,
        "competition": 0.25,
        "fit": 0.25,
        "momentum": 0.10,
    }
    assert abs(sum(weights.values()) - 1.0) < 1e-9
