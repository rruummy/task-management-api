from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set
from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.task import Task, TaskPriority, TaskStatus
from app.models.user import User
from app.schemas.task import (
    PaginatedTasksResponse,
    TaskCreate,
    TaskResponse,
    TaskStatisticsResponse,
    TaskUpdate,
)

MAX_ACTIVE_TASKS_PER_USER = 10

ACTIVE_STATUSES: Set[TaskStatus] = {
    TaskStatus.BACKLOG,
    TaskStatus.IN_PROGRESS,
    TaskStatus.REVIEW,
}

ALLOWED_TRANSITIONS: Dict[TaskStatus, Set[TaskStatus]] = {
    TaskStatus.BACKLOG: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.IN_PROGRESS: {TaskStatus.REVIEW, TaskStatus.CANCELLED},
    TaskStatus.REVIEW: {TaskStatus.DONE, TaskStatus.CANCELLED},
    TaskStatus.DONE: set(),
    TaskStatus.CANCELLED: set(),
}


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_task_or_404(self, task_id: int) -> Task:
        """Fetch task by ID with relationships or raise 404."""
        query = (
            select(Task)
            .where(Task.id == task_id)
            .options(
                selectinload(Task.author),
                selectinload(Task.assignee),
            )
        )
        result = await self.session.execute(query)
        task = result.scalar_one_or_none()

        if not task:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Task with ID {task_id} not found",
            )
        return task

    async def _validate_user_exists(self, user_id: int) -> User:
        """Verify that a user exists in the database."""
        query = select(User).where(User.id == user_id)
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} does not exist",
            )
        return user

    async def _check_active_tasks_limit(
        self, user_id: int, exclude_task_id: Optional[int] = None
    ) -> None:
        """Ensure the user does not exceed the limit of 10 active tasks."""
        query = (
            select(func.count(Task.id))
            .where(
                Task.assignee_id == user_id,
                Task.status.in_(ACTIVE_STATUSES),
            )
        )
        if exclude_task_id is not None:
            query = query.where(Task.id != exclude_task_id)

        result = await self.session.execute(query)
        active_count = result.scalar() or 0

        if active_count >= MAX_ACTIVE_TASKS_PER_USER:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"User {user_id} cannot have more than {MAX_ACTIVE_TASKS_PER_USER} active tasks simultaneously",
            )

    async def create_task(self, task_in: TaskCreate, author_id: int) -> Task:
        """Create a new task with Backlog status."""
        if task_in.assignee_id is not None:
            await self._validate_user_exists(task_in.assignee_id)
            await self._check_active_tasks_limit(task_in.assignee_id)

        new_task = Task(
            title=task_in.title,
            description=task_in.description,
            priority=task_in.priority,
            deadline=task_in.deadline,
            status=TaskStatus.BACKLOG,
            author_id=author_id,
            assignee_id=task_in.assignee_id,
        )

        self.session.add(new_task)
        await self.session.commit()

        return await self._get_task_or_404(new_task.id)

    async def get_task_by_id(self, task_id: int) -> Task:
        """Retrieve task by ID."""
        return await self._get_task_or_404(task_id)

    async def update_task(self, task_id: int, task_in: TaskUpdate) -> Task:
        """Update task details while enforcing business rules."""
        task = await self._get_task_or_404(task_id)

        if task.status in {TaskStatus.DONE, TaskStatus.CANCELLED}:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Tasks in '{task.status.value}' status cannot be edited",
            )

        update_data = task_in.model_dump(exclude_unset=True)

        if "assignee_id" in update_data:
            new_assignee_id = update_data["assignee_id"]
            if new_assignee_id != task.assignee_id:
                if task.status in {TaskStatus.REVIEW, TaskStatus.DONE}:
                    raise HTTPException(
                        status_code=http_status.HTTP_400_BAD_REQUEST,
                        detail=f"Cannot change assignee while task is in '{task.status.value}' status",
                    )
                if new_assignee_id is not None:
                    await self._validate_user_exists(new_assignee_id)
                    await self._check_active_tasks_limit(
                        new_assignee_id, exclude_task_id=task.id
                    )

        for field, value in update_data.items():
            setattr(task, field, value)

        await self.session.commit()
        return await self._get_task_or_404(task.id)

    async def change_status(self, task_id: int, new_status: TaskStatus) -> Task:
        """Transition task status following allowed state machine routes."""
        task = await self._get_task_or_404(task_id)

        if task.status == new_status:
            return task

        allowed = ALLOWED_TRANSITIONS.get(task.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid transition from '{task.status.value}' to '{new_status.value}'. Reverting or invalid path is not allowed.",
            )

        if new_status == TaskStatus.DONE:
            if task.assignee_id is None:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="Cannot complete task (Done) without an assigned user",
                )

            now_utc = datetime.now(timezone.utc)
            deadline_utc = (
                task.deadline
                if task.deadline.tzinfo
                else task.deadline.replace(tzinfo=timezone.utc)
            )

            if deadline_utc < now_utc:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="Cannot complete task (Done) because its deadline has already passed",
                )

        task.status = new_status
        await self.session.commit()
        return await self._get_task_or_404(task.id)

    async def delete_task(self, task_id: int) -> None:
        """Delete task ensuring it is not In Progress or Review."""
        task = await self._get_task_or_404(task_id)

        if task.status in {TaskStatus.IN_PROGRESS, TaskStatus.REVIEW}:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete a task in '{task.status.value}' status. Mark it as Cancelled or Done first.",
            )

        await self.session.delete(task)
        await self.session.commit()

    # Fields that are safe to sort on, mapped to their SQLAlchemy column
    SORTABLE_FIELDS: Dict[str, Any] = {
        "created_at": Task.created_at,
        "deadline": Task.deadline,
        "priority": Task.priority,
    }

    async def get_tasks(
        self,
        q: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
        assignee_id: Optional[int] = None,
        deadline_from: Optional[datetime] = None,
        deadline_to: Optional[datetime] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "asc",
        limit: int = 10,
        offset: int = 0,
    ) -> PaginatedTasksResponse:
        """List tasks with search, filtering, pagination, and sorting."""
        query = select(Task).options(
            selectinload(Task.author),
            selectinload(Task.assignee),
        )

        filters = []

        if q:
            search_pattern = f"%{q}%"
            filters.append(
                or_(
                    Task.title.ilike(search_pattern),
                    Task.description.ilike(search_pattern),
                )
            )

        if status:
            filters.append(Task.status == status)
        if priority:
            filters.append(Task.priority == priority)
        if assignee_id is not None:
            filters.append(Task.assignee_id == assignee_id)
        if deadline_from:
            filters.append(Task.deadline >= deadline_from)
        if deadline_to:
            filters.append(Task.deadline <= deadline_to)

        if filters:
            query = query.where(and_(*filters))

        count_query = select(func.count()).select_from(Task)
        if filters:
            count_query = count_query.where(and_(*filters))

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        if sort_by:
            column = self.SORTABLE_FIELDS.get(sort_by)
            if column is None:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot sort by '{sort_by}'. Allowed fields: "
                    f"{', '.join(self.SORTABLE_FIELDS)}",
                )
            order_clause = column.desc() if sort_order == "desc" else column.asc()
            query = query.order_by(order_clause)
        else:
            priority_order = case(
                (Task.priority == TaskPriority.HIGH, 1),
                (Task.priority == TaskPriority.MEDIUM, 2),
                (Task.priority == TaskPriority.LOW, 3),
            )
            query = query.order_by(priority_order.asc(), Task.deadline.asc())

        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        tasks = result.scalars().all()

        return PaginatedTasksResponse(
            items=[TaskResponse.model_validate(t) for t in tasks],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_overdue_tasks(
        self, limit: int = 10, offset: int = 0
    ) -> PaginatedTasksResponse:
        """Retrieve overdue tasks that are not in terminal states."""
        now = datetime.now(timezone.utc)
        filter_condition = and_(
            Task.deadline < now,
            Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
        )

        query = (
            select(Task)
            .where(filter_condition)
            .options(
                selectinload(Task.author),
                selectinload(Task.assignee),
            )
            .order_by(Task.deadline.asc())
            .limit(limit)
            .offset(offset)
        )

        count_query = select(func.count(Task.id)).where(filter_condition)
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        tasks_result = await self.session.execute(query)
        tasks = tasks_result.scalars().all()

        return PaginatedTasksResponse(
            items=[TaskResponse.model_validate(t) for t in tasks],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_statistics(self) -> TaskStatisticsResponse:
        """Generate dashboard task metrics."""
        now = datetime.now(timezone.utc)

        total_stmt = select(func.count(Task.id))
        total_tasks = (await self.session.execute(total_stmt)).scalar() or 0

        status_stmt = select(Task.status, func.count(Task.id)).group_by(Task.status)
        status_results = (await self.session.execute(status_stmt)).all()
        by_status = {s.value: 0 for s in TaskStatus}
        for st, count in status_results:
            by_status[st.value] = count

        priority_stmt = select(Task.priority, func.count(Task.id)).group_by(
            Task.priority
        )
        priority_results = (await self.session.execute(priority_stmt)).all()
        by_priority = {p.value: 0 for p in TaskPriority}
        for pr, count in priority_results:
            by_priority[pr.value] = count

        overdue_stmt = select(func.count(Task.id)).where(
            Task.deadline < now,
            Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
        )
        overdue_tasks = (await self.session.execute(overdue_stmt)).scalar() or 0

        active_stmt = select(func.count(Task.id)).where(
            Task.status.in_(ACTIVE_STATUSES)
        )
        active_tasks = (await self.session.execute(active_stmt)).scalar() or 0

        return TaskStatisticsResponse(
            total_tasks=total_tasks,
            by_status=by_status,
            by_priority=by_priority,
            overdue_tasks=overdue_tasks,
            active_tasks=active_tasks,
        )