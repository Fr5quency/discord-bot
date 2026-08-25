import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import time

DATA_FILE = "afk_data.json"


class AFK(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.afk_users = self.load_data()

    def load_data(self):
        if not os.path.exists(DATA_FILE):
            return {}

        with open(DATA_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}

    def save_data(self):
        with open(DATA_FILE, "w") as f:
            json.dump(self.afk_users, f, indent=4)

    async def set_afk_logic(self, user: discord.User, reason: str):
        user_id = str(user.id)

        self.afk_users[user_id] = {
            "reason": reason,
            "since": int(time.time())
        }

        self.save_data()

        embed = discord.Embed(
            title="AFK Set!",
            description=f"😴 You are now AFK.\n\n**Reason:** {reason}",
            color=discord.Color.orange()
        )
        embed.set_author(name=f"{user}", icon_url=user.display_avatar.url)

        return embed

    @app_commands.command(name="afk", description="Set yourself as AFK")
    @app_commands.describe(reason="Reason for going AFK")
    async def afk_slash(self, interaction: discord.Interaction, reason: str = "No reason provided"):
        embed = await self.set_afk_logic(interaction.user, reason)
        await interaction.response.send_message(embed=embed)

    @commands.command(name="afk")
    async def afk_prefix(self, ctx: commands.Context, *, reason: str = "No reason provided"):
        embed = await self.set_afk_logic(ctx.author, reason)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        ctx = await self.bot.get_context(message)
        if ctx.command:
            return

        user_id = str(message.author.id)

        if user_id in self.afk_users:
            data = self.afk_users[user_id]
            afk_since = data["since"]

            del self.afk_users[user_id]
            self.save_data()

            embed = discord.Embed(
                description=f"👋 Welcome back {message.author.mention}!",
                color=discord.Color.green()
            )
            embed.add_field(
                name="AFK Duration",
                value=f"You were AFK since <t:{afk_since}:R>",
                inline=False
            )
            embed.set_footer(text="AFK status removed")

            await message.channel.send(embed=embed)

        for user in message.mentions:
            mentioned_id = str(user.id)

            if mentioned_id in self.afk_users:
                data = self.afk_users[mentioned_id]
                reason = data["reason"]
                afk_since = f"<t:{data['since']}:R>"

                embed = discord.Embed(
                    description=f"💤 {user.mention} is currently AFK, **Since:** {afk_since} for **Reason:** {reason}",
                    color=discord.Color.red()
                )
                embed.set_author(name=user, icon_url=user.display_avatar.url)

                await message.channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AFK(bot))
