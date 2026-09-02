from datetime import datetime
from typing import TYPE_CHECKING, List
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.comment import Comment
    from app.models.task import Task


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


    authored_tasks: Mapped[List["Task"]] = relationship(
        "Task",
        foreign_keys="Task.author_id",
        back_populates="author",
        cascade="all, delete-orphan",
    )
    assigned_tasks: Mapped[List["Task"]] = relationship(
        "Task",
        foreign_keys="Task.assignee_id",
        back_populates="assignee",
    )
    comments: Mapped[List["Comment"]] = relationship(
        "Comment",
        back_populates="author",
        cascade="all, delete-orphan",
    )