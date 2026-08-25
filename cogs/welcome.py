import discord
from discord.ext import commands
from discord import app_commands
import json
import os

DATA_FILE = "welcome_data.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


def fill_placeholders(text: str, member: discord.Member) -> str:
    return (
        text.replace("{user}", member.mention)
        .replace("{server}", member.guild.name)
        .replace("{membercount}", str(member.guild.member_count))
    )


class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    welcome_group = app_commands.Group(name="welcome", description="Configure the welcome message")

    @welcome_group.command(name="setchannel", description="Set the channel where welcome messages are sent.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(channel="The channel to send welcome messages in")
    async def setchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        data = load_data()
        gd = data.setdefault(str(interaction.guild_id), {})
        gd["channel_id"] = channel.id
        save_data(data)

        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"✅ Welcome messages will now be sent in {channel.mention}.",
                color=discord.Color.green()
            ),
            ephemeral=True
        )

    @welcome_group.command(name="setembed", description="Customize the welcome embed's title and description.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        title="Embed title. Supports {user}, {server}, {membercount}",
        description="Embed description. Supports {user}, {server}, {membercount}"
    )
    async def setembed(self, interaction: discord.Interaction, title: str, description: str):
        data = load_data()
        gd = data.setdefault(str(interaction.guild_id), {})
        gd["embed_title"] = title
        gd["embed_description"] = description
        save_data(data)

        preview = discord.Embed(
            title=fill_placeholders(title, interaction.user) if interaction.guild else title,
            description=fill_placeholders(description, interaction.user) if interaction.guild else description,
            color=discord.Color.blurple()
        )

        await interaction.response.send_message(
            content="✅ Welcome embed updated. Preview:",
            embed=preview,
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        data = load_data()
        gd = data.get(str(member.guild.id))

        if not gd or not gd.get("channel_id"):
            return

        channel = member.guild.get_channel(gd["channel_id"])
        if not channel:
            return

        mention_text = f"👋 {member.mention} welcome to the server!"

        title = gd.get("embed_title", "Welcome!")
        description = gd.get("embed_description", "We're glad to have you here, {user}!")

        embed = discord.Embed(
            title=fill_placeholders(title, member),
            description=fill_placeholders(description, member),
            color=discord.Color.blurple()
        )
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)

        try:
            await channel.send(content=mention_text, embed=embed)
        except discord.Forbidden:
            pass


async def setup(bot):
    await bot.add_cog(Welcome(bot))
