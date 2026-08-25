import discord
from discord.ext import commands
import json
import os
import asyncio

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)


def load_config():
    with open("config.json", "r") as f:
        return json.load(f)


config = load_config()
TOKEN = config.get("token")


async def load_cogs():
    cog_folder = "./cogs"

    for filename in os.listdir(cog_folder):
        if filename.endswith(".py") and not filename.startswith("_"):
            module_path = f"cogs.{filename[:-3]}"
            try:
                await bot.load_extension(module_path)
                print(f"Loaded: {module_path}")
            except Exception as e:
                print(f"Failed to load {module_path}: {e}")


async def update_status():
    await bot.wait_until_ready()
    while not bot.is_closed():
        server_count = len(bot.guilds)
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name=f".help in {server_count} servers!"
        )
        await bot.change_presence(status=discord.Status.idle, activity=activity)
        await asyncio.sleep(600)


async def update_status_once():
    server_count = len(bot.guilds)
    activity = discord.Activity(
        type=discord.ActivityType.listening,
        name=f".help in {server_count} servers!"
    )
    await bot.change_presence(status=discord.Status.idle, activity=activity)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    print("Bot is ready.")
    bot.loop.create_task(update_status())


@bot.event
async def on_guild_join(guild):
    await update_status_once()


@bot.event
async def on_guild_remove(guild):
    await update_status_once()


@bot.event
async def setup_hook():
    await load_cogs()
    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} slash commands.")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("No token found. Add your bot token to config.json before running.")
    bot.run(TOKEN)
