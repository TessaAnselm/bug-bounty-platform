from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from src.workflows.types import OnboardingInput, OnboardingResult, ReconInput, MonitorInput
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

        recon_handle = await workflow.start_child_workflow(
            "ReconWorkflow",
            args=[ReconInput(program_id=program_id, triggered_by="onboarding")],
            id=f"recon-{program_id}-initial",
            task_queue=TASK_QUEUE,
        )

        monitor_handle = await workflow.start_child_workflow(
            "MonitorWorkflow",
            args=[MonitorInput(program_id=program_id, interval_hours=24)],
            id=f"monitor-{program_id}",
            task_queue=TASK_QUEUE,
        )

        await workflow.execute_activity(
            send_discord_alert,
            f"✅ Onboarded: **{input.name}** ({input.platform}) — recon started",
            start_to_close_timeout=_SHORT,
            retry_policy=_RETRY,
        )

        return OnboardingResult(
            program_id=program_id,
            recon_workflow_id=recon_handle.id,
            monitor_workflow_id=monitor_handle.id,
        )
