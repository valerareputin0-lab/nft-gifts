import asyncpg
from config import DATABASE_URL

_pool = None


async def init_db():
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with _pool.acquire() as c:
        await c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                balance BIGINT DEFAULT 1000,
                btc DOUBLE PRECISION DEFAULT 0,
                bank_wallet BIGINT DEFAULT 0,
                last_passive BIGINT DEFAULT 0,
                last_courier BIGINT DEFAULT 0,
                last_builder BIGINT DEFAULT 0,
                last_programmer BIGINT DEFAULT 0,
                last_bonus BIGINT DEFAULT 0,
                businesses TEXT DEFAULT '',
                farms TEXT DEFAULT '',
                houses TEXT DEFAULT '',
                garage TEXT DEFAULT '',
                garage_bought INTEGER DEFAULT 0,
                wardrobe TEXT DEFAULT '',
                clothes_worn TEXT DEFAULT '',
                deposit_amount BIGINT DEFAULT 0,
                deposit_end BIGINT DEFAULT 0,
                deposit_rate DOUBLE PRECISION DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0
            )
        """)
        await c.execute("""
            CREATE TABLE IF NOT EXISTS promos (
                code TEXT PRIMARY KEY,
                amount BIGINT,
                limit_total INTEGER,
                used INTEGER DEFAULT 0
            )
        """)
        await c.execute("""
            CREATE TABLE IF NOT EXISTS promo_uses (
                code TEXT,
                user_id BIGINT,
                PRIMARY KEY (code, user_id)
            )
        """)


async def get_user(user_id: int, username: str = None):
    async with _pool.acquire() as c:
        row = await c.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
        if row is None:
            await c.execute(
                "INSERT INTO users (user_id, username) VALUES ($1, $2)",
                user_id, username or "player"
            )
            row = await c.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
        return dict(row)


async def get_user_by_id(user_id: int):
    async with _pool.acquire() as c:
        row = await c.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
        return dict(row) if row else None


async def update(user_id: int, **kwargs):
    if not kwargs:
        return
    async with _pool.acquire() as c:
        fields = list(kwargs.keys())
        sets = ", ".join(f"{k}=${i+2}" for i, k in enumerate(fields))
        vals = [user_id] + [kwargs[k] for k in fields]
        await c.execute(f"UPDATE users SET {sets} WHERE user_id=$1", *vals)


async def add_balance(user_id: int, amount: int):
    async with _pool.acquire() as c:
        await c.execute(
            "UPDATE users SET balance=balance+$1 WHERE user_id=$2",
            amount, user_id
        )


async def get_top(limit: int = 10):
    async with _pool.acquire() as c:
        rows = await c.fetch(
            "SELECT username, balance FROM users ORDER BY balance DESC LIMIT $1",
            limit
        )
        return [dict(r) for r in rows]


# ============ ПРОМОКОДЫ ============
async def create_promo(code: str, amount: int, limit_total: int):
    async with _pool.acquire() as c:
        await c.execute(
            "INSERT INTO promos (code, amount, limit_total, used) VALUES ($1,$2,$3,0) "
            "ON CONFLICT (code) DO UPDATE SET amount=$2, limit_total=$3, used=0",
            code.upper(), amount, limit_total
        )


async def get_promo(code: str):
    async with _pool.acquire() as c:
        row = await c.fetchrow("SELECT * FROM promos WHERE code=$1", code.upper())
        return dict(row) if row else None


async def use_promo(code: str, user_id: int):
    async with _pool.acquire() as c:
        await c.execute(
            "INSERT INTO promo_uses (code, user_id) VALUES ($1,$2) ON CONFLICT DO NOTHING",
            code.upper(), user_id
        )
        await c.execute("UPDATE promos SET used=used+1 WHERE code=$1", code.upper())


async def user_used_promo(code: str, user_id: int) -> bool:
    async with _pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT 1 FROM promo_uses WHERE code=$1 AND user_id=$2",
            code.upper(), user_id
        )
        return row is not None
