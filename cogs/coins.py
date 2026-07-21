import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import feedparser
import os
import re
import database

YOUTUBE_HANDLE = os.environ.get("YOUTUBE_CHANNEL_HANDLE", "@Uiset")
RSS_BASE = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
POLL_INTERVAL = 5  # minutes


async def resolve_channel_id(handle: str) -> str | None:
    """Resolve a YouTube @handle to a channel ID by fetching the channel page."""
    handle = handle.lstrip("@")
    url = f"https://www.youtube.com/@{handle}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; bot)"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                html = await resp.text()
                match = re.search(r'"channelId":"(UC[\w-]{22})"', html)
                if match:
                    return match.group(1)
    except Exception as e:
        print(f"[YT] Failed to resolve handle {handle}: {e}")
    return None


class YouTubeAlerts(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.channel_id: str | None = None
        self.check_youtube.start()

    def cog_unload(self):
        self.check_youtube.cancel()

    @tasks.loop(minutes=POLL_INTERVAL)
    async def check_youtube(self):
        if not self.channel_id:
            self.channel_id = await resolve_channel_id(YOUTUBE_HANDLE)
            if not self.channel_id:
                print("[YT] Could not resolve YouTube channel ID. Retrying next cycle.")
                return

        rss_url = RSS_BASE.format(self.channel_id)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(rss_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    content = await resp.text()
            feed = feedparser.parse(content)
        except Exception as e:
            print(f"[YT] RSS fetch error: {e}")
            return

        if not feed.entries:
            return

        latest = feed.entries[0]
        latest_id = latest.get("yt_videoid", "")
        latest_url = latest.get("link", "")
        latest_title = latest.get("title", "New Video")
        channel_name = feed.feed.get("title", "The channel")

        for guild in self.bot.guilds:
            db_channel_id = await database.get_setting(guild.id, "yt_alert_channel")
            last_video_id = await database.get_setting(guild.id, "yt_last_video_id")

            if not db_channel_id:
                continue
            if last_video_id == latest_id:
                continue

            await database.set_setting(guild.id, "yt_last_video_id", latest_id)

            alert_channel = guild.get_channel(int(db_channel_id))
            if not alert_channel:
                continue

            embed = discord.Embed(
                title=f"🎬 {latest_title}",
                url=latest_url,
                description=f"Hey **{guild.name}**! **{channel_name}** has uploaded a new video — watch it here! 👇",
                color=discord.Color.red()
            )
            embed.set_footer(text="YouTube Upload Alert • Subscribe so you never miss one!")
            await alert_channel.send(
                content=f"@everyone 🔔 **New video just dropped!**",
                embed=embed
            )

    @check_youtube.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="setup-yt-alerts", description="Set the channel to receive YouTube upload alerts")
    @app_commands.describe(channel="Channel where upload alerts will be posted")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_yt_alerts(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await database.set_setting(interaction.guild.id, "yt_alert_channel", str(channel.id))
        await database.set_setting(interaction.guild.id, "yt_last_video_id", "")  # reset to allow first alert

        embed = discord.Embed(
            title="✅ YouTube Alerts Configured",
            description=f"Upload alerts for **{YOUTUBE_HANDLE}** will be posted in {channel.mention}.",
            color=discord.Color.green()
        )
        embed.add_field(name="Check Interval", value=f"Every {POLL_INTERVAL} minutes")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="disable-yt-alerts", description="Disable YouTube upload alerts")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def disable_yt_alerts(self, interaction: discord.Interaction):
        await database.set_setting(interaction.guild.id, "yt_alert_channel", "")
        await interaction.response.send_message("✅ YouTube upload alerts disabled.", ephemeral=True)

    @setup_yt_alerts.error
    async def setup_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You need **Manage Server** permission.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(YouTubeAlerts(bot))
