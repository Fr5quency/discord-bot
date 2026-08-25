import discord
from discord.ext import commands
import re
import datetime


def parse_time(t: str):
    m = re.fullmatch(r"(\d+)(s|m|h|d)", t.lower())
    if not m:
        return None
    n = int(m.group(1))
    u = m.group(2)
    if u == "s":
        return n
    if u == "m":
        return n * 60
    if u == "h":
        return n * 3600
    if u == "d":
        return n * 86400


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="mute")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def mute(self, ctx, member: discord.Member, duration: str, *, reason=None):
        seconds = parse_time(duration)
        if seconds is None:
            return await ctx.send("❌ Invalid duration format. Use `10s`, `5m`, `1h`, `2d`.")

        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.send("❌ I can't mute that member because their role is equal to or higher than mine.")

        until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)

        try:
            await member.timeout(until, reason=reason)
        except discord.Forbidden:
            return await ctx.send("❌ I don't have permission to timeout that member.")

        await ctx.send(f"<a:PJ_Check:1541526360747548843> Muted {member.mention} for {duration}.")

    @commands.command(name="kick")
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason=None):
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.send("❌ I can't kick that member because their role is equal to or higher than mine.")

        try:
            await member.kick(reason=reason)
        except discord.Forbidden:
            return await ctx.send("❌ I don't have permission to kick that member.")

        await ctx.send(f"<a:PJ_Check:1541526360747548843> Kicked {member.mention}.")

    @commands.command(name="ban")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason=None):
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.send("❌ I can't ban that member because their role is equal to or higher than mine.")

        try:
            await member.ban(reason=reason)
        except discord.Forbidden:
            return await ctx.send("❌ I don't have permission to ban that member.")

        await ctx.send(f"<a:PJ_Check:1541526360747548843> Banned {member.mention}.")

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            return await ctx.send("❌ You don't have permission to use this command.")

        if isinstance(error, commands.BotMissingPermissions):
            return await ctx.send("❌ I don't have the required permission to do that.")

        if isinstance(error, commands.MemberNotFound):
            return await ctx.send(f"❌ Couldn't find a member matching `{error.argument}`. Mention them or use their ID.")

        if isinstance(error, commands.MissingRequiredArgument):
            usage = {
                "mute": "mute @member <10s|5m|1h|2d> [reason]",
                "kick": "kick @member [reason]",
                "ban": "ban @member [reason]"
            }
            example = usage.get(ctx.command.name, ctx.command.name)
            return await ctx.send(f"❌ Missing required argument.\nUsage: `{example}`")

        if isinstance(error, commands.BadArgument):
            return await ctx.send("❌ Invalid argument. Make sure you're mentioning a valid member.")

        if isinstance(error, commands.NoPrivateMessage):
            return await ctx.send("❌ This command can only be used in a server.")

        print(f"Unhandled error in {ctx.command}: {error}")
        await ctx.send("❌ An unexpected error occurred while running that command.")


async def setup(bot):
    await bot.add_cog(Moderation(bot))
