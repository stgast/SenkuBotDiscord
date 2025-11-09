import discord
from discord.ext import commands
import asyncio
from bot.config import config


intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True
intents.messages = True


bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

async def _load_cogs():
    await bot.load_extension("bot.cogs.moderation")

def run_bot():
    async def _start():
        await _load_cogs()
        await bot.start(config.TOKEN)

    asyncio.run(_start())
