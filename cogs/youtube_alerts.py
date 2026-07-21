import discord
from discord.ext import commands
from discord import app_commands
import database


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setup-welcome", description="Set up the welcome message for new members")
    @app_commands.describe(
        channel="Channel to send welcome messages in",
        message="Welcome message. Use {user}, {server}, {member_count} as placeholders"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_welcome(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str
    ):
        await database.set_setting(interaction.guild.id, "welcome_channel", str(channel.id))
        await database.set_setting(interaction.guild.id, "welcome_message", message)

        preview = message.replace("{user}", interaction.user.mention) \
                         .replace("{server}", interaction.guild.name) \
                         .replace("{member_count}", str(interaction.guild.member_count))

        embed = discord.Embed(
            title="✅ Welcome Message Set",
            color=discord.Color.green()
        )
        embed.add_field(name="Channel", value=channel.mention, inline=False)
        embed.add_field(name="Message", value=message, inline=False)
        embed.add_field(name="Preview", value=preview, inline=False)
        embed.set_footer(text="Variables: {user}, {server}, {member_count}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="welcome-disable", description="Disable welcome messages")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_disable(self, interaction: discord.Interaction):
        await database.set_setting(interaction.guild.id, "welcome_channel", "")
        await interaction.response.send_message("✅ Welcome messages disabled.", ephemeral=True)

    @app_commands.command(name="welcome-test", description="Preview the welcome message as if you just joined")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_test(self, interaction: discord.Interaction):
        await self._send_welcome(interaction.guild, interaction.user)
        await interaction.response.send_message("✅ Test welcome message sent!", ephemeral=True)

    async def _send_welcome(self, guild: discord.Guild, member: discord.Member):
        channel_id = await database.get_setting(guild.id, "welcome_channel")
        message_template = await database.get_setting(guild.id, "welcome_message")
        if not channel_id or not message_template:
            return
        channel = guild.get_channel(int(channel_id))
        if not channel:
            return
        message = message_template.replace("{user}", member.mention) \
                                  .replace("{server}", guild.name) \
                                  .replace("{member_count}", str(guild.member_count))

        embed = discord.Embed(
            description=message,
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Member #{guild.member_count}")
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._send_welcome(member.guild, member)

    @setup_welcome.error
    async def setup_welcome_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You need **Manage Server** permission.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
