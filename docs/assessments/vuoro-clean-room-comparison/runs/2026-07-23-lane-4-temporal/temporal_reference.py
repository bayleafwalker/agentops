import asyncio
import json
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.worker import Worker


@activity.defn
async def receipt(task: str) -> dict:
    return {"corpus_task": task, "execution_receipt": "temporal-activity-completed"}


@workflow.defn
class CorpusReceiptWorkflow:
    @workflow.run
    async def run(self, task: str) -> dict:
        await workflow.sleep(2)
        return await workflow.execute_activity(receipt, task, start_to_close_timeout=timedelta(seconds=20))


async def main() -> None:
    client = await Client.connect("127.0.0.1:17233")
    async with Worker(client, task_queue="vuoro-clean-room-lane4", workflows=[CorpusReceiptWorkflow], activities=[receipt]):
        handle = await client.start_workflow(CorpusReceiptWorkflow.run, "CR-02", id="BATCH-02", task_queue="vuoro-clean-room-lane4", id_conflict_policy=WorkflowIDConflictPolicy.FAIL)
        try:
            await client.start_workflow(CorpusReceiptWorkflow.run, "CR-02", id="BATCH-02", task_queue="vuoro-clean-room-lane4", id_conflict_policy=WorkflowIDConflictPolicy.FAIL)
        except WorkflowAlreadyStartedError:
            duplicate_rejected = True
        else:
            duplicate_rejected = False
        result = await handle.result()
    assert duplicate_rejected
    assert result["corpus_task"] == "CR-02"
    print(json.dumps({"workflow_started": True, "duplicate_start_rejected_while_running": duplicate_rejected, "result": result}, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
