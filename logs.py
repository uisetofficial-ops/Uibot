import discord
from discord.ext import commands
from discord import app_commands
import database

COLOR_MAP = {
    "red":    discord.Color.red(),
    "blue":   discord.Color.blue(),
    "green":  discord.Color.green(),
    "purple": discord.Color.purple(),
    "yellow": discord.Color.yellow(),
    "orange": discord.Color.orange(),
    "pink":   discord.Color.from_rgb(255, 105, 180),
    "white":  discord.Color.from_rgb(255, 255, 255),
    "black":  discord.Color.from_rgb(35, 35, 35),
    "blurple": discord.Color.blurple(),
}


class TicketButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="📩 Open a Ticket",
            style=discord.ButtonStyle.primary,
            custom_id="ticket:create"
        )

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user

        # Check if user already has an open ticket
        existing = discord.utils.get(
            guild.text_channels,
            name=f"ticket-{user.name.lower().replace(' ', '-')}"
        )
        if existing:
            await interaction.response.send_message(
                f"❌ You already have an open ticket: {existing.mention}",
                ephemeral=True
            )
            return

        # Get support role if configured
        support_role_id = await database.get_setting(guild.id, "ticket_support_role")
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
        }
        if support_role_id:
            role = guild.get_role(int(support_role_id))
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # Get ticket category if configured
        category_id = await database.get_setting(guild.id, "ticket_category")
        category = None
        if category_id:
            category = guild.get_channel(int(category_id))

        channel = await guild.create_text_channel(
            name=f"ticket-{user.name.lower().replace(' ', '-')}",
            overwrites=overwrites,
            category=category,
            topic=f"Support ticket opened by {user} (ID: {user.id})"
        )

        await database.set_setting(guild.id, f"ticket:{channel.id}", str(user.id))

        # Send welcome message in ticket
        saved_color = await database.get_setting(guild.id, "ticket_color")
        ticket_color = COLOR_MAP.get(saved_color, discord.Color.blurple())

        embed = discord.Embed(
            title="🎫 Support Ticket",
            description=(
                f"Hello {user.mention}! A staff member will assist you shortly.\n\n"
                "Please describe your issue in detail below.\n\n"
                "To close this ticket, click the button below."
            ),
            color=ticket_color
        )
        embed.set_footer(text=f"Ticket opened by {user} • {guild.name}")

        close_view = discord.ui.View(timeout=None)
        close_view.add_item(CloseTicketButton())

        await channel.send(content=user.mention, embed=embed, view=close_view)
        await interaction.response.send_message(
            f"✅ Your ticket has been created: {channel.mention}",
            ephemeral=True
        )


class CloseTicketButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="🔒 Close Ticket",
            style=discord.ButtonStyle.danger,
            custom_id="ticket:close"
        )

    async def callback(self, interaction: discord.Interaction):
        channel = interaction.channel
        user = interaction.user

        # Only staff or ticket owner can close
        support_role_id = await database.get_setting(interaction.guild.id, "ticket_support_role")
        ticket_owner_id = await database.get_setting(interaction.guild.id, f"ticket:{channel.id}")

        is_owner = ticket_owner_id and str(user.id) == ticket_owner_id
        is_staff = user.guild_permissions.manage_channels
        if support_role_id:
            role = interaction.guild.get_role(int(support_role_id))
            is_staff = is_staff or (role in user.roles)

        if not (is_owner or is_staff):
            await interaction.response.send_message("❌ Only staff or the ticket owner can close this ticket.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🔒 Ticket Closing",
            description=f"Closed by {user.mention}. This channel will be deleted in 5 seconds.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)

        import asyncio
        await asyncio.sleep(5)
        await channel.delete(reason=f"Ticket closed by {user}")


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketButton())


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(TicketPanelView())  # Persist view across restarts

    @app_commands.command(name="ticket-panel", description="Send the ticket panel with a button")
    @app_commands.describe(
        channel="Channel to post the panel in (defaults to current channel)",
        title="Panel title",
        description="Panel description",
        color="Embed color"
    )
    @app_commands.choices(color=[
        app_commands.Choice(name="Red",     value="red"),
        app_commands.Choice(name="Blue",    value="blue"),
        app_commands.Choice(name="Green",   value="green"),
        app_commands.Choice(name="Purple",  value="purple"),
        app_commands.Choice(name="Yellow",  value="yellow"),
        app_commands.Choice(name="Orange",  value="orange"),
        app_commands.Choice(name="Pink",    value="pink"),
        app_commands.Choice(name="White",   value="white"),
        app_commands.Choice(name="Black",   value="black"),
        app_commands.Choice(name="Blurple", value="blurple"),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel = None,
        title: str = "🎫 Support Tickets",
        description: str = "Need help? Click the button below to open a private support ticket. Our team will assist you shortly.",
        color: str = "blurple"
    ):
        target = channel or interaction.channel
        chosen_color = COLOR_MAP.get(color, discord.Color.blurple())

        # Save panel color so ticket embeds inside channels match
        await database.set_setting(interaction.guild.id, "ticket_color", color)

        embed = discord.Embed(
            title=title,
            description=description,
            color=chosen_color
        )
        embed.set_footer(text=f"{interaction.guild.name} Support System")

        await target.send(embed=embed, view=TicketPanelView())
        await interaction.response.send_message(
            f"✅ Ticket panel posted in {target.mention}!",
            ephemeral=True
        )

    @app_commands.command(name="ticket-setup", description="Configure the ticket system")
    @app_commands.describe(
        support_role="Role that can see and manage tickets",
        category="Category to create tickets in",
        color="Color for ticket embeds"
    )
    @app_commands.choices(color=[
        app_commands.Choice(name="Red",     value="red"),
        app_commands.Choice(name="Blue",    value="blue"),
        app_commands.Choice(name="Green",   value="green"),
        app_commands.Choice(name="Purple",  value="purple"),
        app_commands.Choice(name="Yellow",  value="yellow"),
        app_commands.Choice(name="Orange",  value="orange"),
        app_commands.Choice(name="Pink",    value="pink"),
        app_commands.Choice(name="White",   value="white"),
        app_commands.Choice(name="Black",   value="black"),
        app_commands.Choice(name="Blurple", value="blurple"),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        support_role: discord.Role = None,
        category: discord.CategoryChannel = None,
        color: str = None
    ):
        if support_role:
            await database.set_setting(interaction.guild.id, "ticket_support_role", str(support_role.id))
        if category:
            await database.set_setting(interaction.guild.id, "ticket_category", str(category.id))
        if color:
            await database.set_setting(interaction.guild.id, "ticket_color", color)

        embed = discord.Embed(title="✅ Ticket System Configured", color=discord.Color.green())
        if support_role:
            embed.add_field(name="Support Role", value=support_role.mention)
        if category:
            embed.add_field(name="Category", value=category.name)
        if color:
            embed.add_field(name="Ticket Color", value=color.capitalize())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ticket_panel.error
    async def panel_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You need **Manage Server** permission.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
