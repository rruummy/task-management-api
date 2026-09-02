# Task Management API

REST API for a task management system built with FastAPI, SQLAlchemy (async), and PostgreSQL.

## Stack

* FastAPI
* SQLAlchemy 2.0 (async) + asyncpg
* PostgreSQL 17
* Alembic (migrations)
* Pydantic v2
* JWT authentication (PyJWT + bcrypt)
* Docker Compose
* Pytest (pytest-asyncio, httpx, aiosqlite for the in-memory test database)
* Background Tasks (asyncio worker for automatically cancelling overdue tasks)

## Running with Docker Compose

```bash
docker compose up --build
```

This will start:

* `db` — PostgreSQL 17 on port `5434` (host) → `5432` (container)
* `api` — FastAPI application on port `8000`, automatically applying Alembic migrations on startup

The API will be available at `http://localhost:8000`, and the interactive documentation will be available at `http://localhost:8000/docs`.

## Local Run (without Docker)

1. Copy `.envexample` to `.env` and fill in the required values (`DATABASE_URL`, `SECRET_KEY`, ...).
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```
3. Start PostgreSQL locally (for example, only the `db` service from docker-compose):

   ```bash
   docker compose up db
   ```
4. Apply migrations:

   ```bash
   alembic upgrade head
   ```
5. Start the server:

   ```bash
   uvicorn app.main:app --reload
   ```

## Tests

Tests use a separate in-memory SQLite database (via `aiosqlite`) and do not require a running PostgreSQL instance.

```bash
pytest
```

## Main Endpoints

| Method | Path                               | Description                                         |
| ------ | ---------------------------------- | --------------------------------------------------- |
| POST   | `/api/v1/auth/register`            | User registration                                   |
| POST   | `/api/v1/auth/login`               | User authentication and JWT issuance                |
| GET    | `/api/v1/auth/me`                  | Current user profile                                |
| POST   | `/api/v1/tasks/`                   | Create a task                                       |
| GET    | `/api/v1/tasks/`                   | List tasks (search, filtering, sorting, pagination) |
| GET    | `/api/v1/tasks/overdue`            | Overdue tasks                                       |
| GET    | `/api/v1/tasks/statistics`         | Task statistics                                     |
| GET    | `/api/v1/tasks/{task_id}`          | Get a task                                          |
| PUT    | `/api/v1/tasks/{task_id}`          | Update a task                                       |
| PATCH  | `/api/v1/tasks/{task_id}/status`   | Change task status                                  |
| DELETE | `/api/v1/tasks/{task_id}`          | Delete a task                                       |
| POST   | `/api/v1/tasks/{task_id}/comments` | Add a comment                                       |
| GET    | `/api/v1/tasks/{task_id}/comments` | List comments                                       |

## Business Rules

* Task statuses: `Backlog → In Progress → Review → Done`, with transitions to `Cancelled` also allowed from `Backlog`/`In Progress`/`Review`. Returning to a previous status is not allowed.
* Transitioning to `Done` requires an assigned executor and a deadline that has not passed.
* Tasks in `Review`/`Done` cannot be reassigned; tasks in `Done`/`Cancelled` cannot be edited.
* Deletion is only allowed when the task is not in `In Progress`/`Review`.
* A user can have no more than 10 active tasks (`Backlog`, `In Progress`, `Review`) at the same time.
* The background worker (`app/background/task_canceller.py`) checks every minute and moves overdue tasks to `Cancelled`.
