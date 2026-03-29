import aiosqlite
import os
from config import DATABASE_URL
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def init_db():
    os.makedirs(os.path.dirname(DATABASE_URL) if os.path.dirname(DATABASE_URL) else ".", exist_ok=True)
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                api_key TEXT NOT NULL,
                api_base TEXT DEFAULT 'https://api.openai.com/v1',
                model TEXT DEFAULT 'gpt-4o',
                allowed_models TEXT DEFAULT NULL,
                is_admin INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.commit()

        # Migration: add allowed_models column if missing
        try:
            await db.execute("ALTER TABLE users ADD COLUMN allowed_models TEXT DEFAULT NULL")
            await db.commit()
        except Exception:
            pass  # Column already exists

        # Create default admin if no users exist
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        count = (await cursor.fetchone())[0]
        if count == 0:
            hashed = pwd_context.hash("admin123")
            await db.execute(
                "INSERT INTO users (username, password, api_key, api_base, model, is_admin) VALUES (?, ?, ?, ?, ?, ?)",
                ("admin", hashed, "sk-kD3ZqjwMCrEQzTBVQ", "https://api.arctan.top/v1", "gpt-4o", 1)
            )
            await db.commit()
            print("✅ Default admin created: admin / admin123")


async def get_user_by_username(username: str):
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_user_by_id(user_id: int):
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def get_admin_config():
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT api_base, api_key FROM users WHERE is_admin = 1 ORDER BY id ASC LIMIT 1")
        row = await cursor.fetchone()
        return dict(row) if row else None

async def get_all_users():
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT id, username, api_key, api_base, model, allowed_models, is_admin, created_at FROM users ORDER BY id")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def create_user(username: str, password: str, api_key: str = "", api_base: str = "", model: str = "gpt-4o", is_admin: int = 0, allowed_models: str = None):
    hashed = pwd_context.hash(password)
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute(
            "INSERT INTO users (username, password, api_key, api_base, model, allowed_models, is_admin) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username, hashed, api_key, api_base, model, allowed_models, is_admin)
        )
        await db.commit()


async def update_user(user_id: int, data: dict):
    if "password" in data and data["password"]:
        data["password"] = pwd_context.hash(data["password"])
    elif "password" in data:
        del data["password"]

    if not data:
        return

    fields = ", ".join(f"{k} = ?" for k in data)
    values = list(data.values()) + [user_id]
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute(f"UPDATE users SET {fields} WHERE id = ?", values)
        await db.commit()


async def delete_user(user_id: int):
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await db.commit()


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
