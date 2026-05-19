from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OnboardingInput:
    name: str
    platform: str
    scope: list[str]
    out_of_scope: list[str]
    max_payout: Optional[int] = None


@dataclass
class OnboardingResult:
    program_id: str
    recon_workflow_id: str
    monitor_workflow_id: str


@dataclass
class ReconInput:
    program_id: str
    triggered_by: str = "manual"


@dataclass
class ReconResult:
    recon_run_id: str
    assets_found: int
    new_assets: int


@dataclass
class FindingInput:
    program_id: str
    title: str
    vuln_type: str
    severity: str
    asset_id: Optional[str] = None


@dataclass
class FindingResult:
    finding_id: str
    final_status: str
    payout_amount: Optional[float] = None


@dataclass
class MonitorInput:
    program_id: str
    interval_hours: int = 24


@dataclass
class ProbeResult:
    url: str
    input: str
    status_code: int
    content_length: int
    technologies: list[str]
    webserver: str
    title: str
    host: str
    port: str
    scheme: str


@dataclass
class ScreenshotResult:
    url: str
    path: str


@dataclass
class DiffResult:
    new_assets: int
    changed_assets: int
    total_assets: int
