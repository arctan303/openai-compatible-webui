import json
import os
from contextlib import asynccontextmanager

import aiosqlite
from passlib.context import CryptContext
try:
    import asyncpg
except ImportError:  # Local SQLite mode can run without PostgreSQL driver.
    asyncpg = None

from config import (
    DATABASE_URL,
    BOOTSTRAP_ADMIN_USERNAME,
    BOOTSTRAP_ADMIN_PASSWORD,
    BOOTSTRAP_SYSTEM_API_KEY,
    BOOTSTRAP_SYSTEM_API_BASE,
    BOOTSTRAP_SYSTEM_MODEL,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DB_URL = DATABASE_URL
IS_POSTGRES = DB_URL.startswith("postgresql://") or DB_URL.startswith("postgres://")

_UPDATABLE_USER_FIELDS = {"password", "api_key", "model", "is_admin", "allowed_models"}
_UPDATABLE_SYSTEM_FIELDS = {"api_key", "api_base", "default_model", "model_aliases"}


def _sqlite_path() -> str:
    if DB_URL.startswith("sqlite:///"):
        return DB_URL[len("sqlite:///") :]
    if DB_URL.startswith("sqlite://"):
        return DB_URL[len("sqlite://") :]
    return DB_URL


@asynccontextmanager
async def _sqlite_conn():
    path = _sqlite_path()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = await aiosqlite.connect(path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        await conn.close()


async def get_db_pool():
    if not IS_POSTGRES:
        raise RuntimeError("Connection pool is only available for PostgreSQL")
    if asyncpg is None:
        raise RuntimeError("asyncpg is required for PostgreSQL mode")
    if not hasattr(get_db_pool, "_pool"):
        get_db_pool._pool = await asyncpg.create_pool(DB_URL)
    return get_db_pool._pool


async def _init_postgres():
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR UNIQUE NOT NULL,
                password VARCHAR NOT NULL,
                api_key VARCHAR,
                api_base VARCHAR DEFAULT 'https://api.openai.com/v1',
                model VARCHAR DEFAULT 'gpt-4o',
                allowed_models VARCHAR DEFAULT NULL,
                is_admin SMALLINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id VARCHAR PRIMARY KEY,
                user_id INT REFERENCES users(id) ON DELETE CASCADE,
                title VARCHAR NOT NULL,
                messages JSONB NOT NULL DEFAULT '[]',
                model VARCHAR NOT NULL DEFAULT 'gpt-4o',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                id SMALLINT PRIMARY KEY DEFAULT 1,
                api_key VARCHAR NOT NULL DEFAULT '',
                api_base VARCHAR NOT NULL DEFAULT 'https://api.openai.com/v1',
                default_model VARCHAR NOT NULL DEFAULT 'gpt-4o',
                model_aliases TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT system_config_singleton CHECK (id = 1)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS model_usage (
                user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                model VARCHAR NOT NULL,
                request_count INT NOT NULL DEFAULT 0,
                prompt_tokens INT NOT NULL DEFAULT 0,
                completion_tokens INT NOT NULL DEFAULT 0,
                total_tokens INT NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, model)
            )
        """)

        await conn.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS model VARCHAR NOT NULL DEFAULT 'gpt-4o'")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS allowed_models VARCHAR DEFAULT NULL")
        await conn.execute("ALTER TABLE system_config ADD COLUMN IF NOT EXISTS model_aliases TEXT")
        await conn.execute("ALTER TABLE model_usage ADD COLUMN IF NOT EXISTS prompt_tokens INT NOT NULL DEFAULT 0")
        await conn.execute("ALTER TABLE model_usage ADD COLUMN IF NOT EXISTS completion_tokens INT NOT NULL DEFAULT 0")
        await conn.execute("ALTER TABLE model_usage ADD COLUMN IF NOT EXISTS total_tokens INT NOT NULL DEFAULT 0")

        system_count = await conn.fetchval("SELECT COUNT(*) FROM system_config")
        if system_count == 0:
            admin_row = await conn.fetchrow(
                "SELECT api_key, api_base, model FROM users WHERE is_admin = 1 ORDER BY id ASC LIMIT 1"
            )
            seeded_api_key = BOOTSTRAP_SYSTEM_API_KEY
            seeded_api_base = BOOTSTRAP_SYSTEM_API_BASE
            seeded_model = BOOTSTRAP_SYSTEM_MODEL
            if admin_row:
                seeded_api_key = admin_row["api_key"] or seeded_api_key
                seeded_api_base = admin_row["api_base"] or seeded_api_base
                seeded_model = admin_row["model"] or seeded_model
            await conn.execute(
                """
                INSERT INTO system_config (id, api_key, api_base, default_model, updated_at)
                VALUES (1, $1, $2, $3, CURRENT_TIMESTAMP)
                """,
                seeded_api_key,
                seeded_api_base,
                seeded_model,
            )

        count = await conn.fetchval("SELECT COUNT(*) FROM users")
        if count == 0:
            hashed = pwd_context.hash(BOOTSTRAP_ADMIN_PASSWORD)
            await conn.execute(
                "INSERT INTO users (username, password, api_key, api_base, model, is_admin) VALUES ($1, $2, $3, $4, $5, $6)",
                BOOTSTRAP_ADMIN_USERNAME, hashed, "", "", BOOTSTRAP_SYSTEM_MODEL, 1
            )
            print(f"Default admin '{BOOTSTRAP_ADMIN_USERNAME}' created.")


async def _init_sqlite():
    async with _sqlite_conn() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                api_key TEXT DEFAULT '',
                api_base TEXT DEFAULT 'https://api.openai.com/v1',
                model TEXT DEFAULT 'gpt-4o',
                allowed_models TEXT DEFAULT NULL,
                is_admin INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                messages TEXT NOT NULL DEFAULT '[]',
                model TEXT NOT NULL DEFAULT 'gpt-4o',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                api_key TEXT NOT NULL DEFAULT '',
                api_base TEXT NOT NULL DEFAULT 'https://api.openai.com/v1',
                default_model TEXT NOT NULL DEFAULT 'gpt-4o',
                model_aliases TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS model_usage (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                model TEXT NOT NULL,
                request_count INTEGER NOT NULL DEFAULT 0,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, model)
            )
        """)

        try:
            await conn.execute("ALTER TABLE conversations ADD COLUMN model TEXT NOT NULL DEFAULT 'gpt-4o'")
        except Exception:
            pass

        try:
            await conn.execute("ALTER TABLE users ADD COLUMN allowed_models TEXT DEFAULT NULL")
        except Exception:
            pass

        try:
            await conn.execute("ALTER TABLE system_config ADD COLUMN model_aliases TEXT")
        except Exception:
            pass

        try:
            await conn.execute("ALTER TABLE model_usage ADD COLUMN prompt_tokens INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass

        try:
            await conn.execute("ALTER TABLE model_usage ADD COLUMN completion_tokens INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass

        try:
            await conn.execute("ALTER TABLE model_usage ADD COLUMN total_tokens INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass

        cursor = await conn.execute("SELECT COUNT(*) FROM system_config")
        system_count = (await cursor.fetchone())[0]
        if system_count == 0:
            cursor = await conn.execute(
                "SELECT api_key, api_base, model FROM users WHERE is_admin = 1 ORDER BY id ASC LIMIT 1"
            )
            admin_row = await cursor.fetchone()
            seeded_api_key = BOOTSTRAP_SYSTEM_API_KEY
            seeded_api_base = BOOTSTRAP_SYSTEM_API_BASE
            seeded_model = BOOTSTRAP_SYSTEM_MODEL
            if admin_row:
                seeded_api_key = admin_row["api_key"] or seeded_api_key
                seeded_api_base = admin_row["api_base"] or seeded_api_base
                seeded_model = admin_row["model"] or seeded_model
            await conn.execute(
                """
                INSERT INTO system_config (id, api_key, api_base, default_model, updated_at)
                VALUES (1, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (seeded_api_key, seeded_api_base, seeded_model),
            )

        cursor = await conn.execute("SELECT COUNT(*) FROM users")
        count = (await cursor.fetchone())[0]
        if count == 0:
            hashed = pwd_context.hash(BOOTSTRAP_ADMIN_PASSWORD)
            await conn.execute(
                "INSERT INTO users (username, password, api_key, api_base, model, is_admin) VALUES (?, ?, ?, ?, ?, ?)",
                (BOOTSTRAP_ADMIN_USERNAME, hashed, "", "", BOOTSTRAP_SYSTEM_MODEL, 1),
            )
            print(f"Default admin '{BOOTSTRAP_ADMIN_USERNAME}' created.")

        await conn.commit()


async def init_db():
    if IS_POSTGRES:
        await _init_postgres()
    else:
        await _init_sqlite()


async def get_user_by_username(username: str):
    if IS_POSTGRES:
        pool = await get_db_pool()
        row = await pool.fetchrow("SELECT * FROM users WHERE username = $1", username)
        return dict(row) if row else None

    async with _sqlite_conn() as conn:
        cursor = await conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_user_by_id(user_id: int):
    if IS_POSTGRES:
        pool = await get_db_pool()
        row = await pool.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
        return dict(row) if row else None

    async with _sqlite_conn() as conn:
        cursor = await conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_system_config():
    if IS_POSTGRES:
        pool = await get_db_pool()
        row = await pool.fetchrow("SELECT api_base, api_key, default_model, model_aliases FROM system_config WHERE id = 1")
        return dict(row) if row else None

    async with _sqlite_conn() as conn:
        cursor = await conn.execute("SELECT api_base, api_key, default_model, model_aliases FROM system_config WHERE id = 1")
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_system_config(data: dict):
    if not data:
        return

    for key in data:
        if key not in _UPDATABLE_SYSTEM_FIELDS:
            raise ValueError(f"Disallowed system field: {key}")

    if IS_POSTGRES:
        set_clauses = []
        values = []
        for i, (key, value) in enumerate(data.items(), 1):
            set_clauses.append(f"{key} = ${i}")
            values.append(value)
        values.append(1)
        fields = ", ".join(set_clauses + ["updated_at = CURRENT_TIMESTAMP"])
        query = f"UPDATE system_config SET {fields} WHERE id = ${len(values)}"
        pool = await get_db_pool()
        await pool.execute(query, *values)
        return

    set_clauses = ", ".join(f"{key} = ?" for key in data)
    values = list(data.values()) + [1]
    async with _sqlite_conn() as conn:
        await conn.execute(
            f"UPDATE system_config SET {set_clauses}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values,
        )
        await conn.commit()


async def get_all_users():
    if IS_POSTGRES:
        pool = await get_db_pool()
        rows = await pool.fetch("SELECT id, username, api_key, model, allowed_models, is_admin, created_at FROM users ORDER BY id")
        return [dict(row) for row in rows]

    async with _sqlite_conn() as conn:
        cursor = await conn.execute(
            "SELECT id, username, api_key, model, allowed_models, is_admin, created_at FROM users ORDER BY id"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def create_user(
    username: str,
    password: str,
    api_key: str = "",
    model: str = "gpt-4o",
    is_admin: int = 0,
    allowed_models: str = None,
):
    hashed = pwd_context.hash(password)
    if IS_POSTGRES:
        pool = await get_db_pool()
        await pool.execute(
            "INSERT INTO users (username, password, api_key, model, allowed_models, is_admin) VALUES ($1, $2, $3, $4, $5, $6)",
            username, hashed, api_key, model, allowed_models, is_admin
        )
        return

    async with _sqlite_conn() as conn:
        await conn.execute(
            "INSERT INTO users (username, password, api_key, model, allowed_models, is_admin) VALUES (?, ?, ?, ?, ?, ?)",
            (username, hashed, api_key, model, allowed_models, is_admin),
        )
        await conn.commit()


async def update_user(user_id: int, data: dict):
    if "password" in data and data["password"]:
        data["password"] = pwd_context.hash(data["password"])
    elif "password" in data:
        del data["password"]

    if not data:
        return

    for key in data:
        if key not in _UPDATABLE_USER_FIELDS:
            raise ValueError(f"Disallowed field: {key}")

    if IS_POSTGRES:
        set_clauses = []
        values = []
        for i, (key, value) in enumerate(data.items(), 1):
            set_clauses.append(f"{key} = ${i}")
            values.append(value)
        values.append(user_id)
        query = f"UPDATE users SET {', '.join(set_clauses)} WHERE id = ${len(values)}"
        pool = await get_db_pool()
        await pool.execute(query, *values)
        return

    values = list(data.values()) + [user_id]
    set_clauses = ", ".join(f"{key} = ?" for key in data)
    async with _sqlite_conn() as conn:
        await conn.execute(f"UPDATE users SET {set_clauses} WHERE id = ?", values)
        await conn.commit()


async def delete_user(user_id: int):
    if IS_POSTGRES:
        pool = await get_db_pool()
        await pool.execute("DELETE FROM users WHERE id = $1", user_id)
        return

    async with _sqlite_conn() as conn:
        await conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await conn.commit()


async def record_model_usage(user_id: int, model: str, prompt_tokens: int = 0, completion_tokens: int = 0, total_tokens: int = 0):
    if not model:
        return

    prompt_tokens = max(0, int(prompt_tokens or 0))
    completion_tokens = max(0, int(completion_tokens or 0))
    total_tokens = max(0, int(total_tokens or (prompt_tokens + completion_tokens)))

    if IS_POSTGRES:
        pool = await get_db_pool()
        await pool.execute(
            """
            INSERT INTO model_usage (user_id, model, request_count, prompt_tokens, completion_tokens, total_tokens, updated_at)
            VALUES ($1, $2, 1, $3, $4, $5, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, model) DO UPDATE SET
                request_count = model_usage.request_count + 1,
                prompt_tokens = model_usage.prompt_tokens + EXCLUDED.prompt_tokens,
                completion_tokens = model_usage.completion_tokens + EXCLUDED.completion_tokens,
                total_tokens = model_usage.total_tokens + EXCLUDED.total_tokens,
                updated_at = CURRENT_TIMESTAMP
            """,
            user_id,
            model,
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )
        return

    async with _sqlite_conn() as conn:
        await conn.execute(
            """
            INSERT INTO model_usage (user_id, model, request_count, prompt_tokens, completion_tokens, total_tokens, created_at, updated_at)
            VALUES (?, ?, 1, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, model) DO UPDATE SET
                request_count = request_count + 1,
                prompt_tokens = prompt_tokens + excluded.prompt_tokens,
                completion_tokens = completion_tokens + excluded.completion_tokens,
                total_tokens = total_tokens + excluded.total_tokens,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, model, prompt_tokens, completion_tokens, total_tokens),
        )
        await conn.commit()


async def get_model_usage_rows():
    if IS_POSTGRES:
        pool = await get_db_pool()
        rows = await pool.fetch(
            """
            SELECT user_id, model, request_count, prompt_tokens, completion_tokens, total_tokens, created_at, updated_at
            FROM model_usage
            ORDER BY total_tokens DESC, request_count DESC, updated_at DESC, user_id ASC, model ASC
            """
        )
        return [
            {
                "user_id": row["user_id"],
                "model": row["model"],
                "request_count": row["request_count"],
                "prompt_tokens": row["prompt_tokens"],
                "completion_tokens": row["completion_tokens"],
                "total_tokens": row["total_tokens"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            }
            for row in rows
        ]

    async with _sqlite_conn() as conn:
        cursor = await conn.execute(
            """
            SELECT user_id, model, request_count, prompt_tokens, completion_tokens, total_tokens, created_at, updated_at
            FROM model_usage
            ORDER BY total_tokens DESC, request_count DESC, updated_at DESC, user_id ASC, model ASC
            """
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


async def get_conversations(user_id: int):
    if IS_POSTGRES:
        pool = await get_db_pool()
        rows = await pool.fetch(
            "SELECT id, title, messages, model, created_at, updated_at FROM conversations WHERE user_id = $1 ORDER BY updated_at DESC",
            user_id,
        )
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "messages": json.loads(row["messages"]) if isinstance(row["messages"], str) else (row["messages"] or []),
                "model": row["model"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            }
            for row in rows
        ]

    async with _sqlite_conn() as conn:
        cursor = await conn.execute(
            "SELECT id, title, messages, model, created_at, updated_at FROM conversations WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "messages": json.loads(row["messages"] or "[]"),
                "model": row["model"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]


async def save_conversation(conv_id: str, user_id: int, title: str, messages: list, model: str):
    msg_json = json.dumps(messages)
    if IS_POSTGRES:
        pool = await get_db_pool()
        await pool.execute(
            """
            INSERT INTO conversations (id, user_id, title, messages, model, updated_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, CURRENT_TIMESTAMP)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                messages = EXCLUDED.messages,
                model = EXCLUDED.model,
                updated_at = CURRENT_TIMESTAMP
            """,
            conv_id, user_id, title, msg_json, model
        )
        return

    async with _sqlite_conn() as conn:
        await conn.execute(
            """
            INSERT INTO conversations (id, user_id, title, messages, model, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                messages = excluded.messages,
                model = excluded.model,
                updated_at = CURRENT_TIMESTAMP
            """,
            (conv_id, user_id, title, msg_json, model),
        )
        await conn.commit()


async def delete_conversation(conv_id: str, user_id: int):
    if IS_POSTGRES:
        pool = await get_db_pool()
        await pool.execute("DELETE FROM conversations WHERE id = $1 AND user_id = $2", conv_id, user_id)
        return

    async with _sqlite_conn() as conn:
        await conn.execute("DELETE FROM conversations WHERE id = ? AND user_id = ?", (conv_id, user_id))
        await conn.commit()
