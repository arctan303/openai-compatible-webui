# AI Chat

FastAPI chat service with two install modes:

- PostgreSQL with Docker: recommended for service deployment
- SQLite file mode: useful for lightweight local use

## Quick Start

Clone the repo, then run:

```powershell
.\install.ps1
```

The installer will ask which storage mode you want:

1. `PostgreSQL with Docker`
2. `SQLite file mode`

It writes `.env` for you.

## PostgreSQL Mode

Recommended for real deployment.

What the installer does:

- writes Docker/PostgreSQL settings into `.env`
- sets bootstrap admin and system config
- can start `app + postgres` with `docker compose up -d --build`

Manual start command:

```powershell
docker compose up -d --build
```

Default services in [docker-compose.yml](C:/git/ai-chat/docker-compose.yml):

- `app`
- `postgres`

## SQLite Mode

Useful when you do not want a database service.

The installer writes:

```env
DATABASE_URL=sqlite:///data/chat.db
```

Then run the app locally:

```powershell
py -3.13 main.py
```

SQLite database file:

- [chat.db](C:/git/ai-chat/data/chat.db)

## Bootstrap Rules

These values are used for first initialization:

- `BOOTSTRAP_ADMIN_USERNAME`
- `BOOTSTRAP_ADMIN_PASSWORD`
- `BOOTSTRAP_SYSTEM_API_BASE`
- `BOOTSTRAP_SYSTEM_API_KEY`
- `BOOTSTRAP_SYSTEM_MODEL`

Runtime system config is stored in the database after initialization.

## One-Time Setup Wizard

There is also an admin-only setup wizard at `/setup`.

Rules:

- you must log in as admin first
- the wizard is controlled by `SETUP_WIZARD_ENABLED`
- after successful initialization, the app writes `SETUP_WIZARD_ENABLED=false` into `.env`
- after that, changing database/bootstrap config should be done by editing `.env` and restarting
