import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import feedparser
import re
import database

RSS_BASE = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
POLL_INTERVAL = 5  # minutes


async def resolve_channel_id(handle_or_id: str) -> str | None:
    """Resolve a YouTube @handle or channel ID to a channel ID."""
    # If user already gave a channel ID (starts with UC...)
    if handle_or_id.startswith("UC") and len(handle_or_id) >= 10:
        return handle_or_id

    # Otherwise treat it as a handle
    handle = handle_or_id.lstrip("@")
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
        self.check_youtube.start()

    def cog_unload(self):
        self.check_youtube.cancel()

    @tasks.loop(minutes=POLL_INTERVAL)
    async def check_youtube(self):
        await self.bot.wait_until_ready()

        for guild in self.bot.guilds:
            channel_id = await database.get_setting(guild.id, "yt_channel_id")
            alert_channel_id = await database.get_setting(guild.id, "yt_alert_channel")

            if not channel_id or not alert_channel_id:
                continue

            rss_url = RSS_BASE.format(channel_id)

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(rss_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        content = await resp.text()
                feed = feedparser.parse(content)
            except Exception as e:
                print(f"[YT] RSS fetch error: {e}")
                continue

            if not feed.entries:
                continue

            latest = feed.entries[0]
            latest_id = latest.get("yt_videoid", "")
            latest_url = latest.get("link", "")
            latest_title = latest.get("title", "New Video")
            channel_name = feed.feed.get("title", "The channel")

            last_video_id = await database.get_setting(guild.id, "yt_last_video_id")
            if last_video_id == latest_id:
                continue

            await database.set_setting(guild.id, "yt_last_video_id", latest_id)

            alert_channel = guild.get_channel(int(alert_channel_id))
            if not alert_channel:
                continue

            embed = discord.Embed(
                title=f"🎬 {latest_title}",
                url=latest_url,
                description=f"Hey **{guild.name}**! **{channel_name}** just uploaded a new video 👇",
                color=discord.Color.red()
            )
            embed.set_footer(text="YouTube Upload Alert")

            await alert_channel.send(
                content="@everyone 🔔 **New video just dropped!**",
                embed=embed
            )

    @check_youtube.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # ---------------------------------------------------------
    # ⭐ NEW: /youtube-add <channel link>
    # ---------------------------------------------------------
    @app_commands.command(
        name="youtube-add",
        description="Add a YouTube channel to track uploads from."
    )
    @app_commands.describe(link="Paste the YouTube channel link (@handle or /channel/ID)")
    async def youtube_add(self, interaction: discord.Interaction, link: str):

        # Extract handle or channel ID
        handle_or_id = self.extract_handle_or_id(link)
        if not handle_or_id:
            await interaction.response.send_message(
                "❌ Invalid YouTube link. Use:\n"
                "`https://youtube.com/@YourChannel`\n"
                "`https://youtube.com/channel/UCxxxxxx`",
                ephemeral=True
            )
            return

        # Resolve to channel ID
        channel_id = await resolve_channel_id(handle_or_id)
        if not channel_id:
            await interaction.response.send_message(
                "❌ Could not resolve that YouTube channel.",
                ephemeral=True
            )
            return

        await database.set_setting(interaction.guild.id, "yt_channel_id", channel_id)
        await database.set_setting(interaction.guild.id, "yt_last_video_id", "")

        await interaction.response.send_message(
            f"✅ Now tracking uploads from **{handle_or_id}** (Channel ID: `{channel_id}`)",
            ephemeral=True
        )

    def extract_handle_or_id(self, link: str):
        # @handle format
        match = re.search(r"youtube\.com/@([A-Za-z0-9_\-\.]+)", link)
        if match:
            return match.group(1)

        # /channel/ID format
        match = re.search(r"youtube\.com/channel/([A-Za-z0-9_\-]+)", link)
        if match:
            return match.group(1)

        return None

    # ---------------------------------------------------------
    # Existing setup command (kept)
    # ---------------------------------------------------------
    @app_commands.command(name="setup-yt-alerts", description="Set the channel to receive YouTube upload alerts")
    @app_commands.describe(channel="Channel where upload alerts will be posted")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_yt_alerts(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await database.set_setting(interaction.guild.id, "yt_alert_channel", str(channel.id))
        await interaction.response.send_message(
            f"✅ YouTube alerts will be posted in {channel.mention}.",
            ephemeral=True
        )

    @app_commands.command(name="disable-yt-alerts", description="Disable YouTube upload alerts")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def disable_yt_alerts(self, interaction: discord.Interaction):
        await database.set_setting(interaction.guild.id, "yt_alert_channel", "")
        await interaction.response.send_message("✅ YouTube upload alerts disabled.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(YouTubeAlerts(bot))
