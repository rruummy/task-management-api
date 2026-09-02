from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.task import TaskPriority, TaskStatus
from app.schemas.user import UserPublic


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=10000)
    priority: TaskPriority = TaskPriority.MEDIUM
    deadline: datetime
    assignee_id: Optional[int] = None

    @field_validator("deadline")
    @classmethod
    def validate_deadline_not_in_past(cls, value: datetime) -> datetime:
        now = datetime.now(timezone.utc)
        deadline_utc = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if deadline_utc <= now:
            raise ValueError("The deadline cannot be earlier than the current date and time.")
        return deadline_utc


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=10000)
    priority: Optional[TaskPriority] = None
    deadline: Optional[datetime] = None
    assignee_id: Optional[int] = None

    @field_validator("deadline")
    @classmethod
    def validate_deadline_not_in_past(
        cls, value: Optional[datetime]
    ) -> Optional[datetime]:
        if value is None:
            return value
        now = datetime.now(timezone.utc)
        deadline_utc = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if deadline_utc <= now:
            raise ValueError("The deadline cannot be earlier than the current date and time.")
        return deadline_utc


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    status: TaskStatus
    priority: TaskPriority
    deadline: datetime
    created_at: datetime
    updated_at: datetime
    author: UserPublic
    assignee: Optional[UserPublic] = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedTasksResponse(BaseModel):
    items: List[TaskResponse]
    total: int
    limit: int
    offset: int


class TaskStatisticsResponse(BaseModel):
    total_tasks: int
    by_status: Dict[str, int]
    by_priority: Dict[str, int]
    overdue_tasks: int
    active_tasks: int