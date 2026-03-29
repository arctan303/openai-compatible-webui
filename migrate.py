import asyncio
import aiosqlite

async def fix():
    async with aiosqlite.connect('data/chat.db') as db:
        # Add allowed_models column if missing
        try:
            await db.execute("ALTER TABLE users ADD COLUMN allowed_models TEXT DEFAULT NULL")
            await db.commit()
            print("Added allowed_models column")
        except Exception:
            print("allowed_models column already exists")

        # Update admin credentials
        await db.execute(
            "UPDATE users SET api_key=?, api_base=? WHERE username='admin'",
            ('sk-kD3ZqjwMCrEQzTBVQ', 'https://api.arctan.top/v1')
        )
        await db.commit()

        cur = await db.execute("SELECT id, username, api_key, api_base, model, is_admin FROM users")
        rows = await cur.fetchall()
        print("\nCurrent users:")
        for r in rows:
            print(f"  id={r[0]} username={r[1]} api_base={r[3]} model={r[4]} is_admin={r[5]}")

asyncio.run(fix())
