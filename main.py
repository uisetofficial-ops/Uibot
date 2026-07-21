import discord
from discord.ext import commands
import os
import asyncio
import database

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True

bot = commands.Bot(command_prefix="u!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ {bot.user} is now online!")
    print(f"   Serving {len(bot.guilds)} guild(s)")
    try:
        synced = await bot.tree.sync()
        print(f"   Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"   Failed to sync commands: {e}")

async def main():
    await database.init_db()

    cogs = [
        "cogs.youtube_alerts",
        "cogs.coins",
        "cogs.tickets",
        "cogs.leveling",
        "cogs.welcome",
        "cogs.birthdays",
        "cogs.logs",
        "cogs.moderation",
    ]

    for cog in cogs:
        try:
            await bot.load_extension(cog)
            print(f"   ✓ Loaded {cog}")
        except Exception as e:
            print(f"   ✗ Failed to load {cog}: {e}")

    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("ERROR: DISCORD_TOKEN environment variable not set.")
        return

    await bot.start(token)

asyncio.run(main())
