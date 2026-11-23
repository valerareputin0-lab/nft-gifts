import asyncpg
import time
from config import DATABASE_URL

_pool = None

async def init_db():
    global _pool
    _pool = await asyncpg.create_pool(
        DATABASE_URL, min_size=1, max_size=5, statement_cache_size=0
    )
    async with _pool.acquire() as c:
        await c.execute("CREATE SEQUENCE IF NOT EXISTS user_game_id_seq START 1001")
        await c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                nick TEXT,
                game_id BIGINT,
                registered_at BIGINT,
                balance BIGINT DEFAULT 1000,
                btc DOUBLE PRECISION DEFAULT 0,
                bank_wallet BIGINT DEFAULT 0,
                last_passive BIGINT DEFAULT 0,
                last_bonus BIGINT DEFAULT 0,
                last_active BIGINT DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                ban_until BIGINT DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                admin_perms TEXT DEFAULT '',
                businesses TEXT DEFAULT '',
                business_last_collect BIGINT DEFAULT 0,
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
        # Миграции
        await c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS nick TEXT")
        await c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS game_id BIGINT")
        await c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS registered_at BIGINT")
        await c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active BIGINT DEFAULT 0")
        await c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned INTEGER DEFAULT 0")
        await c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS ban_until BIGINT DEFAULT 0")
        await c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin INTEGER DEFAULT 0")
        await c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_perms TEXT DEFAULT ''")
        await c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS business_last_collect BIGINT DEFAULT 0")
        await c.execute("UPDATE users SET game_id = nextval('user_game_id_seq') WHERE game_id IS NULL")
        await c.execute("UPDATE users SET registered_at = $1 WHERE registered_at IS NULL", int(time.time()))
        await c.execute("""
            CREATE TABLE IF NOT EXISTS promos (
                code TEXT PRIMARY KEY, amount BIGINT,
                limit_total INTEGER, used INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1
            )
        """)
        await c.execute("ALTER TABLE promos ADD COLUMN IF NOT EXISTS active INTEGER DEFAULT 1")
        await c.execute("""
            CREATE TABLE IF NOT EXISTS promo_uses (
                code TEXT, user_id BIGINT,
                PRIMARY KEY (code, user_id)
            )
        """)

async def get_user(user_id: int, username: str = None):
    async with _pool.acquire() as c:
        row = await c.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
        if row is None:
            now = int(time.time())
            await c.execute(
                "INSERT INTO users (user_id, username, game_id, registered_at, last_active) "
                "VALUES ($1, $2, nextval('user_game_id_seq'), $3, $3)",
                user_id, username or "player", now
            )
            row = await c.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
        return dict(row)

async def get_user_by_id(user_id: int):
    async with _pool.acquire() as c:
        row = await c.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
        return dict(row) if row else None

async def get_user_by_game_id(game_id: int):
    async with _pool.acquire() as c:
        row = await c.fetchrow("SELECT * FROM users WHERE game_id=$1", game_id)
        return dict(row) if row else None

async def get_user_rank(user_id: int) -> int:
    async with _pool.acquire() as c:
        u = await c.fetchrow("SELECT balance, game_id FROM users WHERE user_id=$1", user_id)
        if not u: return 0
        cnt = await c.fetchrow(
            "SELECT COUNT(*) FROM users WHERE balance > $1 OR (balance = $1 AND game_id < $2)",
            u["balance"], u["game_id"])
        return cnt[0] + 1

async def update(user_id: int, **kwargs):
    if not kwargs: return
    async with _pool.acquire() as c:
        fields = list(kwargs.keys())
        sets = ", ".join(f"{k}=${i+2}" for i, k in enumerate(fields))
        vals = [user_id] + [kwargs[k] for k in fields]
        await c.execute(f"UPDATE users SET {sets} WHERE user_id=$1", *vals)

async def add_balance(user_id: int, amount: int):
    async with _pool.acquire() as c:
        await c.execute("UPDATE users SET balance=balance+$1 WHERE user_id=$2", amount, user_id)

async def touch_active(user_id: int):
    async with _pool.acquire() as c:
        await c.execute("UPDATE users SET last_active=$1 WHERE user_id=$2", int(time.time()), user_id)

async def get_top(limit: int = 10):
    async with _pool.acquire() as c:
        rows = await c.fetch(
            "SELECT username, nick, balance FROM users ORDER BY balance DESC LIMIT $1", limit)
        return [dict(r) for r in rows]

