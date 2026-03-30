import os
from pathlib import Path

import aiosqlite
from dotenv import dotenv_values, set_key
from passlib.context import CryptContext

try:
    import asyncpg
except ImportError:
    asyncpg = None


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ENV_PATH = Path(__file__).resolve().parent / ".env"


def is_postgres_url(database_url: str) -> bool:
    return database_url.startswith("postgresql://") or database_url.startswith("postgres://")


def sqlite_path_from_url(database_url: str) -> str:
    if database_url.startswith("sqlite:///"):
        return database_url[len("sqlite:///") :]
    if database_url.startswith("sqlite://"):
        return database_url[len("sqlite://") :]
    return database_url


async def initialize_database(
    database_url: str,
    admin_username: str,
    admin_password: str,
    system_api_base: str,
    system_api_key: str,
    system_model: str,
):
    if is_postgres_url(database_url):
        await _initialize_postgres(
            database_url,
            admin_username,
            admin_password,
            system_api_base,
            system_api_key,
            system_model,
        )
        return

    await _initialize_sqlite(
        database_url,
        admin_username,
        admin_password,
        system_api_base,
        system_api_key,
        system_model,
    )


async def _initialize_postgres(
    database_url: str,
    admin_username: str,
    admin_password: str,
    system_api_base: str,
    system_api_key: str,
    system_model: str,
):
    if asyncpg is None:
        raise RuntimeError("当前环境未安装 asyncpg，无法初始化 PostgreSQL。")

    conn = await asyncpg.connect(database_url)
    try:
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

        try:
            await conn.execute("ALTER TABLE conversations ADD COLUMN model VARCHAR NOT NULL DEFAULT 'gpt-4o'")
        except Exception:
            pass

        try:
            await conn.execute("ALTER TABLE users ADD COLUMN allowed_models VARCHAR DEFAULT NULL")
        except Exception:
            pass

        try:
            await conn.execute("ALTER TABLE system_config ADD COLUMN model_aliases TEXT")
        except Exception:
            pass

        await conn.execute(
            """
            INSERT INTO system_config (id, api_key, api_base, default_model, updated_at)
            VALUES (1, $1, $2, $3, CURRENT_TIMESTAMP)
            ON CONFLICT (id) DO UPDATE
            SET api_key = EXCLUDED.api_key,
                api_base = EXCLUDED.api_base,
                default_model = EXCLUDED.default_model,
                updated_at = CURRENT_TIMESTAMP
            """,
            system_api_key,
            system_api_base,
            system_model,
        )

        hashed_password = pwd_context.hash(admin_password)
        existing_user = await conn.fetchrow("SELECT id FROM users WHERE username = $1", admin_username)
        if existing_user:
            await conn.execute(
                """
                UPDATE users
                SET password = $1, model = $2, is_admin = 1
                WHERE username = $3
                """,
                hashed_password,
                system_model,
                admin_username,
            )
        else:
            await conn.execute(
                """
                INSERT INTO users (username, password, api_key, api_base, model, is_admin)
                VALUES ($1, $2, '', '', $3, 1)
                """,
                admin_username,
                hashed_password,
                system_model,
            )
    finally:
        await conn.close()


async def _initialize_sqlite(
    database_url: str,
    admin_username: str,
    admin_password: str,
    system_api_base: str,
    system_api_key: str,
    system_model: str,
):
    db_path = sqlite_path_from_url(database_url)
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    try:
        await conn.execute("PRAGMA foreign_keys = ON")
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

        await conn.execute(
            """
            INSERT INTO system_config (id, api_key, api_base, default_model, updated_at)
            VALUES (1, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                api_key = excluded.api_key,
                api_base = excluded.api_base,
                default_model = excluded.default_model,
                updated_at = CURRENT_TIMESTAMP
            """,
            (system_api_key, system_api_base, system_model),
        )

        hashed_password = pwd_context.hash(admin_password)
        cursor = await conn.execute("SELECT id FROM users WHERE username = ?", (admin_username,))
        existing_user = await cursor.fetchone()
        if existing_user:
            await conn.execute(
                """
                UPDATE users
                SET password = ?, model = ?, is_admin = 1
                WHERE username = ?
                """,
                (hashed_password, system_model, admin_username),
            )
        else:
            await conn.execute(
                """
                INSERT INTO users (username, password, api_key, api_base, model, is_admin)
                VALUES (?, ?, '', '', ?, 1)
                """,
                (admin_username, hashed_password, system_model),
            )

        await conn.commit()
    finally:
        await conn.close()


def write_env_file(
    database_url: str,
    admin_username: str,
    admin_password: str,
    system_api_base: str,
    system_api_key: str,
    system_model: str,
):
    if not ENV_PATH.exists():
        ENV_PATH.touch()

    values = dotenv_values(ENV_PATH)
    if "SECRET_KEY" not in values:
        set_key(str(ENV_PATH), "SECRET_KEY", "change-this-secret-key-in-production-please")
    if "ENV" not in values:
        set_key(str(ENV_PATH), "ENV", "development")

    set_key(str(ENV_PATH), "DATABASE_URL", database_url)
    set_key(str(ENV_PATH), "BOOTSTRAP_ADMIN_USERNAME", admin_username)
    set_key(str(ENV_PATH), "BOOTSTRAP_ADMIN_PASSWORD", admin_password)
    set_key(str(ENV_PATH), "BOOTSTRAP_SYSTEM_API_BASE", system_api_base)
    set_key(str(ENV_PATH), "BOOTSTRAP_SYSTEM_API_KEY", system_api_key)
    set_key(str(ENV_PATH), "BOOTSTRAP_SYSTEM_MODEL", system_model)
    set_key(str(ENV_PATH), "SETUP_WIZARD_ENABLED", "false")
