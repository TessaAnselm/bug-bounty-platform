"""Recon plan is the single source of truth for rate + tools — the workflow and
the program page both derive from it, so displayed config == actual behavior."""
from src.lib.recon_plan import recon_plan, effective_rps, DEFAULT_RPS


def test_effective_rps_matches_rpm():
    assert effective_rps({"rate_limit_rpm": 600}) == 10
    assert effective_rps({"rate_limit_rpm": 180}) == 3
    assert effective_rps({"rate_limit_rpm": 30}) == 1     # floors to >=1
    assert effective_rps({}) == DEFAULT_RPS               # no cap → default
    assert effective_rps(None) == DEFAULT_RPS


def test_plan_passive_only_by_default():
    p = recon_plan({"rate_limit_rpm": 600})
    assert p["active_scanning"] is False
    assert p["rate_rps"] == 10
    # httpx is the only target-facing tool when active scanning is off
    assert p["target_facing"] == ["httpx"]
    # active tools are listed as skipped, not run
    assert p["tools_skipped"] == ["katana", "gowitness"]
    assert "katana" not in p["tools_running"] and "gowitness" not in p["tools_running"]
    # passive tools query third-party data, never the target
    assert set(p["passive"]) == {"subfinder", "fingerprint", "gau", "github"}


def test_plan_active_adds_target_facing_tools():
    p = recon_plan({"rate_limit_rpm": 600, "allow_active_scanning": True})
    assert p["active_scanning"] is True
    assert "katana" in p["target_facing"] and "gowitness" in p["target_facing"]
    assert p["tools_skipped"] == []


def test_plan_rate_source_label():
    assert "600/min" in recon_plan({"rate_limit_rpm": 600})["rate_source"]
    assert "default" in recon_plan({})["rate_source"]


def test_workflow_and_page_use_same_rps():
    """The workflow imports effective_rps; the page calls recon_plan. Both must
    yield the same probe rate for the same constraints."""
    c = {"rate_limit_rpm": 600}
    assert effective_rps(c) == recon_plan(c)["rate_rps"]
