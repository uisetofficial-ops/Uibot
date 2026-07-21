import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiosqlite
import database
from datetime import datetime, timezone

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

MONTH_CHOICES = [
    app_commands.Choice(name="January",   value="1"),
    app_commands.Choice(name="February",  value="2"),
    app_commands.Choice(name="March",     value="3"),
    app_commands.Choice(name="April",     value="4"),
    app_commands.Choice(name="May",       value="5"),
    app_commands.Choice(name="June",      value="6"),
    app_commands.Choice(name="July",      value="7"),
    app_commands.Choice(name="August",    value="8"),
    app_commands.Choice(name="September", value="9"),
    app_commands.Choice(name="October",   value="10"),
    app_commands.Choice(name="November",  value="11"),
    app_commands.Choice(name="December",  value="12"),
]

MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]


async def ensure_birthday_table():
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS birthdays (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                month INTEGER NOT NULL,
                day INTEGER NOT NULL,
                year INTEGER,
                announced INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
        """)
        await db.commit()


class Birthdays(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        await ensure_birthday_table()
        self.birthday_check.start()

    def cog_unload(self):
        self.birthday_check.cancel()

    @tasks.loop(minutes=30)
    async def birthday_check(self):
        now = datetime.now(timezone.utc)
        today_month = now.month
        today_day = now.day

        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT user_id, guild_id, year, announced FROM birthdays WHERE month=? AND day=?",
                (today_month, today_day)
            ) as cursor:
                rows = await cursor.fetchall()

        for user_id, guild_id, year, announced in rows:
            if announced:
                continue

            channel_id = await database.get_setting(guild_id, "birthday_channel")
            if not channel_id:
                continue

            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            channel = guild.get_channel(int(channel_id))
            member = guild.get_member(user_id)
            if not channel or not member:
                continue

            age_text = ""
            if year:
                age = now.year - year
                age_text = f" They're turning **{age}** today!"

            embed = discord.Embed(
                title="🎂 Happy Birthday!",
                description=(
                    f"🎉 Everyone wish {member.mention} a happy birthday!{age_text}\n\n"
                    f"🥳 Hope your day is amazing!"
                ),
                color=discord.Color.from_rgb(255, 105, 180)
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"🎈 {MONTH_NAMES[today_month]} {today_day}")

            await channel.send(content=f"@everyone", embed=embed)

            # Mark as announced so it doesn't repeat today
            async with aiosqlite.connect(database.DB_PATH) as db:
                await db.execute(
                    "UPDATE birthdays SET announced=1 WHERE user_id=? AND guild_id=?",
                    (user_id, guild_id)
                )
                await db.commit()

    @tasks.loop(hours=24)
    async def reset_announced(self):
        """Reset the announced flag daily so next year works."""
        now = datetime.now(timezone.utc)
        # Reset at midnight UTC — only reset days that aren't today
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE birthdays SET announced=0 WHERE NOT (month=? AND day=?)",
                (now.month, now.day)
            )
            await db.commit()

    @birthday_check.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # ── Commands ──────────────────────────────────────────────────

    @app_commands.command(name="rememberbirthday", description="Save your birthday so the server can celebrate!")
    @app_commands.describe(
        month="Your birth month",
        day="Your birth day (1–31)",
        year="Your birth year (optional)"
    )
    @app_commands.choices(month=MONTH_CHOICES)
    async def remember_birthday(
        self,
        interaction: discord.Interaction,
        month: str,
        day: int,
        year: int = None
    ):
        month_int = int(month)

        # Validate day
        if day < 1 or day > 31:
            await interaction.response.send_message("❌ Day must be between 1 and 31.", ephemeral=True)
            return

        # Validate year if given
        current_year = datetime.now(timezone.utc).year
        if year and (year < 1900 or year > current_year):
            await interaction.response.send_message(f"❌ Year must be between 1900 and {current_year}.", ephemeral=True)
            return

        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                """INSERT OR REPLACE INTO birthdays (user_id, guild_id, month, day, year, announced)
                   VALUES (?, ?, ?, ?, ?, 0)""",
                (interaction.user.id, interaction.guild.id, month_int, day, year)
            )
            await db.commit()

        date_str = f"{MONTH_NAMES[month_int]} {day}"
        if year:
            date_str += f", {year}"

        embed = discord.Embed(
            title="🎂 Birthday Saved!",
            description=f"I'll remember your birthday: **{date_str}** 🎉",
            color=discord.Color.from_rgb(255, 105, 180)
        )
        embed.set_footer(text="The server will celebrate when your day comes!")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="birthday", description="Check someone's birthday")
    @app_commands.describe(user="User to look up (defaults to you)")
    async def birthday(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT month, day, year FROM birthdays WHERE user_id=? AND guild_id=?",
                (target.id, interaction.guild.id)
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            await interaction.response.send_message(
                f"❌ {target.display_name} hasn't saved their birthday yet.",
                ephemeral=True
            )
            return

        month, day, year = row
        date_str = f"{MONTH_NAMES[month]} {day}"
        if year:
            date_str += f", {year}"

        embed = discord.Embed(
            title=f"🎂 {target.display_name}'s Birthday",
            description=f"**{date_str}**",
            color=discord.Color.from_rgb(255, 105, 180)
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="upcoming-birthdays", description="See upcoming birthdays in the server")
    async def upcoming_birthdays(self, interaction: discord.Interaction):
        now = datetime.now(timezone.utc)
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT user_id, month, day FROM birthdays WHERE guild_id=? ORDER BY month, day",
                (interaction.guild.id,)
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            await interaction.response.send_message("No birthdays saved yet!", ephemeral=True)
            return

        # Sort so upcoming ones come first
        def sort_key(r):
            m, d = r[1], r[2]
            if (m, d) >= (now.month, now.day):
                return (0, m, d)
            return (1, m, d)

        rows.sort(key=sort_key)

        embed = discord.Embed(title="🎂 Upcoming Birthdays", color=discord.Color.from_rgb(255, 105, 180))
        lines = []
        for user_id, month, day in rows[:15]:
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"Unknown ({user_id})"
            lines.append(f"**{name}** — {MONTH_NAMES[month]} {day}")

        embed.description = "\n".join(lines) if lines else "None found."
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setup-birthdays", description="Set the channel where birthday announcements are posted")
    @app_commands.describe(channel="Channel for birthday messages")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_birthdays(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await database.set_setting(interaction.guild.id, "birthday_channel", str(channel.id))
        embed = discord.Embed(
            title="✅ Birthday Channel Set",
            description=f"Birthday announcements will be posted in {channel.mention} 🎂",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="forgetbirthday", description="Remove your saved birthday")
    async def forget_birthday(self, interaction: discord.Interaction):
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "DELETE FROM birthdays WHERE user_id=? AND guild_id=?",
                (interaction.user.id, interaction.guild.id)
            )
            await db.commit()
        await interaction.response.send_message("✅ Your birthday has been removed.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Birthdays(bot))
