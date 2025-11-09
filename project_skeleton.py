# Project: discord-news-bot
# Description: Bot that scrapes MyAnimeList news and sends to moderation channel for approval.

# File tree (to copy into your project):
#
# discord-news-bot/
# ├── README.md
# ├── requirements.txt
# ├── .env
# ├── run.py
# ├── bot/
# │   ├── __init__.py
# │   ├── main.py
# │   ├── config.py
# │   ├── parser.py
# │   ├── storage.py
# │   ├── utils.py
# │   └── cogs/
# │       └── moderation.py
# └── data/
#     └── processed.json

# ---------------------- README.md ----------------------
# (This file is included below; open it in your editor.)

"""
# Discord News Bot (MyAnimeList)

Кратко: бот периодически парсит https://myanimelist.net/news и отправляет новости в канал модерации. Модераторы ставят реакции ✅/❌ — при ✅ бот публикует новость в целевой канал.

## Этапы проекта
1. Структура проекта, базовый бот и конфиг — **сейчас**
2. Парсер новостей (aiohttp + BeautifulSoup) + unit-тесты
3. Отправка в канал модерации, добавление реакций
4. Обработка реакций, фильтр по роли, публикация в канал
5. Хранение состояния (JSON или SQLite) чтобы избежать дублей
6. Улучшения: кнопки (discord.ui), логирование, Docker, CI

## Быстрый старт
1. Скопируй файлы из репозитория
2. Создай `.env` на основе `.env`
3. Установи зависимости: `pip install -r requirements.txt`
4. Запусти: `python run.py`

"""

# ---------------------- requirements.txt ----------------------
# discord.py v2.x compatible; choose latest stable version

"""
discord.py>=2.3.2
aiohttp>=3.8.1
beautifulsoup4>=4.12.2
python-dotenv>=1.0.0
"""

# ---------------------- .env ----------------------
"""
DISCORD_TOKEN=your_bot_token_here
MODERATION_CHANNEL_ID=123456789012345678
APPROVED_CHANNEL_ID=987654321098765432
MODERATOR_ROLE_ID=111111111111111111
CHECK_INTERVAL_MINUTES=10
"""

# ---------------------- run.py ----------------------
"""
# Entry point — запускает бота
from bot.main import run_bot

if __name__ == '__main__':
    run_bot()
"""

# ---------------------- bot/__init__.py ----------------------
"""
# package marker
"""

# ---------------------- bot/config.py ----------------------
"""
# Configuration loader
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TOKEN = os.getenv('DISCORD_TOKEN')
    MODERATION_CHANNEL_ID = int(os.getenv('MODERATION_CHANNEL_ID')) if os.getenv('MODERATION_CHANNEL_ID') else None
    APPROVED_CHANNEL_ID = int(os.getenv('APPROVED_CHANNEL_ID')) if os.getenv('APPROVED_CHANNEL_ID') else None
    MODERATOR_ROLE_ID = int(os.getenv('MODERATOR_ROLE_ID')) if os.getenv('MODERATOR_ROLE_ID') else None
    CHECK_INTERVAL_MINUTES = int(os.getenv('CHECK_INTERVAL_MINUTES', '10'))


config = Config()
"""

# ---------------------- bot/parser.py ----------------------
"""
# Fetch and parse latest news from MyAnimeList using aiohttp + BeautifulSoup
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict

MAL_NEWS_URL = 'https://myanimelist.net/news'

async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url, timeout=15) as resp:
        resp.raise_for_status()
        return await resp.text()

async def parse_latest_news(limit: int = 5) -> List[Dict]:
    """Return list of dicts: {title, link, image, excerpt, id}
    id should be unique — we can use the link as id.
    """
    async with aiohttp.ClientSession() as session:
        html = await fetch_page(session, MAL_NEWS_URL)

    soup = BeautifulSoup(html, 'html.parser')
    news_units = soup.select('.news-unit')

    results = []
    for unit in news_units[:limit]:
        a = unit.select_one('p.title a')
        if not a:
            continue
        title = a.text.strip()
        link = a['href']
        # image might be in <img data-src> or <img src>
        img = None
        img_tag = unit.select_one('img')
        if img_tag:
            img = img_tag.get('data-src') or img_tag.get('src')
        excerpt_tag = unit.select_one('.text')
        excerpt = excerpt_tag.text.strip() if excerpt_tag else ''
        results.append({
            'id': link,
            'title': title,
            'link': link,
            'image': img,
            'excerpt': excerpt,
        })
    return results
"""

