import enum
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.comment import Comment
    from app.models.user import User


class TaskStatus(str, enum.Enum):
    BACKLOG = "Backlog"
    IN_PROGRESS = "In Progress"
    REVIEW = "Review"
    DONE = "Done"
    CANCELLED = "Cancelled"


class TaskPriority(str, enum.Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status_enum", native_enum=False),
        default=TaskStatus.BACKLOG,
        index=True,
        nullable=False,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority, name="task_priority_enum", native_enum=False),
        default=TaskPriority.MEDIUM,
        index=True,
        nullable=False,
    )

    deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assignee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )


    author: Mapped["User"] = relationship(
        "User", foreign_keys=[author_id], back_populates="authored_tasks"
    )
    assignee: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[assignee_id], back_populates="assigned_tasks"
    )
    comments: Mapped[List["Comment"]] = relationship(
        "Comment",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="Comment.created_at",
    )