async def is_nick_taken(nick: str, exclude_user_id: int = None) -> bool:
    async with _pool.acquire() as c:
        if exclude_user_id:
            row = await c.fetchrow(
                "SELECT 1 FROM users WHERE LOWER(nick)=LOWER($1) AND user_id!=$2",
                nick, exclude_user_id)
        else:
            row = await c.fetchrow("SELECT 1 FROM users WHERE LOWER(nick)=LOWER($1)", nick)
        return row is not None

async def set_nick(user_id: int, nick: str):
    async with _pool.acquire() as c:
        await c.execute("UPDATE users SET nick=$1 WHERE user_id=$2", nick, user_id)

async def count_all() -> int:
    async with _pool.acquire() as c:
        row = await c.fetchrow("SELECT COUNT(*) FROM users")
        return row[0]

async def count_banned() -> int:
    async with _pool.acquire() as c:
        now = int(time.time())
        row = await c.fetchrow(
            "SELECT COUNT(*) FROM users WHERE is_banned=1 AND (ban_until=0 OR ban_until > $1)",
            now)
        return row[0]

async def get_online(seconds: int = 300):
    async with _pool.acquire() as c:
        cutoff = int(time.time()) - seconds
        rows = await c.fetch(
            "SELECT game_id, nick, user_id FROM users "
            "WHERE last_active >= $1 AND is_banned=0 ORDER BY last_active DESC",
            cutoff)
        return [dict(r) for r in rows]

async def get_all_users():
    async with _pool.acquire() as c:
        rows = await c.fetch("SELECT * FROM users")
        return [dict(r) for r in rows]

async def reset_user(user_id: int):
    async with _pool.acquire() as c:
        await c.execute("""
            UPDATE users SET
                balance=1000, btc=0, bank_wallet=0,
                businesses='', business_last_collect=0,
                farms='', houses='', garage='', garage_bought=0,
                wardrobe='', clothes_worn='',
                deposit_amount=0, deposit_end=0, deposit_rate=0,
                wins=0, losses=0, last_bonus=0,
                is_admin=0, admin_perms=''
            WHERE user_id=$1
        """, user_id)

async def reset_all():
    async with _pool.acquire() as c:
        await c.execute("""
            UPDATE users SET
                balance=1000, btc=0, bank_wallet=0,
                businesses='', business_last_collect=0,
                farms='', houses='', garage='', garage_bought=0,
                wardrobe='', clothes_worn='',
                deposit_amount=0, deposit_end=0, deposit_rate=0,
                wins=0, losses=0, last_bonus=0
        """)

async def reset_full(user_id: int):
    """Полное обнуление (для пермабана 999 дней)"""
    async with _pool.acquire() as c:
        await c.execute("""
            UPDATE users SET
                balance=1000, btc=0, bank_wallet=0,
                businesses='', business_last_collect=0,
                farms='', houses='', garage='', garage_bought=0,
                wardrobe='', clothes_worn='',
                deposit_amount=0, deposit_end=0, deposit_rate=0,
                wins=0, losses=0, last_bonus=0,
                nick=NULL, is_admin=0, admin_perms=''
            WHERE user_id=$1
        """, user_id)

async def create_promo(code: str, amount: int, limit_total: int):
    async with _pool.acquire() as c:
        await c.execute(
            "INSERT INTO promos (code, amount, limit_total, used, active) VALUES ($1,$2,$3,0,1) "
            "ON CONFLICT (code) DO UPDATE SET amount=$2, limit_total=$3, used=0, active=1",
            code.upper(), amount, limit_total)

async def get_promo(code: str):
    async with _pool.acquire() as c:
        row = await c.fetchrow("SELECT * FROM promos WHERE code=$1", code.upper())
        return dict(row) if row else None

async def deactivate_promo(code: str) -> bool:
    async with _pool.acquire() as c:
        result = await c.execute(
            "UPDATE promos SET active=0 WHERE code=$1 AND active=1", code.upper())
        return result.split()[-1] != "0"

async def use_promo(code: str, user_id: int):
    async with _pool.acquire() as c:
        await c.execute(
            "INSERT INTO promo_uses (code, user_id) VALUES ($1,$2) ON CONFLICT DO NOTHING",
            code.upper(), user_id)
        await c.execute("UPDATE promos SET used=used+1 WHERE code=$1", code.upper())

async def user_used_promo(code: str, user_id: int) -> bool:
    async with _pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT 1 FROM promo_uses WHERE code=$1 AND user_id=$2", code.upper(), user_id)
        return row is not None
