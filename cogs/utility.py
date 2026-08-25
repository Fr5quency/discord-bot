import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone


class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="membercount", description="Show the server's member count.")
    @app_commands.guild_only()
    async def membercount(self, interaction: discord.Interaction):
        humans = sum(1 for m in interaction.guild.members if not m.bot)
        bots = sum(1 for m in interaction.guild.members if m.bot)

        embed = discord.Embed(
            title=interaction.guild.name,
            description=f"Total Member Count: **{interaction.guild.member_count}**",
            timestamp=discord.utils.utcnow(),
            color=discord.Color.blurple()
        )

        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)

        embed.add_field(
            name=" ",
            value=f"👥 Members: **{humans}**\n🤖 Bots: **{bots}**",
            inline=False
        )

        await interaction.response.send_message(embed=embed)

    @commands.command(name="ping")
    @commands.guild_only()
    async def ping(self, ctx: commands.Context):
        if not ctx.author.guild_permissions.administrator:
            embed = discord.Embed(
                title="❌ Missing Permission",
                description="You need Administrator permission.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            return await ctx.send(embed=embed)

        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latency: `{round(self.bot.latency * 1000)}ms`",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Utility(bot))
