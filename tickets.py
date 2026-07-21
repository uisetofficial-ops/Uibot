import discord
from discord.ext import commands
from discord import app_commands
import random
import io
from datetime import datetime, timezone
import database
from utils.rank_card import generate_rank_card, fetch_avatar

XP_MIN = 15
XP_MAX = 25
XP_COOLDOWN_SECONDS = 60  # Cooldown between XP gains


def xp_for_level(level: int) -> int:
    """XP needed to reach next level from current level."""
    return 5 * (level ** 2) + 50 * level + 100


def total_xp_for_level(level: int) -> int:
    """Total XP accumulated to reach a given level."""
    return sum(xp_for_level(i) for i in range(level))


class Leveling(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        user_id = message.author.id
        guild_id = message.guild.id
        data = await database.get_xp_data(user_id, guild_id)

        now = datetime.now(timezone.utc)

        # Cooldown check
        if data["last_xp_time"]:
            last = datetime.fromisoformat(data["last_xp_time"])
            elapsed = (now - last).total_seconds()
            if elapsed < XP_COOLDOWN_SECONDS:
                return

        # Grant XP
        gained = random.randint(XP_MIN, XP_MAX)
        xp = data["xp"] + gained
        level = data["level"]

        # Check level up
        leveled_up = False
        while xp >= xp_for_level(level):
            xp -= xp_for_level(level)
            level += 1
            leveled_up = True

        await database.update_xp(user_id, guild_id, xp, level, now.isoformat())

        if leveled_up:
            await self._announce_level_up(message, level)

    async def _announce_level_up(self, message: discord.Message, new_level: int):
        # Check for custom level-up channel
        channel_id = await database.get_setting(message.guild.id, "levelup_channel")
        channel = message.guild.get_channel(int(channel_id)) if channel_id else message.channel

        embed = discord.Embed(
            title="⬆️ Level Up!",
            description=f"🎉 {message.author.mention} just reached **Level {new_level}**!",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=message.author.display_avatar.url)

        # Check for level role rewards
        role_id = await database.get_setting(message.guild.id, f"level_role:{new_level}")
        if role_id:
            role = message.guild.get_role(int(role_id))
            if role:
                try:
                    await message.author.add_roles(role, reason=f"Reached level {new_level}")
                    embed.add_field(name="Role Reward", value=f"You earned the {role.mention} role!")
                except discord.Forbidden:
                    pass

        await channel.send(embed=embed)

    @app_commands.command(name="rank", description="View your rank card")
    @app_commands.describe(user="Check another user's rank (optional)")
    async def rank(self, interaction: discord.Interaction, user: discord.Member = None):
        await interaction.response.defer()
        target = user or interaction.user
        guild_id = interaction.guild.id

        data = await database.get_xp_data(target.id, guild_id)
        rank_pos = await database.get_rank(target.id, guild_id)

        level = data["level"]
        xp = data["xp"]
        xp_needed = xp_for_level(level)

        # Generate rank card
        try:
            avatar_img = await fetch_avatar(str(target.display_avatar.url), size=180)
            disc = target.discriminator if hasattr(target, "discriminator") else "0"
            card_bytes = generate_rank_card(
                avatar_img=avatar_img,
                username=target.display_name,
                discriminator=disc,
                level=level,
                current_xp=xp,
                xp_needed=xp_needed,
                rank=rank_pos,
            )
            file = discord.File(io.BytesIO(card_bytes), filename="rank_card.png")
            await interaction.followup.send(file=file)
        except Exception as e:
            # Fallback to embed if image generation fails
            embed = discord.Embed(
                title=f"📊 {target.display_name}'s Rank",
                color=discord.Color.blurple()
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            embed.add_field(name="Level", value=str(level), inline=True)
            embed.add_field(name="Rank", value=f"#{rank_pos}", inline=True)
            embed.add_field(name="XP", value=f"{xp:,} / {xp_needed:,}", inline=True)
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="leaderboard", description="View the XP leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        board = await database.get_leaderboard(interaction.guild.id, limit=10)

        embed = discord.Embed(
            title=f"🏆 {interaction.guild.name} Leaderboard",
            color=discord.Color.gold()
        )

        if not board:
            embed.description = "No one has earned XP yet. Start chatting!"
        else:
            medals = ["🥇", "🥈", "🥉"]
            lines = []
            for i, (user_id, xp, level) in enumerate(board):
                member = interaction.guild.get_member(user_id)
                name = member.display_name if member else f"Unknown ({user_id})"
                medal = medals[i] if i < 3 else f"`#{i+1}`"
                lines.append(f"{medal} **{name}** — Level {level} ({xp:,} XP)")
            embed.description = "\n".join(lines)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setup-levels", description="Configure the leveling system")
    @app_commands.describe(
        levelup_channel="Channel to announce level ups (leave empty to use same channel)"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_levels(
        self,
        interaction: discord.Interaction,
        levelup_channel: discord.TextChannel = None
    ):
        if levelup_channel:
            await database.set_setting(interaction.guild.id, "levelup_channel", str(levelup_channel.id))
            await interaction.response.send_message(
                f"✅ Level up announcements will go to {levelup_channel.mention}.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "✅ Level up announcements will go in the same channel as the message.", ephemeral=True
            )

    @app_commands.command(name="set-level-role", description="Assign a role reward for reaching a level")
    @app_commands.describe(level="Level that triggers the reward", role="Role to give")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def set_level_role(self, interaction: discord.Interaction, level: int, role: discord.Role):
        await database.set_setting(interaction.guild.id, f"level_role:{level}", str(role.id))
        await interaction.response.send_message(
            f"✅ Users who reach **Level {level}** will receive the **{role.name}** role.", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
