from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import CurrentUser, SessionDep
from app.models.task import TaskPriority, TaskStatus
from app.schemas.task import (
    PaginatedTasksResponse,
    TaskCreate,
    TaskResponse,
    TaskStatisticsResponse,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["Tasks"])


def get_task_service(db: SessionDep) -> TaskService:
    """Dependency provider for TaskService with an active database session."""
    return TaskService(db)


@router.post(
    "/",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new task",
)
async def create_task(
    task_in: TaskCreate,
    current_user: CurrentUser,
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    """
    Create a new task:
    - The authenticated user becomes the task's author.
    - New tasks always start in the 'Backlog' status.
    - If an assignee is provided, they must exist and must not already
      have 10 or more active tasks (Backlog, In Progress, Review).
    """
    task = await service.create_task(task_in=task_in, author_id=current_user.id)
    return TaskResponse.model_validate(task)


@router.get(
    "/",
    response_model=PaginatedTasksResponse,
    status_code=status.HTTP_200_OK,
    summary="List tasks with search, filtering, sorting, and pagination",
)
async def list_tasks(
    current_user: CurrentUser,
    service: TaskService = Depends(get_task_service),
    q: Optional[str] = Query(None, description="Search text within title and description"),
    status_: Optional[TaskStatus] = Query(None, alias="status", description="Filter by status"),
    priority: Optional[TaskPriority] = Query(None, description="Filter by priority"),
    assignee_id: Optional[int] = Query(None, description="Filter by assignee user ID"),
    deadline_from: Optional[datetime] = Query(None, description="Only tasks with deadline on or after this timestamp"),
    deadline_to: Optional[datetime] = Query(None, description="Only tasks with deadline on or before this timestamp"),
    sort_by: Optional[Literal["created_at", "deadline", "priority"]] = Query(
        None, description="Sort field. If omitted, default sort is priority then nearest deadline."
    ),
    sort_order: Literal["asc", "desc"] = Query("asc", description="Sort direction"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> PaginatedTasksResponse:
    """
    Retrieve a paginated list of tasks:
    - Full-text search over title and description via `q`.
    - Filter by status, priority, assignee, and deadline range.
    - Sort by created_at, deadline, or priority (default: priority, then nearest deadline).
    """
    return await service.get_tasks(
        q=q,
        status=status_,
        priority=priority,
        assignee_id=assignee_id,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/overdue",
    response_model=PaginatedTasksResponse,
    status_code=status.HTTP_200_OK,
    summary="List overdue tasks",
)
async def get_overdue_tasks(
    current_user: CurrentUser,
    service: TaskService = Depends(get_task_service),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> PaginatedTasksResponse:
    """
    Retrieve all tasks whose deadline has already passed and which are not
    yet in a terminal status (Done or Cancelled).
    """
    return await service.get_overdue_tasks(limit=limit, offset=offset)


@router.get(
    "/statistics",
    response_model=TaskStatisticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get task statistics",
)
async def get_task_statistics(
    current_user: CurrentUser,
    service: TaskService = Depends(get_task_service),
) -> TaskStatisticsResponse:
    """
    Retrieve aggregated task statistics:
    - Total task count.
    - Count grouped by status.
    - Count grouped by priority.
    - Count of overdue tasks.
    - Count of active tasks.
    """
    return await service.get_statistics()


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a task by ID",
)
async def get_task(
    task_id: int,
    current_user: CurrentUser,
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    """Retrieve a single task by its ID."""
    task = await service.get_task_by_id(task_id)
    return TaskResponse.model_validate(task)


@router.put(
    "/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a task",
)
async def update_task(
    task_id: int,
    task_in: TaskUpdate,
    current_user: CurrentUser,
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    """
    Update an existing task:
    - Tasks in 'Done' or 'Cancelled' status cannot be edited.
    - The assignee cannot be changed once the task reaches 'Review' or 'Done'.
    - Deadline cannot be set to a moment in the past.
    """
    task = await service.update_task(task_id=task_id, task_in=task_in)
    return TaskResponse.model_validate(task)


@router.patch(
    "/{task_id}/status",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Change a task's status",
)
async def change_task_status(
    task_id: int,
    status_in: TaskStatusUpdate,
    current_user: CurrentUser,
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    """
    Transition a task to a new status via the dedicated status endpoint:
    - Only forward transitions along the allowed workflow are permitted.
    - Moving to 'Done' requires an assignee and a deadline that has not passed.
    """
    task = await service.change_status(task_id=task_id, new_status=status_in.status)
    return TaskResponse.model_validate(task)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
)
async def delete_task(
    task_id: int,
    current_user: CurrentUser,
    service: TaskService = Depends(get_task_service),
) -> None:
    """
    Delete a task:
    - Tasks in 'In Progress' or 'Review' status cannot be deleted directly;
      they must first be moved to 'Cancelled' or 'Done'.
    """
    await service.delete_task(task_id)
