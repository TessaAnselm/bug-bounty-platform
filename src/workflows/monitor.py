from datetime import timedelta
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from src.workflows.types import MonitorInput, ReconInput


TASK_QUEUE = "bounty-task-queue"


@workflow.defn
class MonitorWorkflow:
    def __init__(self) -> None:
        self._active = True

    @workflow.signal
    async def stop(self) -> None:
        self._active = False

    @workflow.run
    async def run(self, input: MonitorInput) -> None:
        run_count = 0
        while self._active:
            run_count += 1
            await workflow.start_child_workflow(
                "ReconWorkflow",
                args=[ReconInput(program_id=input.program_id, triggered_by="monitor")],
                id=f"recon-{input.program_id}-{run_count}",
                task_queue=TASK_QUEUE,
            )
            await workflow.wait_condition(
                lambda: not self._active,
                timeout=timedelta(hours=input.interval_hours),
            )
