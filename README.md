# Task Management API

REST API для системи управління задачами, побудований на FastAPI, SQLAlchemy (async) та PostgreSQL.

## Стек

- FastAPI
- SQLAlchemy 2.0 (async) + asyncpg
- PostgreSQL 17
- Alembic (міграції)
- Pydantic v2
- JWT-автентифікація (PyJWT + bcrypt)
- Docker Compose
- Pytest (pytest-asyncio, httpx, aiosqlite для тестової БД в памʼяті)
- Background Tasks (asyncio-воркер для автоскасування прострочених задач)

## Запуск через Docker Compose

```bash
docker compose up --build
```

Це підніме:
- `db` — PostgreSQL 17 на порту `5434` (host) → `5432` (container)
- `api` — FastAPI застосунок на порту `8000`, автоматично застосовує Alembic-міграції при старті

API буде доступне на `http://localhost:8000`, інтерактивна документація — на `http://localhost:8000/docs`.

## Локальний запуск (без Docker)

1. Скопіюйте `.envexample` у `.env` та заповніть значення (`DATABASE_URL`, `SECRET_KEY`, ...).
2. Встановіть залежності:
   ```bash
   pip install -r requirements.txt
   ```
3. Підніміть PostgreSQL локально (наприклад, тільки сервіс `db` з docker-compose):
   ```bash
   docker compose up db
   ```
4. Застосуйте міграції:
   ```bash
   alembic upgrade head
   ```
5. Запустіть сервер:
   ```bash
   uvicorn app.main:app --reload
   ```

## Тести

Тести використовують окрему SQLite-базу в памʼяті (через `aiosqlite`) і не потребують запущеного PostgreSQL.

```bash
pytest
```

## Основні ендпоінти

| Метод | Шлях | Опис |
|---|---|---|
| POST | `/api/v1/auth/register` | Реєстрація користувача |
| POST | `/api/v1/auth/login` | Авторизація, видача JWT |
| GET | `/api/v1/auth/me` | Профіль поточного користувача |
| POST | `/api/v1/tasks/` | Створення задачі |
| GET | `/api/v1/tasks/` | Список задач (пошук, фільтри, сортування, пагінація) |
| GET | `/api/v1/tasks/overdue` | Прострочені задачі |
| GET | `/api/v1/tasks/statistics` | Статистика по задачам |
| GET | `/api/v1/tasks/{task_id}` | Отримати задачу |
| PUT | `/api/v1/tasks/{task_id}` | Оновити задачу |
| PATCH | `/api/v1/tasks/{task_id}/status` | Змінити статус задачі |
| DELETE | `/api/v1/tasks/{task_id}` | Видалити задачу |
| POST | `/api/v1/tasks/{task_id}/comments` | Додати коментар |
| GET | `/api/v1/tasks/{task_id}/comments` | Список коментарів |

## Бізнес-правила

- Статуси задач: `Backlog → In Progress → Review → Done`, а також перехід у `Cancelled` з `Backlog`/`In Progress`/`Review`. Повернення на попередній статус заборонено.
- Перехід у `Done` вимагає призначеного виконавця та дедлайну, що ще не минув.
- Задачі у `Review`/`Done` не можна перепризначати; задачі у `Done`/`Cancelled` не можна редагувати.
- Видалення можливе лише поза статусами `In Progress`/`Review`.
- Один користувач — не більше 10 активних задач (`Backlog`, `In Progress`, `Review`) одночасно.
- Фоновий воркер (`app/background/task_canceller.py`) раз на хвилину переводить прострочені задачі у `Cancelled`.
