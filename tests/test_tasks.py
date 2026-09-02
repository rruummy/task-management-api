from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from fastapi import status

pytestmark = pytest.mark.asyncio


# --- Test Helpers ---


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
    """Helper to produce an ISO-8601 string for a future UTC timestamp."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


# --- CRUD Tests ---


async def test_create_task_success(client: AsyncClient) -> None:
    """Test successful task creation with default Backlog status[cite: 1]."""
    headers, _ = await create_authenticated_user(
        client, "task_author", "author@example.com"
    )

    payload = {
        "title": "Set up CI/CD pipeline",
        "description": "Configure GitHub actions and test workflows",
        "priority": "High",
        "deadline": get_future_iso(days=3),
    }

    response = await client.post("/api/v1/tasks/", json=payload, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["title"] == payload["title"]
    assert data["status"] == "Backlog"
    assert data["priority"] == "High"
    assert data["author"]["username"] == "task_author"
    assert data["assignee"] is None


async def test_create_task_past_deadline_validation_error(client: AsyncClient) -> None:
    """Test that creating a task with a deadline in the past fails validation[cite: 1]."""
    headers, _ = await create_authenticated_user(
        client, "deadline_user", "deadline@example.com"
    )

    past_deadline = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    payload = {
        "title": "Invalid task",
        "deadline": past_deadline,
    }

    response = await client.post("/api/v1/tasks/", json=payload, headers=headers)
    # Pydantic field validator raises 422 Unprocessable Entity
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_get_and_update_task(client: AsyncClient) -> None:
    """Test retrieving and updating general fields of an existing task."""
    headers, _ = await create_authenticated_user(
        client, "updater_user", "updater@example.com"
    )

    create_res = await client.post(
        "/api/v1/tasks/",
        json={"title": "Original Title", "deadline": get_future_iso(days=2)},
        headers=headers,
    )
    task_id = create_res.json()["id"]

    # Update task details
    update_res = await client.put(
        f"/api/v1/tasks/{task_id}",
        json={"title": "Updated Title", "description": "Added detailed description"},
        headers=headers,
    )
    assert update_res.status_code == status.HTTP_200_OK
    assert update_res.json()["title"] == "Updated Title"
    assert update_res.json()["description"] == "Added detailed description"


# --- Status Transition Business Rules ---


async def test_valid_status_transition_pipeline(client: AsyncClient) -> None:
    """Test full valid lifecycle: Backlog -> In Progress -> Review -> Done[cite: 1]."""
    headers, user_id = await create_authenticated_user(
        client, "pipeline_worker", "worker@example.com"
    )

    # Create task assigned to self
    create_res = await client.post(
        "/api/v1/tasks/",
        json={
            "title": "Full pipeline task",
            "deadline": get_future_iso(days=5),
            "assignee_id": user_id,
        },
        headers=headers,
    )
    task_id = create_res.json()["id"]

    # Step 1: Backlog -> In Progress[cite: 1]
    res1 = await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "In Progress"},
        headers=headers,
    )
    assert res1.status_code == status.HTTP_200_OK
    assert res1.json()["status"] == "In Progress"

    # Step 2: In Progress -> Review[cite: 1]
    res2 = await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "Review"},
        headers=headers,
    )
    assert res2.status_code == status.HTTP_200_OK
    assert res2.json()["status"] == "Review"

    # Step 3: Review -> Done[cite: 1]
    res3 = await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "Done"},
        headers=headers,
    )
    assert res3.status_code == status.HTTP_200_OK
    assert res3.json()["status"] == "Done"


async def test_reverting_task_status_forbidden(client: AsyncClient) -> None:
    """Test that reverting a task status back to an earlier stage returns 400[cite: 1]."""
    headers, _ = await create_authenticated_user(
        client, "revert_user", "revert@example.com"
    )

    create_res = await client.post(
        "/api/v1/tasks/",
        json={"title": "Revert test task", "deadline": get_future_iso(days=2)},
        headers=headers,
    )
    task_id = create_res.json()["id"]

    # Advance to In Progress[cite: 1]
    await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "In Progress"},
        headers=headers,
    )

    # Attempt to revert back to Backlog[cite: 1]
    revert_res = await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "Backlog"},
        headers=headers,
    )
    assert revert_res.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid transition" in revert_res.json()["detail"]


async def test_transition_to_done_without_assignee_fails(client: AsyncClient) -> None:
    """Test that moving a task to Done without an assignee is rejected[cite: 1]."""
    headers, _ = await create_authenticated_user(
        client, "unassigned_user", "unassigned@example.com"
    )

    # Task created without assignee
    create_res = await client.post(
        "/api/v1/tasks/",
        json={"title": "No assignee task", "deadline": get_future_iso(days=2)},
        headers=headers,
    )
    task_id = create_res.json()["id"]

    await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "In Progress"},
        headers=headers,
    )
    await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "Review"},
        headers=headers,
    )

    # Transition to Done without assignee must fail[cite: 1]
    done_res = await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "Done"},
        headers=headers,
    )
    assert done_res.status_code == status.HTTP_400_BAD_REQUEST
    assert "assigned user" in done_res.json()["detail"].lower()


async def test_cannot_edit_completed_or_cancelled_tasks(client: AsyncClient) -> None:
    """Test that tasks in Done or Cancelled status cannot be edited[cite: 1]."""
    headers, _ = await create_authenticated_user(
        client, "edit_lock_user", "editlock@example.com"
    )

    create_res = await client.post(
        "/api/v1/tasks/",
        json={"title": "To be cancelled", "deadline": get_future_iso(days=2)},
        headers=headers,
    )
    task_id = create_res.json()["id"]

    # Cancel task[cite: 1]
    await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "Cancelled"},
        headers=headers,
    )

    # Attempt to edit cancelled task[cite: 1]
    update_res = await client.put(
        f"/api/v1/tasks/{task_id}",
        json={"title": "New Title Attempt"},
        headers=headers,
    )
    assert update_res.status_code == status.HTTP_400_BAD_REQUEST
    assert "cannot be edited" in update_res.json()["detail"].lower()


async def test_cannot_change_assignee_in_review_status(client: AsyncClient) -> None:
    """Test that assignee cannot be modified once the task reaches Review status[cite: 1]."""
    headers, user1_id = await create_authenticated_user(
        client, "user_one", "u1@example.com"
    )
    _, user2_id = await create_authenticated_user(
        client, "user_two", "u2@example.com"
    )

    create_res = await client.post(
        "/api/v1/tasks/",
        json={
            "title": "Review assignee check",
            "deadline": get_future_iso(days=3),
            "assignee_id": user1_id,
        },
        headers=headers,
    )
    task_id = create_res.json()["id"]

    # Advance to In Progress -> Review[cite: 1]
    await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "In Progress"},
        headers=headers,
    )
    await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "Review"},
        headers=headers,
    )

    # Attempt re-assignment in Review status[cite: 1]
    update_res = await client.put(
        f"/api/v1/tasks/{task_id}",
        json={"assignee_id": user2_id},
        headers=headers,
    )
    assert update_res.status_code == status.HTTP_400_BAD_REQUEST
    assert "cannot change assignee" in update_res.json()["detail"].lower()


# --- Deletion Business Rules ---


async def test_task_deletion_rules(client: AsyncClient) -> None:
    """
    Test deletion constraints[cite: 1]:
    - Cannot delete task in In Progress or Review status[cite: 1].
    - Can delete task when Cancelled or Done[cite: 1].
    """
    headers, _ = await create_authenticated_user(
        client, "deleter_user", "deleter@example.com"
    )

    create_res = await client.post(
        "/api/v1/tasks/",
        json={"title": "Delete rule task", "deadline": get_future_iso(days=2)},
        headers=headers,
    )
    task_id = create_res.json()["id"]

    # Advance to In Progress[cite: 1]
    await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "In Progress"},
        headers=headers,
    )

    # Deletion in In Progress must fail[cite: 1]
    del_res = await client.delete(f"/api/v1/tasks/{task_id}", headers=headers)
    assert del_res.status_code == status.HTTP_400_BAD_REQUEST

    # Cancel task first[cite: 1]
    await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "Cancelled"},
        headers=headers,
    )

    # Deletion in Cancelled must succeed[cite: 1]
    del_res2 = await client.delete(f"/api/v1/tasks/{task_id}", headers=headers)
    assert del_res2.status_code == status.HTTP_204_NO_CONTENT


# --- Concurrency Workload & Overdue Tests ---


async def test_user_active_tasks_limit_exceeded(client: AsyncClient) -> None:
    """Test that a single user cannot have more than 10 active tasks concurrently[cite: 1]."""
    headers, assignee_id = await create_authenticated_user(
        client, "busy_dev", "busy@example.com"
    )

    # Create 10 active tasks assigned to the same user[cite: 1]
    for i in range(10):
        res = await client.post(
            "/api/v1/tasks/",
            json={
                "title": f"Active task #{i + 1}",
                "deadline": get_future_iso(days=4),
                "assignee_id": assignee_id,
            },
            headers=headers,
        )
        assert res.status_code == status.HTTP_201_CREATED

    # 11th active task assignment must be rejected[cite: 1]
    overflow_res = await client.post(
        "/api/v1/tasks/",
        json={
            "title": "Overflow task #11",
            "deadline": get_future_iso(days=4),
            "assignee_id": assignee_id,
        },
        headers=headers,
    )
    assert overflow_res.status_code == status.HTTP_400_BAD_REQUEST
    assert "more than 10 active tasks" in overflow_res.json()["detail"]


async def test_get_overdue_tasks_endpoint(client: AsyncClient) -> None:
    """Test that /tasks/overdue endpoint returns only tasks past deadline not Done/Cancelled[cite: 1]."""
    headers, _ = await create_authenticated_user(
        client, "overdue_checker", "overdue@example.com"
    )

    response = await client.get("/api/v1/tasks/overdue", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "items" in data
    assert "total" in data
    # Verified that all returned tasks are not in terminal states
    for task in data["items"]:
        assert task["status"] not in ["Done", "Cancelled"]


# --- Background Worker: Auto-Cancel Overdue Tasks ---


async def test_background_job_cancels_overdue_tasks(
    client: AsyncClient, db_engine, monkeypatch
) -> None:
    """
    Test that the background worker's cancellation routine transitions
    overdue, non-terminal tasks to 'Cancelled'[cite: 1].
    """
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.background import task_canceller

    headers, _ = await create_authenticated_user(
        client, "bg_worker_user", "bgworker@example.com"
    )

    # Create a task with a deadline a couple of seconds in the future
    # (valid at creation time), then let it lapse before running the sweep.
    near_future = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
    create_res = await client.post(
        "/api/v1/tasks/",
        json={"title": "Soon overdue task", "deadline": near_future},
        headers=headers,
    )
    task_id = create_res.json()["id"]

    await asyncio.sleep(2.5)

    # The worker normally binds to the real (Postgres) AsyncSessionLocal.
    # Point it at a session factory backed by the same test engine instead.
    test_session_maker = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(task_canceller, "AsyncSessionLocal", test_session_maker)

    cancelled_count = await task_canceller.cancel_overdue_tasks()
    assert cancelled_count >= 1

    check_res = await client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert check_res.json()["status"] == "Cancelled"
