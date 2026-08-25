import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import time
import random
import asyncio
import datetime

DATA_FILE = "giveaways.json"
GIVEAWAY_EMOJI_ID = 1541526373624193084


def is_giveaway_emoji(reaction_emoji) -> bool:
    return getattr(reaction_emoji, "id", None) == GIVEAWAY_EMOJI_ID


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


async def delete_prefix(ctx):
    if ctx.interaction is None:
        await asyncio.sleep(1)
        try:
            await ctx.message.delete()
        except Exception:
            pass


def has_giveaway_perms():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator:
            return True
        role = discord.utils.get(ctx.author.roles, name="Giveaways")
        if role:
            return True
        msg = await ctx.send("You don't have permission to use giveaway commands.")
        await asyncio.sleep(5)
        await msg.delete()
        return False
    return commands.check(predicate)


class Giveaway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.giveaway_loop.start()
        self.cleanup_loop.start()

    def cog_unload(self):
        self.giveaway_loop.cancel()
        self.cleanup_loop.cancel()

    def parse_time(self, time_str):
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        return int(time_str[:-1]) * units[time_str[-1]]

    @tasks.loop(seconds=5)
    async def giveaway_loop(self):
        data = load_data()
        now = int(time.time())

        for msg_id, giveaway in list(data.items()):
            if giveaway["status"] == "active":
                if giveaway["end_timestamp"] <= now:
                    await self.end_giveaway(int(msg_id), ended_by=None)

    @giveaway_loop.before_loop
    async def before_giveaway_loop(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def cleanup_loop(self):
        data = load_data()
        now = int(time.time())

        for msg_id, giveaway in list(data.items()):
            if giveaway["status"] == "ended":
                if giveaway["ended_at"] and now >= giveaway["ended_at"] + 604800:
                    del data[msg_id]

        save_data(data)

    @cleanup_loop.before_loop
    async def before_cleanup_loop(self):
        await self.bot.wait_until_ready()

    async def end_giveaway(self, message_id, ended_by=None):
        data = load_data()
        giveaway = data.get(str(message_id))
        if not giveaway or giveaway["status"] != "active":
            return

        channel = self.bot.get_channel(giveaway["channel_id"])
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
        except Exception:
            del data[str(message_id)]
            save_data(data)
            return

        users = []
        for reaction in message.reactions:
            if is_giveaway_emoji(reaction.emoji):
                async for user in reaction.users():
                    if not user.bot:
                        users.append(user)

        winners = []

        if users:
            winners = random.sample(users, min(len(users), giveaway["winner_count"]))

        giveaway["status"] = "ended"
        giveaway["ended_at"] = int(time.time())
        giveaway["winners"] = [u.id for u in winners]
        prize = giveaway["prize"]
        ended_time = int(time.time())
        save_data(data)

        winner_mentions = ""
        if winners:
            winner_mentions = ", ".join([u.mention for u in winners])
            await channel.send(
                f"<a:PJ_Giveaway:1541526373624193084> Congratulations, {winner_mentions}. You won **{prize}**!"
            )
        else:
            await channel.send("No valid entries. Giveaway ended with no winners.")

        original = message.embeds[0]
        embed = original.copy()

        embed.title = f"<a:PJ_Present:1541526383866679437> {prize} <a:PJ_Present:1541526383866679437>"
        embed.color = discord.Color.red()

        desc = original.description or ""

        if winners:
            desc += f"\n\n**Winners:** {winner_mentions}"
        else:
            desc += "\n\n**Winners:** None"

        if ended_by:
            desc += f"\n**Ended By:** {ended_by.mention}"
        else:
            desc += "\n**Ended By:** Time up"

        embed.description = desc
        embed.timestamp = datetime.datetime.fromtimestamp(ended_time, tz=datetime.timezone.utc)
        embed.set_footer(text="Ended")

        await message.edit(
            content="<:PJ_Gift:1541526393894993942> **Giveaway Ended** <:PJ_Gift:1541526393894993942>",
            embed=embed
        )

    @commands.hybrid_command()
    @has_giveaway_perms()
    async def gstart(self, ctx, duration: str, winners: int, *, prize: str):
        seconds = self.parse_time(duration)
        end_time = int(time.time()) + seconds

        embed = discord.Embed(
            title=f"<a:PJ_Present:1541526383866679437> {prize} <a:PJ_Present:1541526383866679437>",
            description=(
                f"<:PJ_Dot:1541526405672607847> **No. of Winners:** {winners}\n"
                f"<:PJ_Dot:1541526405672607847> **Hosted By:** {ctx.author.mention}\n"
                f"<:PJ_Dot:1541526405672607847> **Ends:** <t:{end_time}:R>\n\n"
                f"<:PJ_Dot:1541526405672607847> React with <a:PJ_Giveaway:1541526373624193084> to participate!"
            ),
            color=discord.Color(0x005FFF)
        )

        embed.timestamp = datetime.datetime.fromtimestamp(end_time, tz=datetime.timezone.utc)
        embed.set_footer(text="Ends")

        message = await ctx.send(
            "<:PJ_Gift:1541526393894993942> **New Giveaway** <:PJ_Gift:1541526393894993942>",
            embed=embed
        )

        await message.add_reaction("<a:PJ_Giveaway:1541526373624193084>")

        data = load_data()
        data[str(message.id)] = {
            "guild_id": ctx.guild.id,
            "channel_id": ctx.channel.id,
            "host_id": ctx.author.id,
            "prize": prize,
            "winner_count": winners,
            "start_timestamp": int(time.time()),
            "end_timestamp": end_time,
            "status": "active",
            "winners": [],
            "ended_at": None
        }
        save_data(data)

        await delete_prefix(ctx)

    @commands.hybrid_command()
    @has_giveaway_perms()
    async def gend(self, ctx, message_id: int):
        await self.end_giveaway(message_id, ended_by=ctx.author)
        await delete_prefix(ctx)

    @commands.hybrid_command()
    @has_giveaway_perms()
    async def greroll(self, ctx, message_id: int):

        data = load_data()
        giveaway = data.get(str(message_id))

        if not giveaway or giveaway["status"] != "ended":
            if ctx.interaction:
                return await ctx.interaction.response.send_message(
                    "That giveaway is not ended or doesn't exist.",
                    ephemeral=True
                )
            else:
                msg = await ctx.send("That giveaway is not ended or doesn't exist.")
                await asyncio.sleep(5)
                await msg.delete()
                await delete_prefix(ctx)
                return

        channel = self.bot.get_channel(giveaway["channel_id"])
        message = await channel.fetch_message(message_id)

        users = []
        for reaction in message.reactions:
            if is_giveaway_emoji(reaction.emoji):
                async for user in reaction.users():
                    if not user.bot and user.id not in giveaway["winners"]:
                        users.append(user)

        if not users:
            if ctx.interaction:
                return await ctx.interaction.response.send_message(
                    "No eligible users for reroll.",
                    ephemeral=True
                )
            else:
                msg = await ctx.send("No eligible users for reroll.")
                await asyncio.sleep(5)
                await msg.delete()
                await delete_prefix(ctx)
                return

        winner = random.choice(users)

        giveaway["winners"].append(winner.id)
        save_data(data)

        await channel.send(
            f"<a:PJ_Giveaway:1541526373624193084> Rerolled Winner: {winner.mention} won **{giveaway['prize']}**!"
        )

        await delete_prefix(ctx)

    @commands.hybrid_command()
    @has_giveaway_perms()
    async def gdelete(self, ctx, message_id: int):

        data = load_data()
        giveaway = data.get(str(message_id))

        if not giveaway or giveaway["status"] != "active":
            if ctx.interaction:
                return await ctx.interaction.response.send_message(
                    "Active giveaway not found.",
                    ephemeral=True
                )
            else:
                msg = await ctx.send("Active giveaway not found.")
                await asyncio.sleep(5)
                await msg.delete()
                await delete_prefix(ctx)
                return

        channel = self.bot.get_channel(giveaway["channel_id"])

        try:
            message = await channel.fetch_message(message_id)
            await message.delete()
        except Exception:
            pass

        del data[str(message_id)]
        save_data(data)

        if ctx.interaction:
            await ctx.interaction.response.send_message(
                "Giveaway deleted successfully.",
                ephemeral=True
            )
        else:
            msg = await ctx.send("Giveaway deleted successfully.")
            await asyncio.sleep(5)
            await msg.delete()
            await delete_prefix(ctx)

    @app_commands.command(name="glist")
    async def glist(self, interaction: discord.Interaction):

        data = load_data()
        active = [
            (msg_id, g) for msg_id, g in data.items()
            if g["status"] == "active"
        ]

        if not active:
            return await interaction.response.send_message(
                "No active giveaways.",
                ephemeral=True
            )

        embed = discord.Embed(
            title="<a:PJ_Giveaway:1541526373624193084> Active Giveaways",
            color=discord.Color.blue()
        )

        for msg_id, g in active:
            embed.add_field(
                name=g["prize"],
                value=(
                    f"Channel: <#{g['channel_id']}>\n"
                    f"Winners: {g['winner_count']}\n"
                    f"Ends <t:{g['end_timestamp']}:R>\n"
                    f"[Jump](https://discord.com/channels/{g['guild_id']}/{g['channel_id']}/{msg_id})"
                ),
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ghelp")
    async def ghelp(self, interaction: discord.Interaction):

        embed = discord.Embed(
            title="Giveaway Commands",
            description=(
                "**Hybrid Commands**\n"
                "`gstart <time> <winners> <prize>`\n"
                "`gend <message_id>`\n"
                "`greroll <message_id>`\n"
                "`gdelete <message_id>`\n\n"
                "**Slash Commands**\n"
                "`/glist`\n"
                "`/ghelp`"
            ),
            color=discord.Color.blurple()
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):

        if ctx.interaction:
            return

        if isinstance(error, commands.CommandNotFound):
            return

        if ctx.command is None or ctx.command.cog is not self:
            return

        usage = {
            "gstart": "gstart 10m 1 Nitro",
            "gend": "gend 123456789012345678",
            "greroll": "greroll 123456789012345678",
            "gdelete": "gdelete 123456789012345678"
        }

        command_name = ctx.command.name if ctx.command else None
        example = usage.get(command_name, command_name)

        if isinstance(error, commands.MissingRequiredArgument):
            msg = await ctx.send(
                f"Missing required argument.\nUsage: `{example}`"
            )

        elif isinstance(error, commands.BadArgument):
            msg = await ctx.send(
                f"Invalid argument provided.\nExample: `{example}`"
            )

        elif isinstance(error, commands.CheckFailure):
            msg = await ctx.send(
                "You don't have permission to use giveaway commands."
            )

        else:
            msg = await ctx.send(
                "An unexpected error occurred while running the command."
            )

        await asyncio.sleep(5)

        try:
            await msg.delete()
        except Exception:
            pass

        try:
            await ctx.message.delete()
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(Giveaway(bot))
