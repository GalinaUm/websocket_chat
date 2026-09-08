# WebSocket Chat

Чат на вебсокетах: комнаты, переписка в реальном времени, статусы онлайн, заявки на вступление и приглашения.

## Возможности

- Регистрация и вход (JWT)
- Комнаты: создание (с лимитом на пользователя), список, блок «Мои комнаты»
- Сообщения: отправка, история, удаление, редактирование
- Заявки на вступление: «постучаться», создатель принимает/отклоняет
- Приглашение участника по имени (только создатель)
- Статусы онлайн и счётчик участников в реальном времени (Redis pub/sub)
- Индикатор «печатает…»
- Счётчик непрочитанных сообщений
- Поиск пользователей

## Стек

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0 (sync), PostgreSQL, Redis, Alembic, python-jose, passlib
- **Frontend**: Vite + TypeScript (vanilla, без фреймворков), WebSocket API

## Структура

```
app/                  бэкенд
  api/                роутеры (auth, rooms, users, ws)
  core/               конфиг и безопасность
  models/             SQLAlchemy-модели
  schemas/            Pydantic-схемы
  main.py             точка входа FastAPI
alembic/              миграции БД
frontend/             Vite-приложение
tests/, test_ws*.py   тесты
```

## Локальный запуск

### 1. База данных и Redis

Нужны работающие PostgreSQL и Redis. Дефолтные URL (см. `app/core/config.py`):

```
DATABASE_URL=postgresql+psycopg://postgres:1234@localhost:5432/websocket_chat
REDIS_URL=redis://127.0.0.1:6379/0
```

### 2. Бэкенд

```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt   # Windows; на *nix: venv/bin/pip

venv\Scripts\python -m alembic upgrade head   # применить миграции
venv\Scripts\python -m uvicorn app.main:app --reload
```

Сервер поднимется на `http://127.0.0.1:8000`, интерактивная документация — `/docs`.

### 3. Фронтенд

```bash
cd frontend
npm install
npm run dev
```

Откройте `http://localhost:5173`. Vite проксирует `/auth`, `/rooms`, `/users`, `/ws` на бэкенд.

## Конфигурация

Переменные окружения. Шаблон — `.env.example`, рабочий файл `.env` (в гите игнорируется), оба читаются через pydantic-settings из корня бэкенда:

| Переменная | Дефолт | Описание |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:1234@localhost:5432/websocket_chat` | Подключение к БД |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis (pub/sub комнат, статусы онлайн) |
| `MAX_ROOMS_PER_USER` | `20` | Лимит комнат на пользователя |
| `SECRET_KEY` | `change-me-in-production` | Ключ подписи JWT — **сгенерируйте свой** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Срок жизни access-токена |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Разрешённые origins (JSON-массив) |

## REST API

| Метод | Путь | Описание |
|---|---|---|
| POST | `/auth/register` | Регистрация |
| POST | `/auth/login` | Вход, возвращает токен |
| GET | `/auth/me` | Текущий пользователь |
| GET | `/rooms` | Список комнат |
| POST | `/rooms` | Создать комнату |
| GET | `/rooms/stats` | Счётчики (мои комнаты, лимит, всего) |
| GET | `/rooms/mine` | ID комнат текущего пользователя |
| GET | `/rooms/unread` | Непрочитанные по комнатам |
| POST | `/rooms/{id}/request` | «Постучаться» в комнату |
| POST | `/rooms/{id}/invite` | Пригласить пользователя по имени (создатель) |
| GET | `/users/?q=` | Поиск пользователей |

## WebSocket: `/ws/rooms/{room_id}?token=<JWT>`

Только участники комнаты. Формат сообщений — JSON `{"type": "...", ...}`.

**Клиент → сервер:**

| Тип | Поля | Описание |
|---|---|---|
| `get_messages` | — | История сообщений |
| `send_message` | `content` | Отправить сообщение |
| `delete_message` | `message_id` | Удалить (автор или создатель) |
| `edit_message` | `message_id`, `content` | Изменить (автор) |
| `get_members` | — | Участники со статусами онлайн |
| `typing` | — | Индикатор «печатает…» |
| `get_requests` | — | Входящие заявки (создатель) |
| `approve_request` / `reject_request` | `request_id` | Обработать заявку |
| `delete_room` | — | Удалить комнату (создатель) |
| `leave_room` | — | Покинуть комнату |

**Сервер → клиент:** `welcome`, `history`, `new_message`, `members`, `requests`, `member_joined`, `member_left`, `message_deleted`, `message_edited`, `request_resolved`, `typing`, `room_deleted`, `error`.