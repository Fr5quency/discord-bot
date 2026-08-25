import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone


class DM(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="dm", description="Send a message to a user via DM.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def dm(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        description: str,
        title: str | None = None,
        colour: str | None = None,
        field_name: str | None = None,
        field_value: str | None = None
    ):
        try:
            server_name = interaction.guild.name if interaction.guild else "Server"

            embed_title = title if title else "📩 Message from the Staff Team"

            if colour:
                try:
                    embed_color = discord.Color(int(colour.replace("#", ""), 16))
                except Exception:
                    embed_color = discord.Color.green()
            else:
                embed_color = discord.Color.green()

            dm_embed = discord.Embed(
                title=embed_title,
                description=description,
                color=embed_color,
                timestamp=datetime.now(timezone.utc)
            )

            if field_name or field_value:
                dm_embed.add_field(
                    name=field_name if field_name else " ",
                    value=field_value if field_value else " ",
                    inline=False
                )

            dm_embed.set_footer(text=f"Sent from {server_name}")

            try:
                await user.send(embed=dm_embed)
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description=f"✅ Your message was sent successfully to {user.mention}.",
                        color=discord.Color.green(),
                        timestamp=datetime.now(timezone.utc)
                    ),
                    ephemeral=True
                )
            except discord.Forbidden:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⚠️ DM Failed",
                        description=f"Couldn't send a message to {user.mention} — their DMs appear to be closed.",
                        color=discord.Color.red(),
                        timestamp=datetime.now(timezone.utc)
                    ),
                    ephemeral=True
                )

        except Exception:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ Error",
                    description="An unexpected error occurred while trying to send the DM.",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                ),
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(DM(bot))
