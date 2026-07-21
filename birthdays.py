import discord
from discord.ext import commands
from discord import app_commands
import database
from datetime import timezone


def truncate(text: str, limit: int = 1024) -> str:
    return text if len(text) <= limit else text[:limit - 3] + "..."


class Logs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        channel_id = await database.get_setting(guild.id, "log_channel")
        if not channel_id:
            return None
        return guild.get_channel(int(channel_id))

    async def send_log(self, guild: discord.Guild, embed: discord.Embed):
        channel = await self.get_log_channel(guild)
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    # ── Setup ─────────────────────────────────────────────────────

    @app_commands.command(name="setup-logs", description="Set the channel where server logs are sent")
    @app_commands.describe(channel="Channel to send logs to")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_logs(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await database.set_setting(interaction.guild.id, "log_channel", str(channel.id))
        embed = discord.Embed(
            title="✅ Log Channel Set",
            description=f"Server logs will be sent to {channel.mention}.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Send a confirmation log to the channel
        confirm = discord.Embed(
            title="📋 Logging Started",
            description=f"This channel is now receiving server logs. Set up by {interaction.user.mention}.",
            color=discord.Color.blurple()
        )
        await channel.send(embed=confirm)

    @app_commands.command(name="disable-logs", description="Disable server logging")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def disable_logs(self, interaction: discord.Interaction):
        await database.set_setting(interaction.guild.id, "log_channel", "")
        await interaction.response.send_message("✅ Logging disabled.", ephemeral=True)

    # ── Message Events ────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        # Only log if the log channel is set and message isn't IN the log channel
        channel_id = await database.get_setting(message.guild.id, "log_channel")
        if not channel_id or str(message.channel.id) == channel_id:
            return

        embed = discord.Embed(
            description=truncate(message.content or "*[no text content]*"),
            color=discord.Color.from_rgb(100, 200, 100),
            timestamp=message.created_at
        )
        embed.set_author(name=f"{message.author} — Message Sent", icon_url=message.author.display_avatar.url)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(name="User ID", value=str(message.author.id), inline=True)
        if message.attachments:
            embed.add_field(name="Attachments", value="\n".join(a.url for a in message.attachments), inline=False)
        embed.set_footer(text=f"Message ID: {message.id}")
        await self.send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        embed = discord.Embed(
            description=truncate(message.content or "*[no text content]*"),
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=f"{message.author} — Message Deleted", icon_url=message.author.display_avatar.url)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(name="User ID", value=str(message.author.id), inline=True)
        if message.attachments:
            embed.add_field(name="Attachments (deleted)", value="\n".join(a.url for a in message.attachments), inline=False)
        embed.set_footer(text=f"Message ID: {message.id}")
        await self.send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot:
            return
        if before.content == after.content:
            return

        embed = discord.Embed(
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=f"{before.author} — Message Edited", icon_url=before.author.display_avatar.url)
        embed.add_field(name="Before", value=truncate(before.content or "*empty*"), inline=False)
        embed.add_field(name="After", value=truncate(after.content or "*empty*"), inline=False)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Jump to Message", value=f"[Click here]({after.jump_url})", inline=True)
        embed.set_footer(text=f"User ID: {before.author.id}")
        await self.send_log(before.guild, embed)

    # ── Member Events ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(
            description=f"{member.mention} **joined the server**",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=f"{member} — Member Joined", icon_url=member.display_avatar.url)
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        embed.add_field(name="Member Count", value=str(member.guild.member_count), inline=True)
        embed.set_footer(text=f"User ID: {member.id}")
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(
            description=f"{member.mention} **left the server**",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=f"{member} — Member Left", icon_url=member.display_avatar.url)
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        if roles:
            embed.add_field(name="Roles", value=" ".join(roles), inline=False)
        embed.set_footer(text=f"User ID: {member.id}")
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick != after.nick:
            embed = discord.Embed(
                color=discord.Color.blurple(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=f"{after} — Nickname Changed", icon_url=after.display_avatar.url)
            embed.add_field(name="Before", value=before.nick or "*none*", inline=True)
            embed.add_field(name="After", value=after.nick or "*none*", inline=True)
            embed.set_footer(text=f"User ID: {after.id}")
            await self.send_log(after.guild, embed)

        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if added or removed:
            embed = discord.Embed(
                color=discord.Color.blurple(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=f"{after} — Roles Updated", icon_url=after.display_avatar.url)
            if added:
                embed.add_field(name="Roles Added", value=" ".join(r.mention for r in added), inline=False)
            if removed:
                embed.add_field(name="Roles Removed", value=" ".join(r.mention for r in removed), inline=False)
            embed.set_footer(text=f"User ID: {after.id}")
            await self.send_log(after.guild, embed)

    # ── Moderation Events ─────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            description=f"{user.mention} was **banned**",
            color=discord.Color.dark_red(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=f"{user} — Member Banned", icon_url=user.display_avatar.url)
        embed.set_footer(text=f"User ID: {user.id}")
        await self.send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            description=f"{user.mention} was **unbanned**",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=f"{user} — Member Unbanned", icon_url=user.display_avatar.url)
        embed.set_footer(text=f"User ID: {user.id}")
        await self.send_log(guild, embed)

    # ── Channel Events ────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        embed = discord.Embed(
            description=f"Channel **#{channel.name}** was created",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name="Channel Created", icon_url=channel.guild.icon.url if channel.guild.icon else discord.Embed.Empty)
        embed.add_field(name="Type", value=str(channel.type).replace("_", " ").title(), inline=True)
        embed.set_footer(text=f"Channel ID: {channel.id}")
        await self.send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        embed = discord.Embed(
            description=f"Channel **#{channel.name}** was deleted",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name="Channel Deleted", icon_url=channel.guild.icon.url if channel.guild.icon else discord.Embed.Empty)
        embed.set_footer(text=f"Channel ID: {channel.id}")
        await self.send_log(channel.guild, embed)

    # ── Voice Events ──────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel == after.channel:
            return

        if after.channel and not before.channel:
            desc = f"{member.mention} joined **{after.channel.name}**"
            color = discord.Color.green()
        elif before.channel and not after.channel:
            desc = f"{member.mention} left **{before.channel.name}**"
            color = discord.Color.red()
        else:
            desc = f"{member.mention} moved from **{before.channel.name}** → **{after.channel.name}**"
            color = discord.Color.orange()

        embed = discord.Embed(description=desc, color=color, timestamp=discord.utils.utcnow())
        embed.set_author(name=f"{member} — Voice Activity", icon_url=member.display_avatar.url)
        embed.set_footer(text=f"User ID: {member.id}")
        await self.send_log(member.guild, embed)

    @setup_logs.error
    async def setup_logs_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You need **Manage Server** permission.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
