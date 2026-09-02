from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def create_authenticated_user(
    client: AsyncClient, username: str, email: str
) -> tuple[dict[str, str], int]:
    """Helper to register and log in a test user, returning auth headers and user ID."""
    register_res = await client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": email,
            "password": "StrongPassword123!",
        },
    )
    assert register_res.status_code == status.HTTP_201_CREATED
    user_id = register_res.json()["id"]

    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPassword123!"},
    )
    assert login_res.status_code == status.HTTP_200_OK
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers, user_id


def get_future_iso(days: int = 5) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


async def create_task(client: AsyncClient, headers: dict[str, str], **overrides) -> int:
    payload = {"title": "Comment target task", "deadline": get_future_iso()}
    payload.update(overrides)
    res = await client.post("/api/v1/tasks/", json=payload, headers=headers)
    assert res.status_code == status.HTTP_201_CREATED
    return res.json()["id"]


async def test_add_comment_success(client: AsyncClient) -> None:
    """A user can add a comment to an existing task."""
    headers, _ = await create_authenticated_user(client, "commenter", "commenter@example.com")
    task_id = await create_task(client, headers)

    response = await client.post(
        f"/api/v1/tasks/{task_id}/comments",
        json={"content": "This looks good to me."},
        headers=headers,
    )
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["content"] == "This looks good to me."
    assert data["task_id"] == task_id
    assert data["author"]["username"] == "commenter"


async def test_add_comment_empty_content_rejected(client: AsyncClient) -> None:
    """An empty comment body fails validation."""
    headers, _ = await create_authenticated_user(client, "empty_commenter", "empty@example.com")
    task_id = await create_task(client, headers)

    response = await client.post(
        f"/api/v1/tasks/{task_id}/comments",
        json={"content": ""},
        headers=headers,
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_add_comment_to_nonexistent_task_fails(client: AsyncClient) -> None:
    """Adding a comment to a task ID that does not exist returns 404."""
    headers, _ = await create_authenticated_user(client, "ghost_commenter", "ghost@example.com")

    response = await client.post(
        "/api/v1/tasks/999999/comments",
        json={"content": "Does this even exist?"},
        headers=headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_add_comment_requires_authentication(client: AsyncClient) -> None:
    """Adding a comment without a valid token is rejected."""
    headers, _ = await create_authenticated_user(client, "auth_setup_user", "authsetup@example.com")
    task_id = await create_task(client, headers)

    response = await client.post(
        f"/api/v1/tasks/{task_id}/comments",
        json={"content": "Anonymous comment attempt"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_list_comments_returns_chronological_order(client: AsyncClient) -> None:
    """Comments are listed in the order they were created."""
    headers, _ = await create_authenticated_user(client, "lister", "lister@example.com")
    task_id = await create_task(client, headers)

    await client.post(
        f"/api/v1/tasks/{task_id}/comments",
        json={"content": "First comment"},
        headers=headers,
    )
    await client.post(
        f"/api/v1/tasks/{task_id}/comments",
        json={"content": "Second comment"},
        headers=headers,
    )

    response = await client.get(f"/api/v1/tasks/{task_id}/comments", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert len(data) == 2
    assert data[0]["content"] == "First comment"
    assert data[1]["content"] == "Second comment"


async def test_list_comments_for_nonexistent_task_fails(client: AsyncClient) -> None:
    """Listing comments for a nonexistent task returns 404."""
    headers, _ = await create_authenticated_user(client, "lister_ghost", "listerghost@example.com")

    response = await client.get("/api/v1/tasks/999999/comments", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
