from typing import List
from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import CurrentUser, SessionDep
from app.schemas.comment import CommentCreate, CommentResponse
from app.services.comment_service import CommentService

router = APIRouter(prefix="/tasks", tags=["Comments"])


def get_comment_service(db: SessionDep) -> CommentService:
    """Dependency provider for CommentService with active database session."""
    return CommentService(db)


@router.post(
    "/{task_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a comment to a task",
)
async def add_comment(
    task_id: int,
    comment_in: CommentCreate,
    current_user: CurrentUser,
    service: CommentService = Depends(get_comment_service),
) -> CommentResponse:
    """
    Add a comment to a specified task:
    - Author is resolved from the current authenticated user's token.
    - Requires valid task_id (returns 404 if not found).
    """
    return await service.create_comment(
        task_id=task_id,
        author_id=current_user.id,
        comment_in=comment_in,
    )


@router.get(
    "/{task_id}/comments",
    response_model=List[CommentResponse],
    status_code=status.HTTP_200_OK,
    summary="List comments for a task",
)
async def list_comments(
    task_id: int,
    current_user: CurrentUser,
    service: CommentService = Depends(get_comment_service),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> List[CommentResponse]:
    """
    Retrieve all comments for a given task:
    - Returns a list ordered chronologically by creation timestamp.
    - Includes public author details (id, username).
    """
    return await service.get_comments_by_task(
        task_id=task_id,
        limit=limit,
        offset=offset,
    )