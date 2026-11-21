import aiosqlite
import time

DB_NAME = "casino.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance INTEGER DEFAULT 1000,
                btc REAL DEFAULT 0,
                bank_wallet INTEGER DEFAULT 0,
                last_passive INTEGER DEFAULT 0,
                last_courier INTEGER DEFAULT 0,
                last_builder INTEGER DEFAULT 0,
                last_programmer INTEGER DEFAULT 0,
                businesses TEXT DEFAULT '',
                farms TEXT DEFAULT '',
                houses TEXT DEFAULT '',
                deposit_amount INTEGER DEFAULT 0,
                deposit_end INTEGER DEFAULT 0,
                deposit_rate REAL DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0
            )
        """)
        await db.commit()

async def get_user(user_id: int, username: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as c:
            row = await c.fetchone()
        if row is None:
            await db.execute(
                "INSERT INTO users (user_id, username) VALUES (?, ?)",
                (user_id, username or "player")
            )
            await db.commit()
            async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as c:
                row = await c.fetchone()
        return dict(row)

async def update(user_id: int, **kwargs):
    async with aiosqlite.connect(DB_NAME) as db:
        sets = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [user_id]
        await db.execute(f"UPDATE users SET {sets} WHERE user_id=?", vals)
        await db.commit()

async def add_balance(user_id: int, amount: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, user_id))
        await db.commit()

async def get_top(limit: int = 10):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT username, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,)
        ) as c:
            return [dict(r) for r in await c.fetchall()]
