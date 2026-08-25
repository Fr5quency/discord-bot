import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone


class MessageUtility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="message", description="Send a message using the bot.")
    @app_commands.describe(
        content="The message content to send.",
        reply_to="Message ID to reply to (optional).",
        mention_reply="Mention the user in reply? Default: off."
    )
    @app_commands.guild_only()
    async def message(
        self,
        interaction: discord.Interaction,
        content: str,
        reply_to: str | None = None,
        mention_reply: bool = False
    ):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel
        reply_message = None

        if reply_to:
            try:
                reply_message = await channel.fetch_message(int(reply_to))
            except Exception:
                return await interaction.followup.send("❌ Invalid message ID.", ephemeral=True)

        if reply_message:
            await reply_message.reply(content, mention_author=mention_reply)
        else:
            await channel.send(content)

        embed = discord.Embed(
            title="✅ Message Sent",
            description="Your message has been delivered.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="message-edit", description="Edit a bot message.")
    @app_commands.describe(
        message_id="The ID of the message to edit.",
        content="New content for the message."
    )
    @app_commands.guild_only()
    async def message_edit(self, interaction: discord.Interaction, message_id: str, content: str):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel

        try:
            msg = await channel.fetch_message(int(message_id))
        except Exception:
            return await interaction.followup.send("❌ Invalid message ID.", ephemeral=True)

        if msg.author.id != self.bot.user.id:
            return await interaction.followup.send("❌ I can only edit messages sent by me.", ephemeral=True)

        await msg.edit(content=content)

        embed = discord.Embed(
            title="✏️ Message Edited",
            description="The message has been updated.",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(MessageUtility(bot))
