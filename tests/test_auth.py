import pytest
from fastapi import status
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_register_success(client: AsyncClient) -> None:
    """A new user can register and receives their public profile back."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "new_user",
            "email": "newuser@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["username"] == "new_user"
    assert data["email"] == "newuser@example.com"
    assert "id" in data
    assert "password" not in data
    assert "hashed_password" not in data


async def test_register_duplicate_email_fails(client: AsyncClient) -> None:
    """Registering with an email that is already taken is rejected."""
    payload = {
        "username": "first_user",
        "email": "duplicate@example.com",
        "password": "StrongPassword123!",
    }
    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == status.HTTP_201_CREATED

    payload_two = {**payload, "username": "second_user"}
    second = await client.post("/api/v1/auth/register", json=payload_two)
    assert second.status_code == status.HTTP_400_BAD_REQUEST
    assert "email" in second.json()["detail"].lower()


async def test_register_duplicate_username_fails(client: AsyncClient) -> None:
    """Registering with a username that is already taken is rejected."""
    payload = {
        "username": "taken_username",
        "email": "user1@example.com",
        "password": "StrongPassword123!",
    }
    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == status.HTTP_201_CREATED

    payload_two = {**payload, "email": "user2@example.com"}
    second = await client.post("/api/v1/auth/register", json=payload_two)
    assert second.status_code == status.HTTP_400_BAD_REQUEST
    assert "username" in second.json()["detail"].lower()


async def test_register_weak_password_rejected(client: AsyncClient) -> None:
    """Passwords shorter than the minimum length fail validation."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "weak_pw_user",
            "email": "weakpw@example.com",
            "password": "short",
        },
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_login_success(client: AsyncClient) -> None:
    """A registered user can log in with correct credentials and receive a JWT."""
    await client.post(
        "/api/v1/auth/register",
        json={
            "username": "login_user",
            "email": "login@example.com",
            "password": "StrongPassword123!",
        },
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "StrongPassword123!"},
    )
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password_fails(client: AsyncClient) -> None:
    """Logging in with an incorrect password is rejected with 401."""
    await client.post(
        "/api/v1/auth/register",
        json={
            "username": "wrongpw_user",
            "email": "wrongpw@example.com",
            "password": "StrongPassword123!",
        },
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpw@example.com", "password": "IncorrectPassword"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_login_nonexistent_user_fails(client: AsyncClient) -> None:
    """Logging in with an email that was never registered is rejected."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "SomePassword123!"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_get_current_user_profile(client: AsyncClient) -> None:
    """An authenticated user can fetch their own profile via /auth/me."""
    await client.post(
        "/api/v1/auth/register",
        json={
            "username": "profile_user",
            "email": "profile@example.com",
            "password": "StrongPassword123!",
        },
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "profile@example.com", "password": "StrongPassword123!"},
    )
    token = login_res.json()["access_token"]

    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["username"] == "profile_user"


async def test_get_current_user_profile_without_token_fails(client: AsyncClient) -> None:
    """Accessing /auth/me without a bearer token is rejected."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_get_current_user_profile_invalid_token_fails(client: AsyncClient) -> None:
    """Accessing /auth/me with a malformed/invalid token is rejected."""
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
