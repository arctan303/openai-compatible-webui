import asyncpg
import os
import json
from config import DATABASE_URL, ADMIN_USERNAME, ADMIN_PASSWORD, ADMIN_API_KEY, ADMIN_API_BASE
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DB_URL = DATABASE_URL  # Already resolved from env in config.py

# Whitelist of updatable user fields to prevent SQL injection
_UPDATABLE_USER_FIELDS = {"password", "api_key", "api_base", "model", "is_admin", "allowed_models"}

async def get_db_pool():
    if not hasattr(get_db_pool, "_pool"):
        get_db_pool._pool = await asyncpg.create_pool(DB_URL)
    return get_db_pool._pool

async def init_db():
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

        try:
            await conn.execute("ALTER TABLE conversations ADD COLUMN model VARCHAR NOT NULL DEFAULT 'gpt-4o'")
        except Exception:
            pass

        try:
            await conn.execute("ALTER TABLE users ADD COLUMN allowed_models VARCHAR DEFAULT NULL")
        except asyncpg.exceptions.DuplicateColumnError:
            pass
        except Exception:
            pass

        count = await conn.fetchval("SELECT COUNT(*) FROM users")
        if count == 0:
            hashed = pwd_context.hash(ADMIN_PASSWORD)
            await conn.execute(
                "INSERT INTO users (username, password, api_key, api_base, model, is_admin) VALUES ($1, $2, $3, $4, $5, $6)",
                ADMIN_USERNAME, hashed, ADMIN_API_KEY, ADMIN_API_BASE, "gpt-4o", 1
            )
            print(f"✅ Default admin '{ADMIN_USERNAME}' created. Please change the password via the admin panel.")

async def get_user_by_username(username: str):
    pool = await get_db_pool()
    row = await pool.fetchrow("SELECT * FROM users WHERE username = $1", username)
    return dict(row) if row else None

async def get_user_by_id(user_id: int):
    pool = await get_db_pool()
    row = await pool.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    return dict(row) if row else None

async def get_admin_config():
    pool = await get_db_pool()
    row = await pool.fetchrow("SELECT api_base, api_key FROM users WHERE is_admin = 1 ORDER BY id ASC LIMIT 1")
    return dict(row) if row else None

async def get_all_users():
    pool = await get_db_pool()
    rows = await pool.fetch("SELECT id, username, api_key, api_base, model, allowed_models, is_admin, created_at FROM users ORDER BY id")
    return [dict(r) for r in rows]

async def create_user(username: str, password: str, api_key: str = "", api_base: str = "", model: str = "gpt-4o", is_admin: int = 0, allowed_models: str = None):
    hashed = pwd_context.hash(password)
    pool = await get_db_pool()
    await pool.execute(
        "INSERT INTO users (username, password, api_key, api_base, model, allowed_models, is_admin) VALUES ($1, $2, $3, $4, $5, $6, $7)",
        username, hashed, api_key, api_base, model, allowed_models, is_admin
    )

async def update_user(user_id: int, data: dict):
    if "password" in data and data["password"]:
        data["password"] = pwd_context.hash(data["password"])
    elif "password" in data:
        del data["password"]

    if not data:
        return

    pool = await get_db_pool()
    set_clauses = []
    values = []
    for i, (k, v) in enumerate(data.items(), 1):
        if k not in _UPDATABLE_USER_FIELDS:
            raise ValueError(f"Disallowed field: {k}")
        set_clauses.append(f"{k} = ${i}")
        values.append(v)
    
    values.append(user_id)
    fields = ", ".join(set_clauses)
    query = f"UPDATE users SET {fields} WHERE id = ${len(values)}"
    
    await pool.execute(query, *values)

async def delete_user(user_id: int):
    pool = await get_db_pool()
    await pool.execute("DELETE FROM users WHERE id = $1", user_id)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

async def get_conversations(user_id: int):
    pool = await get_db_pool()
    rows = await pool.fetch("SELECT id, title, messages, model, created_at, updated_at FROM conversations WHERE user_id = $1 ORDER BY updated_at DESC", user_id)
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "messages": json.loads(r["messages"]) if isinstance(r["messages"], str) else (r["messages"] or []),
            "model": r["model"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None
        }
        for r in rows
    ]

async def save_conversation(conv_id: str, user_id: int, title: str, messages: list, model: str):
    pool = await get_db_pool()
    msg_json = json.dumps(messages)
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

async def delete_conversation(conv_id: str, user_id: int):
    pool = await get_db_pool()
    await pool.execute("DELETE FROM conversations WHERE id = $1 AND user_id = $2", conv_id, user_id)