# ---------------------- bot/storage.py ----------------------
"""
# Simple JSON storage to remember processed news IDs
import json
from pathlib import Path
from typing import Set

DATA_FILE = Path('data/processed.json')

class Storage:
    def __init__(self, path: Path = DATA_FILE):
        self.path = path
        self._data: Set[str] = set()
        self._load()

    def _load(self):
        if not self.path.exists():
            self._data = set()
            return
        try:
            with self.path.open('r', encoding='utf-8') as f:
                arr = json.load(f)
            self._data = set(arr)
        except Exception:
            self._data = set()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('w', encoding='utf-8') as f:
            json.dump(list(self._data), f, ensure_ascii=False, indent=2)

    def seen(self, item_id: str) -> bool:
        return item_id in self._data

    def add(self, item_id: str):
        self._data.add(item_id)
        self.save()

storage = Storage()
"""

# ---------------------- bot/utils.py ----------------------
"""
# Utility helpers (embed builder etc.)
import discord

def build_news_embed(news: dict) -> discord.Embed:
    title = news.get('title')
    link = news.get('link')
    desc = news.get('excerpt', '')
    emb = discord.Embed(title=title, url=link, description=(desc[:300] + '...') if desc else None)
    if news.get('image'):
        emb.set_image(url=news['image'])
    return emb
"""

# ---------------------- bot/cogs/moderation.py ----------------------
"""
# Cog that handles posting to moderation channel and reaction handling
from discord.ext import commands, tasks
import discord
from bot.config import config
from bot.parser import parse_latest_news
from bot.storage import storage
from bot.utils import build_news_embed

class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_news_task.start()

    def cog_unload(self):
        self.check_news_task.cancel()

    @tasks.loop(minutes=config.CHECK_INTERVAL_MINUTES)
    async def check_news_task(self):
        channel = self.bot.get_channel(config.MODERATION_CHANNEL_ID)
        if channel is None:
            return
        try:
            news_list = await parse_latest_news(limit=5)
        except Exception as e:
            print('Failed to parse news:', e)
            return

        for item in news_list:
            if storage.seen(item['id']):
                continue
            storage.add(item['id'])
            embed = build_news_embed(item)
            msg = await channel.send(embed=embed)
            await msg.add_reaction('✅')
            await msg.add_reaction('❌')

    @check_news_task.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        # ignore bot reactions
        if user.bot:
            return

        message = reaction.message
        if message.channel.id != config.MODERATION_CHANNEL_ID:
            return

        # check role
        member = message.guild.get_member(user.id)
        if member is None:
            return
        has_role = any(r.id == config.MODERATOR_ROLE_ID for r in member.roles)
        if not has_role:
            return

        if str(reaction.emoji) == '✅':
            approved_channel = self.bot.get_channel(config.APPROVED_CHANNEL_ID)
            if approved_channel and message.embeds:
                await approved_channel.send(embed=message.embeds[0])


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
"""

# ---------------------- bot/main.py ----------------------
"""
# Bot bootstrap — loads cogs and runs
import discord
from discord.ext import commands
import asyncio
from bot.config import config

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')

async def _load_cogs():
    # load moderation cog
    await bot.load_extension('bot.cogs.moderation')

def run_bot():
    async def _start():
        await _load_cogs()
        await bot.start(config.TOKEN)

    asyncio.run(_start())
"""

# ---------------------- data/processed.json ----------------------
"""
# Initially empty array
[]
"""

# ---------------------- Notes and next steps ----------------------
# - This skeleton uses tasks.loop in a Cog to periodically check the MAL news page.
# - Storage is a simple JSON file; you can swap to SQLite later.
# - For production, add error handling, logging, and rate limiting for requests.
# - If you want, I can now:  
#   1) implement the first-stage locally (I provided the skeleton here) or
#   2) generate these files as downloadable archive (zip).

# End of textdoc
