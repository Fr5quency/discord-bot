import discord
from discord.ext import commands
import json
import os
from discord.ui import View, Button, Modal, TextInput
from datetime import datetime, timezone

DATA_FILE = "wallets.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


def get_wallet_embed(user, data):
    user_id = str(user.id)
    wallet = data.get(user_id, {})

    def val(key):
        return wallet.get(key, "Not set")

    embed = discord.Embed(
        title=f"<:PJ_Wallet:1541526481103233095> {user.display_name}'s Wallet",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )

    embed.add_field(name="<:Ltc:1541526350173831268> LTC", value=val("ltc"), inline=False)
    embed.add_field(name="<:btc:1541526427613274204> BTC", value=val("btc"), inline=False)
    embed.add_field(name="<:sol:1541526438153424986> SOL", value=val("sol"), inline=False)
    embed.add_field(name="<:upi:1541526415865020487> UPI", value=val("upi"), inline=False)
    embed.add_field(name="<a:PJ_Warn:1541526448140197960> **__Note__**", value="<:PJ_RedDot:1541526470797820015> To set or update any address use `.wallet update`!")

    return embed


def get_single_wallet_embed(user, data, key, label, emoji):
    user_id = str(user.id)
    wallet = data.get(user_id, {})
    value = wallet.get(key)

    if value:
        embed = discord.Embed(
            title=f"{emoji} {user.display_name}'s {label} Address",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="**<:PJ_Link:1541526460127387649> Address:**", value=f"```{value}```")
        embed.add_field(name="**<a:PJ_Warn:1541526448140197960> Note**", value=f"<:PJ_RedDot:1541526470797820015> This is your **{label}** recieving address.\n<:PJ_RedDot:1541526470797820015> Do not send any other assets they may be lost.\n<:PJ_RedDot:1541526470797820015> Update it anytime via `.wallet update`!")
    else:
        embed = discord.Embed(
            title=f"{emoji} {user.display_name}'s {label} Address",
            description=f"No {label} address saved.\n\n<:PJ_RedDot:1541526470797820015> Use `.wallet update` to set **{label}** address.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )

    return embed


class WalletModal(Modal):
    def __init__(self, user, message):
        super().__init__(title="Update Your Wallet")
        self.user = user
        self.message = message

        data = load_data()
        user_wallet = data.get(str(user.id), {})

        self.ltc = TextInput(label="LTC Address", required=False, default=user_wallet.get("ltc", ""))
        self.btc = TextInput(label="BTC Address", required=False, default=user_wallet.get("btc", ""))
        self.sol = TextInput(label="SOL Address", required=False, default=user_wallet.get("sol", ""))
        self.upi = TextInput(label="UPI ID", required=False, default=user_wallet.get("upi", ""))

        self.add_item(self.ltc)
        self.add_item(self.btc)
        self.add_item(self.sol)
        self.add_item(self.upi)

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        user_id = str(self.user.id)

        if user_id not in data:
            data[user_id] = {}

        data[user_id]["ltc"] = self.ltc.value.strip() if self.ltc.value else None
        data[user_id]["btc"] = self.btc.value.strip() if self.btc.value else None
        data[user_id]["sol"] = self.sol.value.strip() if self.sol.value else None
        data[user_id]["upi"] = self.upi.value.strip() if self.upi.value else None

        data[user_id] = {k: v for k, v in data[user_id].items() if v}

        save_data(data)

        embed = get_wallet_embed(self.user, data)

        await interaction.response.edit_message(embed=embed)


class WalletView(View):
    def __init__(self, user):
        super().__init__(timeout=300)
        self.user = user
        self.message = None

    @discord.ui.button(label="Update Wallet", style=discord.ButtonStyle.primary)
    async def update_wallet(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "You can't edit someone else's wallet.", ephemeral=True
            )

        modal = WalletModal(self.user, interaction.message)
        await interaction.response.send_modal(modal)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class Wallet(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(invoke_without_command=True)
    async def wallet(self, ctx, member: discord.Member = None):
        """View wallet"""
        target = member or ctx.author
        data = load_data()

        embed = get_wallet_embed(target, data)
        await ctx.send(embed=embed)

    @wallet.command(name="update")
    async def wallet_update(self, ctx):
        """Update wallet"""
        data = load_data()
        embed = get_wallet_embed(ctx.author, data)

        view = WalletView(ctx.author)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.command()
    async def ltc(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        data = load_data()
        embed = get_single_wallet_embed(target, data, "ltc", "LTC", "<:Ltc:1541526350173831268>")
        await ctx.send(embed=embed)

    @commands.command()
    async def btc(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        data = load_data()
        embed = get_single_wallet_embed(target, data, "btc", "BTC", "<:btc:1541526427613274204>")
        await ctx.send(embed=embed)

    @commands.command()
    async def sol(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        data = load_data()
        embed = get_single_wallet_embed(target, data, "sol", "SOL", "<:sol:1541526438153424986>")
        await ctx.send(embed=embed)

    @commands.command()
    async def upi(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        data = load_data()
        embed = get_single_wallet_embed(target, data, "upi", "UPI", "<:upi:1541526415865020487>")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Wallet(bot))
