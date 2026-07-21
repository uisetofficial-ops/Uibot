import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from datetime import datetime, timedelta, timezone
import database

XP_PER_COIN = 10
WEEKLY_BASE = 500
WEEKLY_BONUS_MAX = 200

CHALLENGES = [
    "Send 20 messages in the server",
    "React to 10 messages",
    "Help someone in a support channel",
    "Share a meme or art",
    "Participate in a voice chat",
]

COLOR_ROLES_DEFAULT = []  # Admins add via /shop-add


def xp_for_level(level: int) -> int:
    return 5 * (level ** 2) + 50 * level + 100


class CoinsView(discord.ui.View):
    pass


class Coins(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─── Balance ─────────────────────────────────────────────

    @app_commands.command(name="coins", description="Check your Uisetcoins balance")
    @app_commands.describe(user="Check another user's balance (optional)")
    async def coins(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        amount = await database.get_coins(target.id, interaction.guild.id)

        embed = discord.Embed(
            title="🪙 Uisetcoins Balance",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name=target.display_name, value=f"**{amount:,}** Uisetcoins", inline=False)
        await interaction.response.send_message(embed=embed)

    # ─── Weekly Challenge ─────────────────────────────────────

    @app_commands.command(name="weekly", description="Claim your weekly Uisetcoins challenge reward")
    async def weekly(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        guild_id = interaction.guild.id

        last_claim_str = await database.get_setting(guild_id, f"weekly:{user_id}")
        now = datetime.now(timezone.utc)

        if last_claim_str:
            last_claim = datetime.fromisoformat(last_claim_str)
            next_claim = last_claim + timedelta(days=7)
            if now < next_claim:
                remaining = next_claim - now
                days = remaining.days
                hours, rem = divmod(remaining.seconds, 3600)
                minutes = rem // 60
                embed = discord.Embed(
                    title="⏳ Weekly Already Claimed",
                    description=f"Come back in **{days}d {hours}h {minutes}m** for your next weekly challenge!",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

        # Pick a random challenge
        challenge = random.choice(CHALLENGES)
        reward = WEEKLY_BASE + random.randint(0, WEEKLY_BONUS_MAX)

        await database.add_coins(user_id, guild_id, reward)
        await database.set_setting(guild_id, f"weekly:{user_id}", now.isoformat())

        embed = discord.Embed(
            title="🎯 Weekly Challenge Complete!",
            description=f"You completed: **{challenge}**\n\nYou earned **{reward:,} Uisetcoins**! 🪙",
            color=discord.Color.green()
        )
        new_balance = await database.get_coins(user_id, guild_id)
        embed.set_footer(text=f"New balance: {new_balance:,} Uisetcoins • Come back next week!")
        await interaction.response.send_message(embed=embed)

    # ─── Games ───────────────────────────────────────────────

    @app_commands.command(name="games", description="View available coin games")
    async def games(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎮 Uisetcoins Games",
            description="Bet your coins and win big — or lose it all!",
            color=discord.Color.blurple()
        )
        embed.add_field(name="🪙 /coinflip <bet>", value="50/50 chance to double your coins", inline=False)
        embed.add_field(name="🎰 /slots <bet>", value="Spin the slots — match 3 to win big!", inline=False)
        embed.add_field(name="🃏 /blackjack <bet>", value="Beat the dealer to 21!", inline=False)
        embed.set_footer(text="Minimum bet: 10 Uisetcoins")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="coinflip", description="Bet Uisetcoins on a coin flip")
    @app_commands.describe(bet="Amount to bet", choice="Heads or tails")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Heads", value="heads"),
        app_commands.Choice(name="Tails", value="tails"),
    ])
    async def coinflip(self, interaction: discord.Interaction, bet: int, choice: str):
        if bet < 10:
            await interaction.response.send_message("❌ Minimum bet is **10 Uisetcoins**.", ephemeral=True)
            return

        balance = await database.get_coins(interaction.user.id, interaction.guild.id)
        if balance < bet:
            await interaction.response.send_message(f"❌ You only have **{balance:,} Uisetcoins**.", ephemeral=True)
            return

        result = random.choice(["heads", "tails"])
        won = result == choice
        change = bet if won else -bet

        await database.add_coins(interaction.user.id, interaction.guild.id, change)
        new_balance = await database.get_coins(interaction.user.id, interaction.guild.id)

        coin_emoji = "🌕" if result == "heads" else "🌑"
        embed = discord.Embed(
            title=f"{coin_emoji} Coin Flip — {'You Won!' if won else 'You Lost!'}",
            color=discord.Color.green() if won else discord.Color.red()
        )
        embed.add_field(name="Result", value=result.capitalize(), inline=True)
        embed.add_field(name="Your Pick", value=choice.capitalize(), inline=True)
        embed.add_field(name="Change", value=f"{'+'if won else ''}{change:,} 🪙", inline=True)
        embed.set_footer(text=f"Balance: {new_balance:,} Uisetcoins")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="slots", description="Spin the slot machine")
    @app_commands.describe(bet="Amount to bet")
    async def slots(self, interaction: discord.Interaction, bet: int):
        if bet < 10:
            await interaction.response.send_message("❌ Minimum bet is **10 Uisetcoins**.", ephemeral=True)
            return

        balance = await database.get_coins(interaction.user.id, interaction.guild.id)
        if balance < bet:
            await interaction.response.send_message(f"❌ You only have **{balance:,} Uisetcoins**.", ephemeral=True)
            return

        SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "⭐", "💎"]
        WEIGHTS = [30, 25, 20, 15, 7, 3]

        reels = random.choices(SYMBOLS, weights=WEIGHTS, k=3)
        display = f"| {' | '.join(reels)} |"

        if reels[0] == reels[1] == reels[2]:
            symbol = reels[0]
            multipliers = {"💎": 10, "⭐": 6, "🍇": 4, "🍊": 3, "🍋": 2, "🍒": 2}
            mult = multipliers.get(symbol, 2)
            winnings = bet * mult
            await database.add_coins(interaction.user.id, interaction.guild.id, winnings - bet)
            result_text = f"🎉 **JACKPOT! {symbol}{symbol}{symbol}** — You won **{winnings:,} Uisetcoins** (×{mult})!"
            color = discord.Color.gold()
        elif reels[0] == reels[1] or reels[1] == reels[2]:
            winnings = int(bet * 0.5)
            await database.add_coins(interaction.user.id, interaction.guild.id, winnings - bet)
            result_text = f"😐 **Two of a kind!** — You got back **{winnings:,} Uisetcoins**."
            color = discord.Color.yellow()
        else:
            await database.add_coins(interaction.user.id, interaction.guild.id, -bet)
            result_text = f"😢 No match — You lost **{bet:,} Uisetcoins**."
            color = discord.Color.red()

        new_balance = await database.get_coins(interaction.user.id, interaction.guild.id)
        embed = discord.Embed(title="🎰 Slot Machine", description=f"```\n{display}\n```\n{result_text}", color=color)
        embed.set_footer(text=f"Balance: {new_balance:,} Uisetcoins")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="blackjack", description="Play blackjack against the dealer")
    @app_commands.describe(bet="Amount to bet")
    async def blackjack(self, interaction: discord.Interaction, bet: int):
        if bet < 10:
            await interaction.response.send_message("❌ Minimum bet is **10 Uisetcoins**.", ephemeral=True)
            return
        balance = await database.get_coins(interaction.user.id, interaction.guild.id)
        if balance < bet:
            await interaction.response.send_message(f"❌ You only have **{balance:,} Uisetcoins**.", ephemeral=True)
            return

        SUITS = ["♠", "♥", "♦", "♣"]
        RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        deck = [f"{r}{s}" for s in SUITS for r in RANKS]
        random.shuffle(deck)

        def card_value(card):
            r = card[:-1]
            if r in ["J", "Q", "K"]: return 10
            if r == "A": return 11
            return int(r)

        def hand_value(hand):
            val = sum(card_value(c) for c in hand)
            aces = sum(1 for c in hand if c[:-1] == "A")
            while val > 21 and aces:
                val -= 10
                aces -= 1
            return val

        def fmt_hand(hand, hide_second=False):
            if hide_second:
                return f"{hand[0]} 🂠"
            return " ".join(hand)

        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]

        async def show_state(result_text: str = "", final: bool = False):
            embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.blurple())
            embed.add_field(
                name=f"Your Hand ({hand_value(player)})",
                value=fmt_hand(player),
                inline=False
            )
            dealer_val = hand_value(dealer) if final else card_value(dealer[0])
            embed.add_field(
                name=f"Dealer's Hand ({dealer_val if final else '?'})",
                value=fmt_hand(dealer, hide_second=not final),
                inline=False
            )
            embed.add_field(name="Bet", value=f"{bet:,} 🪙", inline=True)
            if result_text:
                embed.add_field(name="Result", value=result_text, inline=False)
            return embed

        # Check natural blackjack
        if hand_value(player) == 21:
            winnings = int(bet * 1.5)
            await database.add_coins(interaction.user.id, interaction.guild.id, winnings)
            new_bal = await database.get_coins(interaction.user.id, interaction.guild.id)
            embed = await show_state(f"🎉 Blackjack! You won **{winnings:,} Uisetcoins**!\nBalance: {new_bal:,}", final=True)
            embed.color = discord.Color.gold()
            await interaction.response.send_message(embed=embed)
            return

        # Action buttons
        class BJView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.action = None

            @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
            async def hit(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                if btn_interaction.user != interaction.user:
                    await btn_interaction.response.send_message("Not your game!", ephemeral=True)
                    return
                player.append(deck.pop())
                pv = hand_value(player)
                if pv > 21:
                    await database.add_coins(interaction.user.id, interaction.guild.id, -bet)
                    new_bal = await database.get_coins(interaction.user.id, interaction.guild.id)
                    embed = await show_state(f"💥 Bust! You lose **{bet:,} Uisetcoins**.\nBalance: {new_bal:,}", final=True)
                    embed.color = discord.Color.red()
                    self.stop()
                    await btn_interaction.response.edit_message(embed=embed, view=None)
                elif pv == 21:
                    self.action = "stand"
                    await btn_interaction.response.edit_message(embed=await show_state(), view=self)
                    await self.stand_action(btn_interaction)
                else:
                    await btn_interaction.response.edit_message(embed=await show_state(), view=self)

            @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
            async def stand(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                if btn_interaction.user != interaction.user:
                    await btn_interaction.response.send_message("Not your game!", ephemeral=True)
                    return
                await self.stand_action(btn_interaction)

            async def stand_action(self, btn_interaction):
                while hand_value(dealer) < 17:
                    dealer.append(deck.pop())
                pv, dv = hand_value(player), hand_value(dealer)
                if dv > 21 or pv > dv:
                    await database.add_coins(interaction.user.id, interaction.guild.id, bet)
                    new_bal = await database.get_coins(interaction.user.id, interaction.guild.id)
                    result = f"🎉 You win **{bet:,} Uisetcoins**!\nBalance: {new_bal:,}"
                    color = discord.Color.green()
                elif pv == dv:
                    new_bal = await database.get_coins(interaction.user.id, interaction.guild.id)
                    result = f"🤝 Push! Bet returned.\nBalance: {new_bal:,}"
                    color = discord.Color.yellow()
                else:
                    await database.add_coins(interaction.user.id, interaction.guild.id, -bet)
                    new_bal = await database.get_coins(interaction.user.id, interaction.guild.id)
                    result = f"😢 Dealer wins. You lose **{bet:,} Uisetcoins**.\nBalance: {new_bal:,}"
                    color = discord.Color.red()
                embed = await show_state(result, final=True)
                embed.color = color
                self.stop()
                try:
                    await btn_interaction.response.edit_message(embed=embed, view=None)
                except Exception:
                    pass

        view = BJView()
        embed = await show_state()
        await interaction.response.send_message(embed=embed, view=view)

    # ─── Shop ────────────────────────────────────────────────

    @app_commands.command(name="shop", description="Browse the Uisetcoins color role shop")
    async def shop(self, interaction: discord.Interaction):
        import aiosqlite, database as db
        async with aiosqlite.connect(db.DB_PATH) as conn:
            async with conn.execute(
                "SELECT role_id, name, price FROM shop_roles WHERE guild_id=? ORDER BY price",
                (interaction.guild.id,)
            ) as cursor:
                roles = await cursor.fetchall()

        if not roles:
            embed = discord.Embed(
                title="🛍️ Uisetcoins Shop",
                description="No color roles available yet.\nAn admin can add roles with `/shop-add`.",
                color=discord.Color.gold()
            )
            await interaction.response.send_message(embed=embed)
            return

        embed = discord.Embed(title="🛍️ Uisetcoins Color Role Shop", color=discord.Color.gold())
        for role_id, name, price in roles:
            role = interaction.guild.get_role(role_id)
            if role:
                embed.add_field(
                    name=f"{role.name}",
                    value=f"**{price:,} Uisetcoins** • `/buy {name}`",
                    inline=True
                )
        embed.set_footer(text="Use /buy <role name> to purchase a color role!")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="buy", description="Buy a color role from the shop")
    @app_commands.describe(role_name="The name of the role to buy")
    async def buy(self, interaction: discord.Interaction, role_name: str):
        import aiosqlite, database as db
        async with aiosqlite.connect(db.DB_PATH) as conn:
            async with conn.execute(
                "SELECT role_id, price FROM shop_roles WHERE guild_id=? AND LOWER(name)=LOWER(?)",
                (interaction.guild.id, role_name)
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            await interaction.response.send_message(f"❌ No role named **{role_name}** in the shop. Check `/shop`.", ephemeral=True)
            return

        role_id, price = row
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message("❌ That role no longer exists.", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.response.send_message(f"❌ You already have the **{role.name}** role.", ephemeral=True)
            return

        balance = await database.get_coins(interaction.user.id, interaction.guild.id)
        if balance < price:
            await interaction.response.send_message(
                f"❌ You need **{price:,} Uisetcoins** but only have **{balance:,}**.", ephemeral=True
            )
            return

        await database.add_coins(interaction.user.id, interaction.guild.id, -price)
        await interaction.user.add_roles(role, reason="Purchased from Uisetcoins shop")

        embed = discord.Embed(
            title="✅ Role Purchased!",
            description=f"You bought the **{role.name}** role for **{price:,} Uisetcoins**!",
            color=role.color
        )
        new_bal = await database.get_coins(interaction.user.id, interaction.guild.id)
        embed.set_footer(text=f"Remaining balance: {new_bal:,} Uisetcoins")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="shop-add", description="Add a color role to the shop (Admin only)")
    @app_commands.describe(role="The role to sell", price="Price in Uisetcoins")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def shop_add(self, interaction: discord.Interaction, role: discord.Role, price: int):
        if price < 1:
            await interaction.response.send_message("❌ Price must be at least 1.", ephemeral=True)
            return
        import aiosqlite, database as db
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO shop_roles (role_id, guild_id, name, price) VALUES (?,?,?,?)",
                (role.id, interaction.guild.id, role.name, price)
            )
            await conn.commit()
        await interaction.response.send_message(
            f"✅ Added **{role.name}** to the shop for **{price:,} Uisetcoins**.", ephemeral=True
        )

    @app_commands.command(name="shop-remove", description="Remove a role from the shop (Admin only)")
    @app_commands.describe(role="The role to remove from the shop")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def shop_remove(self, interaction: discord.Interaction, role: discord.Role):
        import aiosqlite, database as db
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "DELETE FROM shop_roles WHERE role_id=? AND guild_id=?",
                (role.id, interaction.guild.id)
            )
            await conn.commit()
        await interaction.response.send_message(f"✅ Removed **{role.name}** from the shop.", ephemeral=True)

    @app_commands.command(name="give-coins", description="Give Uisetcoins to a user (Admin only)")
    @app_commands.describe(user="User to give coins to", amount="Amount to give")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def give_coins(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        await database.add_coins(user.id, interaction.guild.id, amount)
        new_bal = await database.get_coins(user.id, interaction.guild.id)
        await interaction.response.send_message(
            f"✅ Gave **{amount:,} Uisetcoins** to {user.mention}. Their balance: **{new_bal:,}**",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Coins(bot))
