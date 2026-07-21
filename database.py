import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "bot.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS settings (
                guild_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                PRIMARY KEY (guild_id, key)
            );

            CREATE TABLE IF NOT EXISTS coins (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                amount INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            );

            CREATE TABLE IF NOT EXISTS weekly_claims (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                last_claim TEXT,
                PRIMARY KEY (user_id, guild_id)
            );

            CREATE TABLE IF NOT EXISTS shop_roles (
                role_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                price INTEGER NOT NULL,
                PRIMARY KEY (role_id, guild_id)
            );

            CREATE TABLE IF NOT EXISTS levels (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                last_xp_time TEXT,
                PRIMARY KEY (user_id, guild_id)
            );

            CREATE TABLE IF NOT EXISTS tickets (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                status TEXT DEFAULT 'open'
            );

            CREATE TABLE IF NOT EXISTS yt_alerts (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                last_video_id TEXT
            );
        """)
        await db.commit()

async def get_setting(guild_id: int, key: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT value FROM settings WHERE guild_id=? AND key=?",
            (guild_id, key)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_setting(guild_id: int, key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (guild_id, key, value) VALUES (?,?,?)",
            (guild_id, key, value)
        )
        await db.commit()

async def get_coins(user_id: int, guild_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT amount FROM coins WHERE user_id=? AND guild_id=?",
            (user_id, guild_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def add_coins(user_id: int, guild_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO coins (user_id, guild_id, amount) VALUES (?,?,?)
               ON CONFLICT(user_id, guild_id) DO UPDATE SET amount = amount + ?""",
            (user_id, guild_id, amount, amount)
        )
        await db.commit()

async def set_coins(user_id: int, guild_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO coins (user_id, guild_id, amount) VALUES (?,?,?)",
            (user_id, guild_id, amount)
        )
        await db.commit()

async def get_xp_data(user_id: int, guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT xp, level, last_xp_time FROM levels WHERE user_id=? AND guild_id=?",
            (user_id, guild_id)
        ) as cursor:
            row = await cursor.fetchone()
            return {"xp": row[0], "level": row[1], "last_xp_time": row[2]} if row else {"xp": 0, "level": 0, "last_xp_time": None}

async def update_xp(user_id: int, guild_id: int, xp: int, level: int, last_xp_time: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO levels (user_id, guild_id, xp, level, last_xp_time) VALUES (?,?,?,?,?)",
            (user_id, guild_id, xp, level, last_xp_time)
        )
        await db.commit()

async def get_leaderboard(guild_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, xp, level FROM levels WHERE guild_id=? ORDER BY xp DESC LIMIT ?",
            (guild_id, limit)
        ) as cursor:
            return await cursor.fetchall()

async def get_rank(user_id: int, guild_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*)+1 FROM levels WHERE guild_id=? AND xp > (SELECT COALESCE(xp,0) FROM levels WHERE user_id=? AND guild_id=?)",
            (guild_id, user_id, guild_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 1
