import asyncio
from datetime import datetime, timezone
import logging
from sqlalchemy import update

from app.core.database import AsyncSessionLocal
from app.models.task import Task, TaskStatus

logger = logging.getLogger("app.background.task_canceller")

# Interval between consecutive checks in seconds (e.g., 60 seconds)
DEFAULT_CHECK_INTERVAL_SECONDS = 60


async def cancel_overdue_tasks() -> int:
    """
    Find and cancel overdue tasks in a single database transaction[cite: 1]:
    - Checks for tasks whose deadline is earlier than the current UTC time.
    - Excludes tasks that have already reached terminal states (Done or Cancelled)[cite: 1].
    - Updates their status to Cancelled[cite: 1].

    Returns:
        The number of tasks transitioned to Cancelled.
    """
    now_utc = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        try:
            stmt = (
                update(Task)
                .where(
                    Task.deadline < now_utc,
                    Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
                )
                .values(status=TaskStatus.CANCELLED)
            )
            result = await session.execute(stmt)
            await session.commit()

            cancelled_count = result.rowcount
            if cancelled_count > 0:
                logger.info(
                    "Auto-cancelled %d overdue task(s) past deadline.", cancelled_count
                )
            return cancelled_count

        except Exception as exc:
            await session.rollback()
            logger.error("Error occurred while auto-cancelling overdue tasks: %s", exc)
            raise


async def run_overdue_tasks_worker(
    interval_seconds: int = DEFAULT_CHECK_INTERVAL_SECONDS,
) -> None:
    """
    Infinite background loop that runs periodically to mark overdue tasks as Cancelled[cite: 1].
    
    Catches unexpected errors to keep the background loop resilient,
    while permitting asyncio.CancelledError to bubble up during application shutdown.
    """
    logger.info(
        "Overdue tasks cancellation worker started. Check interval: %d seconds.",
        interval_seconds,
    )

    while True:
        try:
            await cancel_overdue_tasks()
        except asyncio.CancelledError:
            # Re-raise to ensure clean task cancellation during FastAPI shutdown
            logger.info("Overdue tasks worker received cancellation signal.")
            raise
        except Exception as exc:
            logger.error("Unexpected worker iteration failure: %s", exc)

        # Wait before the next sweep
        await asyncio.sleep(interval_seconds)