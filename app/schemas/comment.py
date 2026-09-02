from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserPublic


class CommentCreate(BaseModel):
    content: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Comment content cannot be empty",
    )


class CommentResponse(BaseModel):
    id: int
    task_id: int
    content: str
    created_at: datetime
    author: UserPublic

    model_config = ConfigDict(from_attributes=True)