from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from src.workflows.types import OnboardingInput, OnboardingResult, MonitorInput
    from src.activities.storage.programs import store_program
    from src.activities.scoring.score_program import score_program
    from src.activities.notifications.discord_alert import send_discord_alert

TASK_QUEUE = "bounty-task-queue"
_RETRY = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=5))
_SHORT = timedelta(minutes=5)


@workflow.defn
class ProgramOnboardingWorkflow:
    @workflow.run
    async def run(self, input: OnboardingInput) -> OnboardingResult:
        program_id = await workflow.execute_activity(
            store_program,
            args=[input.name, input.platform, input.scope, input.out_of_scope, input.max_payout],
            start_to_close_timeout=_SHORT,
            retry_policy=_RETRY,
        )

        await workflow.execute_activity(
            score_program,
            program_id,
            start_to_close_timeout=_SHORT,
            retry_policy=_RETRY,
        )

        # Recon is NOT auto-started: the program onboards as `draft` and recon is
        # gated until its compliance checklist is completed and it is activated.
        # The monitor still runs on its schedule; ReconWorkflow refuses any program
        # that isn't active, so monitoring effectively begins once you activate.
        monitor_handle = await workflow.start_child_workflow(
            "MonitorWorkflow",
            args=[MonitorInput(program_id=program_id, interval_hours=24)],
            id=f"monitor-{program_id}",
            task_queue=TASK_QUEUE,
        )

        await workflow.execute_activity(
            send_discord_alert,
            f"✅ Onboarded as draft: **{input.name}** ({input.platform}) — "
            f"complete the compliance checklist and activate to start recon",
            start_to_close_timeout=_SHORT,
            retry_policy=_RETRY,
        )

        return OnboardingResult(
            program_id=program_id,
            recon_workflow_id="",  # not started — activate the program to recon
            monitor_workflow_id=monitor_handle.id,
        )
