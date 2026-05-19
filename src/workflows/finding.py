from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from src.workflows.types import FindingInput, FindingResult
    from src.activities.storage.programs import (
        create_finding,
        update_finding_status,
        record_outcome,
    )
    from src.activities.notifications.discord_alert import send_discord_alert

_RETRY = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=5))
_SHORT = timedelta(minutes=5)

TERMINAL_STATES = {"resolved", "duplicate", "not_applicable", "paid"}


@workflow.defn
class FindingWorkflow:
    def __init__(self) -> None:
        self._status = "draft"
        self._payout: float | None = None

    @workflow.signal
    async def update_status(self, new_status: str) -> None:
        self._status = new_status

    @workflow.signal
    async def set_payout(self, amount: float) -> None:
        self._payout = amount

    @workflow.run
    async def run(self, input: FindingInput) -> FindingResult:
        finding_id = await workflow.execute_activity(
            create_finding,
            args=[
                input.program_id,
                input.title,
                input.vuln_type,
                input.severity,
                input.asset_id,
            ],
            start_to_close_timeout=_SHORT,
            retry_policy=_RETRY,
        )

        await workflow.execute_activity(
            send_discord_alert,
            f"📋 New finding: **{input.title}** ({input.severity}) — tracking started",
            start_to_close_timeout=_SHORT,
            retry_policy=_RETRY,
        )

        await workflow.wait_condition(lambda: self._status in TERMINAL_STATES)

        await workflow.execute_activity(
            update_finding_status,
            args=[finding_id, self._status],
            start_to_close_timeout=_SHORT,
            retry_policy=_RETRY,
        )

        await workflow.execute_activity(
            record_outcome,
            args=[finding_id, self._status, self._payout, None, None],
            start_to_close_timeout=_SHORT,
            retry_policy=_RETRY,
        )

        if self._status == "paid":
            await workflow.execute_activity(
                send_discord_alert,
                f"💰 Paid: **{input.title}** — ${self._payout or 0:.2f}",
                start_to_close_timeout=_SHORT,
                retry_policy=_RETRY,
            )

        return FindingResult(
            finding_id=finding_id,
            final_status=self._status,
            payout_amount=self._payout,
        )
