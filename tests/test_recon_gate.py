"""§2.3a — safety gate: the active recon tools (katana/gowitness) must run ONLY
when the program allows active scanning. Runs the real ReconWorkflow against
mocked activities and asserts which ones were invoked. Guards the release blocker
"active scanning runs without explicit program permission."
"""
import asyncio

from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from src.workflows.recon import ReconWorkflow
from src.workflows.types import ReconInput

_STATE = {"active": False}
_CALLS: list[str] = []


# Mock activities — registered under the same names the workflow calls. They
# record the two active tools and return minimal valid shapes for the rest.
@activity.defn(name="load_program_scope")
async def load_program_scope(program_id):
    return {
        "name": "T", "platform": "bugcrowd",
        "scope": ["*.example.com"], "out_of_scope": [],
        "constraints": {"allow_active_scanning": _STATE["active"]},
    }


@activity.defn(name="create_recon_run")
async def create_recon_run(program_id, triggered_by):
    return "run-1"


@activity.defn(name="enumerate_subdomains")
async def enumerate_subdomains(scope, out_of_scope):
    return ["a.example.com"]


@activity.defn(name="probe_hosts")
async def probe_hosts(hosts, rate=None, platform=""):
    return [{"url": "https://a.example.com", "input": "a.example.com", "status_code": 200, "port": "443"}]


@activity.defn(name="store_assets")
async def store_assets(program_id, run_id, results, scope, oos):
    return []


@activity.defn(name="collect_hist_urls")
async def collect_hist_urls(scope):
    return []


@activity.defn(name="run_github_osint")
async def run_github_osint(scope):
    return []


@activity.defn(name="capture_screenshots")
async def capture_screenshots(urls):
    _CALLS.append("capture_screenshots")   # gowitness — active
    return []


@activity.defn(name="crawl_js_files")
async def crawl_js_files(urls):
    _CALLS.append("crawl_js_files")         # katana — active
    return []


@activity.defn(name="diff_assets")
async def diff_assets(program_id, run_id):
    return {"total_assets": 1, "new_assets": 0}


@activity.defn(name="complete_recon_run")
async def complete_recon_run(run_id, total, new):
    return None


@activity.defn(name="send_discord_alert")
async def send_discord_alert(msg):
    return None


@activity.defn(name="fail_recon_run")
async def fail_recon_run(run_id):
    _CALLS.append("fail_recon_run")
    return None


_ACTIVITIES = [
    load_program_scope, create_recon_run, enumerate_subdomains, probe_hosts,
    store_assets, collect_hist_urls, run_github_osint, capture_screenshots,
    crawl_js_files, diff_assets, complete_recon_run, send_discord_alert,
    fail_recon_run,
]


async def _run(active: bool) -> list[str]:
    _CALLS.clear()
    _STATE["active"] = active
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue="gate-tq",
            workflows=[ReconWorkflow], activities=_ACTIVITIES,
        ):
            await env.client.execute_workflow(
                ReconWorkflow.run,
                ReconInput(program_id="p1", triggered_by="test"),
                id=f"wf-active-{active}", task_queue="gate-tq",
            )
    return list(_CALLS)


def test_active_off_skips_active_tools():
    calls = asyncio.run(_run(active=False))
    assert "capture_screenshots" not in calls   # gowitness did NOT run
    assert "crawl_js_files" not in calls         # katana did NOT run
    assert "fail_recon_run" not in calls          # and the run succeeded


def test_active_on_runs_active_tools():
    calls = asyncio.run(_run(active=True))
    assert "capture_screenshots" in calls
    assert "crawl_js_files" in calls
