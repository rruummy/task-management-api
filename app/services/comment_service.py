from typing import List
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.comment import Comment
from app.models.task import Task
from app.schemas.comment import CommentCreate


class CommentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _validate_task_exists(self, task_id: int) -> Task:
        """Verify that the target task exists."""
        query = select(Task).where(Task.id == task_id)
        result = await self.session.execute(query)
        task = result.scalar_one_or_none()

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with ID {task_id} not found",
            )
        return task

    async def create_comment(
        self, task_id: int, author_id: int, comment_in: CommentCreate
    ) -> Comment:
        """Create and save a new comment associated with a task."""
        await self._validate_task_exists(task_id)

        new_comment = Comment(
            content=comment_in.content,
            task_id=task_id,
            author_id=author_id,
        )

        self.session.add(new_comment)
        await self.session.commit()

        # Eagerly load the author relationship for serialization
        query = (
            select(Comment)
            .where(Comment.id == new_comment.id)
            .options(selectinload(Comment.author))
        )
        result = await self.session.execute(query)
        return result.scalar_one()

    async def get_comments_by_task(
        self, task_id: int, limit: int = 50, offset: int = 0
    ) -> List[Comment]:
        """Fetch comments for a task ordered chronologically."""
        await self._validate_task_exists(task_id)

        query = (
            select(Comment)
            .where(Comment.task_id == task_id)
            .options(selectinload(Comment.author))
            .order_by(Comment.created_at.asc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())