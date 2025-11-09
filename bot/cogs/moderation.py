from discord.ext import commands, tasks
import discord
import asyncio
from bot.config import config
from bot.parser import parse_latest_news
from bot.storage import storage

class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_news.start()
        # Множество message.id, которые сейчас обрабатываются (предотвращает дубли при одновременных реакциях)
        self.processing = set()

    def cog_unload(self):
        self.check_news.cancel()

    @commands.command(name="lastnews")
    async def last_news(self, ctx):
        """Отправляет последнюю новость с MyAnimeList"""
        await ctx.send("🔍 Загружаю последнюю новость, подожди немного...")

        try:
            news_list = await parse_latest_news(limit=1)
            if not news_list:
                await ctx.send("❌ Не удалось получить новости.")
                return

            item = news_list[0]

            embed = discord.Embed(
                title=item["title"],
                url=item.get("link"),
                description=item["excerpt"][:3000],  # чтобы embed не был слишком длинным
                color=discord.Color.blurple()
            )

            if item.get("image"):
                embed.set_image(url=item["image"])

            # footer убран — embed уже содержит ссылку на оригинал

            # Отправляем embed и пытаемся добавить реакции так же, как в check_news
            try:
                msg = await ctx.send(embed=embed)
            except Exception as e:
                await ctx.send(f"Ошибка при отправке новости: {e}")
                print("lastnews: Error sending embed:", e)
                return

            print(f"lastnews: sent msg type={type(msg)} id={getattr(msg,'id',None)} author={getattr(msg,'author',None)} webhook_id={getattr(msg,'webhook_id',None)}")

            # Если объект не поддерживает add_reaction — попробуем получить реальное Message
            if not hasattr(msg, "add_reaction") or not callable(getattr(msg, "add_reaction", None)):
                try:
                    fetched = await ctx.channel.fetch_message(getattr(msg, "id", None))
                    if fetched:
                        msg = fetched
                        print(f"lastnews: fetched message id={msg.id} type={type(msg)}")
                except Exception as e:
                    print("lastnews: fetch failed:", e)

            # Добавляем реакции с обработкой ошибок
            try:
                for emoji in ("✅", "❌"):
                    await msg.add_reaction(emoji)
                    print(f"lastnews: added reaction {emoji} to id={getattr(msg,'id',None)}")
                    await asyncio.sleep(0.25)
            except discord.Forbidden:
                print("lastnews: No permission to add reactions.")
            except Exception as e:
                print("lastnews: Error adding reaction:", e)

        except Exception as e:
            await ctx.send(f"⚠️ Ошибка при получении новости: {e}")
            print("Error in lastnews command:", e)

    @tasks.loop(minutes=config.CHECK_INTERVAL_MINUTES)
    async def check_news(self):
        channel = self.bot.get_channel(config.MODERATION_CHANNEL_ID)
        if not channel:
            print("Канал модерации не найден (check_news).")
            return
        try:
            news_list = await parse_latest_news(limit=config.NEWS_LIMIT)
        except Exception as e:
            print("Error fetching news:", e)
            return

        # Получаем bot_member и права заранее
        bot_member = None
        if channel.guild:
            bot_member = channel.guild.get_member(self.bot.user.id) or channel.guild.me
            if not bot_member:
                try:
                    bot_member = await channel.guild.fetch_member(self.bot.user.id)
                except Exception:
                    bot_member = channel.guild.me
        perms = channel.permissions_for(bot_member) if bot_member else None
        print(f"Bot member: {bot_member} perms: {perms}")

        for item in news_list:
            if storage.seen(item["id"]):
                # Попробуем найти уже отправленное сообщение и добавить недостающие реакции
                try:
                    found = None
                    async for m in channel.history(limit=200):
                        if m.embeds and m.embeds[0].title == item["title"]:
                            found = m
                            break
                    if found:
                        existing = [str(r.emoji) for r in found.reactions]
                        to_add = [e for e in ("✅", "❌") if e not in existing]
                        if to_add:
                            print(f"Найдена старая новость (id={item['id']}) — добавляю недостающие реакции: {to_add}")
                            for emoji in to_add:
                                try:
                                    await found.add_reaction(emoji)
                                    print(f"Восстановлена реакция {emoji} для сообщения id={found.id}")
                                    await asyncio.sleep(0.25)
                                except Exception as e:
                                    print("Ошибка при восстановлении реакции:", e)
                        else:
                            print(f"Найдена старая новость (id={item['id']}) — реакции уже присутствуют.")
                        continue
                except Exception as e:
                    print("Ошибка при поиске/восстановлении старого сообщения:", e)
                    # продолжаем; если не найдена — не отправлять повторно
                    continue
            storage.add(item["id"])
            embed = discord.Embed(
                title=item["title"],
                url=item.get("link"),
                description=item["excerpt"][:300] + "...",
                color=discord.Color.blurple()
            )
            # (footer убран по просьбе) URL новости добавлен в embed.url

            # Встраиваем картинку в embed, если есть
            if item.get("image"):
                try:
                    embed.set_image(url=item["image"])
                except Exception as e:
                    print("Error setting embed image:", e)

            # не отправляем картинку отдельно — она уже в embed

            try:
                msg = await channel.send(embed=embed)
            except Exception as e:
                print("Error sending embed:", e)
                continue

            print(f"Отправлено сообщение типа {type(msg)} id={getattr(msg, 'id', None)} author={getattr(msg, 'author', None)} webhook_id={getattr(msg, 'webhook_id', None)}")

            # Если объект не поддерживает add_reaction — попробуем получить реальное Message
            if not hasattr(msg, "add_reaction") or not callable(getattr(msg, "add_reaction", None)):
                try:
                    fetched = await channel.fetch_message(getattr(msg, "id", None))
                    if fetched:
                        msg = fetched
                        print(f"Получено сообщение через fetch_message: id={msg.id} author={getattr(msg, 'author', None)} webhook_id={getattr(msg, 'webhook_id', None)}")
                except Exception as e:
                    print("Не удалось получить сообщение через fetch_message:", e)

            # Проверяем ещё раз права перед добавлением реакций
            try:
                bot_member = channel.guild.get_member(self.bot.user.id) or channel.guild.me
                perms = channel.permissions_for(bot_member) if bot_member else None
                print(f"Права перед add_reaction: {perms}")
            except Exception as e:
                print("Не удалось определить права перед add_reaction:", e)

            # Добавляем реакции с обработкой ошибок и паузой
            for emoji in ("✅", "❌"):
                try:
                    if perms and not perms.add_reactions:
                        print("У бота нет права add_reactions — пропускаю добавление реакций.")
                        break
                    await msg.add_reaction(emoji)
                    print(f"Добавлена реакция {emoji} для сообщения id={getattr(msg, 'id', None)}")
                    await asyncio.sleep(0.25)
                except discord.Forbidden:
                    print("Нет прав добавлять реакции в этом канале.")
                    break
                except Exception as e:
                    print("Ошибка при добавлении реакции:", e)

    @check_news.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        # Оставляем старый обработчик пустым, чтобы не создавать дубли при одновременном срабатывании raw-обработчика
        # Всё реальное поведение по одобрению теперь в on_raw_reaction_add
        if user.bot:
            return
        # Дополнительный лог для отладки
        try:
            print(f"on_reaction_add (ignored) reaction={reaction.emoji} user={user} message_id={getattr(reaction.message,'id',None)}")
        except Exception:
            pass
        return

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Обработка реакций, когда сообщение может отсутствовать в кеше
        if payload.user_id == self.bot.user.id:
            return
        if payload.channel_id != config.MODERATION_CHANNEL_ID:
            return

        # Попытаться получить канал
        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(payload.channel_id)
            except Exception as e:
                print("Не удалось получить канал для raw reaction:", e)
                return

        # Получаем сообщение
        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception as e:
            print("Не удалось получить сообщение для raw reaction:", e)
            return

        # Если исходное сообщение уже помечено (📌), значит оно уже обработано — пропускаем
        try:
            has_pin = False
            for r in message.reactions:
                try:
                    if str(r.emoji) == '📌':
                        has_pin = True
                        break
                except Exception:
                    continue
            if has_pin:
                print(f"Сообщение id={message.id} уже обработано (найдена реакция 📌) — пропускаю.")
                return
        except Exception:
            pass

        # Получаем участника
        guild = message.guild
        member = None
        if guild:
            member = guild.get_member(payload.user_id)
            if not member:
                try:
                    member = await guild.fetch_member(payload.user_id)
                except Exception:
                    member = None
        if not member:
            return

        has_role = any(r.id == config.MODERATOR_ROLE_ID for r in member.roles)
        if not has_role:
            return

        emoji = str(payload.emoji)
        if emoji == "✅":
            if not message.embeds:
                print("Сообщение не содержит embed для отправки в канал одобренных (raw).")
                return

            emb = message.embeds[0]

            # Предотвращаем одновременную обработку одного и того же сообщения
            if message.id in self.processing:
                print(f"Сообщение id={message.id} уже обрабатывается — пропускаю.")
                return
            self.processing.add(message.id)
            try:
                # Выбираем целевой форум-канал (приоритет) или канал APPROVED_CHANNEL_ID
                forum_channel = None
                forum_id = getattr(config, 'FORUM_CHANNEL_ID', 0) or 1436424801937002566
                if forum_id:
                    try:
                        forum_channel = self.bot.get_channel(forum_id) or await self.bot.fetch_channel(forum_id)
                    except Exception:
                        forum_channel = None

                target_channel = forum_channel or self.bot.get_channel(config.APPROVED_CHANNEL_ID)
                if not target_channel:
                    print("Канал для одобренных не найден (raw).")
                    return

                # Проверяем, не был ли уже опубликован пост с таким же заголовком в целевом канале
                try:
                    # Сначала пытаемся получить id новости из embed.url (если он там есть)
                    nid = None
                    try:
                        if getattr(emb, 'url', None):
                            nid = emb.url
                    except Exception:
                        nid = None
                    # fallback: если в embed не было url, попробуем footer (на случай старых сообщений)
                    if not nid:
                        try:
                            footer = emb.footer.text or ''
                            if 'id:' in footer:
                                nid = footer.split('id:')[-1].strip()
                        except Exception:
                            nid = None

                    if nid and storage.published(nid):
                        print(f"Новость id={nid} уже отмечена как опубликованная — пропускаю публикацию.")
                        return

                    # Если канал поддерживает history (не все типы, например ForumChannel в этой версии может не поддерживать), используем его как запасной способ поиска дубля
                    already = False
                    if hasattr(target_channel, 'history'):
                        async for m in target_channel.history(limit=200):
                            try:
                                if m.embeds and m.embeds[0].title == (emb.title or ''):
                                    already = True
                                    break
                            except Exception:
                                continue
                    else:
                        # если history недоступен, не пытаемся сканировать — полагаемся на storage.published
                        already = False

                    if already:
                        print(f"Пост с заголовком '{emb.title}' уже существует в канале {target_channel.id} — пропускаю публикацию.")
                        return
                except Exception as e:
                    print("Не удалось проверить историю/публикации целевого канала для дублей:", e)

                # Публикуем: если есть create_thread (ForumChannel), используем его; иначе fallback на send
                try:
                    name = emb.title or 'Новость'
                    if hasattr(target_channel, 'create_thread') and callable(getattr(target_channel, 'create_thread')):
                        try:
                            result = await target_channel.create_thread(name=name, embed=emb)
                            # result is (thread, message) namedtuple
                            try:
                                thread = getattr(result, 'thread', None) or (result[0] if isinstance(result, tuple) else None)
                                msg_created = getattr(result, 'message', None) or (result[1] if isinstance(result, tuple) and len(result) > 1 else None)
                                print(f"create_thread returned thread={getattr(thread,'id', None)} message={getattr(msg_created,'id', None)}")
                            except Exception:
                                pass
                        except TypeError:
                            try:
                                result = await target_channel.create_thread(name=name, content=None, embed=emb)
                                try:
                                    thread = getattr(result, 'thread', None) or (result[0] if isinstance(result, tuple) else None)
                                    msg_created = getattr(result, 'message', None) or (result[1] if isinstance(result, tuple) and len(result) > 1 else None)
                                    print(f"create_thread returned thread={getattr(thread,'id', None)} message={getattr(msg_created,'id', None)}")
                                except Exception:
                                    pass
                            except Exception as e:
                                print('Ошибка при create_thread с content fallback:', e)
                                # fallback на send
                                await target_channel.send(embed=emb)
                        except Exception as e:
                            print('Ошибка при вызове create_thread:', e)
                            # fallback на send
                            await target_channel.send(embed=emb)
                    else:
                        await target_channel.send(embed=emb)

                    print(f"Новость отправлена в канал одобренных (raw): id={message.id} target={target_channel.id}")

                    # Пометим исходное сообщение реакцией, чтобы видно было, что оно обработано
                    try:
                        await message.add_reaction("📌")
                    except Exception:
                        pass

                    # Сначала пытаемся получить id новости из embed.url
                    try:
                        nid = None
                        try:
                            if getattr(emb, 'url', None):
                                nid = emb.url
                        except Exception:
                            nid = None
                        # fallback: если в embed не было url, попробуем footer (на случай старых сообщений)
                        if not nid:
                            try:
                                footer = emb.footer.text or ''
                                if 'id:' in footer:
                                    nid = footer.split('id:')[-1].strip()
                            except Exception:
                                nid = None
                        if nid:
                            storage.mark_published(nid)
                    except Exception:
                        pass

                except Exception as e:
                    print("Ошибка при отправке одобренной новости (raw):", e)
            finally:
                # Снимаем флаг обработки в любом случае
                try:
                    self.processing.discard(message.id)
                except Exception:
                    pass

    @commands.command(name="checkperms")
    async def check_perms(self, ctx, channel_id: int = None):
        """Показывает права бота в указанном канале (по умолчанию текущий)."""
        channel = None
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except Exception as e:
                    await ctx.send(f"Не удалось получить канал: {e}")
                    return
        else:
            channel = ctx.channel

        bot_member = None
        if getattr(channel, 'guild', None):
            bot_member = channel.guild.get_member(self.bot.user.id) or channel.guild.me
            if not bot_member:
                try:
                    bot_member = await channel.guild.fetch_member(self.bot.user.id)
                except Exception:
                    bot_member = channel.guild.me
        perms = channel.permissions_for(bot_member) if bot_member else None
        overwrites = None
        try:
            overwrites = channel.overwrites_for(bot_member)
        except Exception:
            overwrites = None
        await ctx.send(f"Права бота в канале {channel.id}: {perms}\nТип канала: {getattr(channel,'type',None)}\nOverwrites: {overwrites}")
        print(f"checkperms: channel={channel.id} type={getattr(channel,'type',None)} bot_member={bot_member} perms={perms} overwrites={overwrites}")

    @commands.command(name="testreact")
    async def test_react(self, ctx):
        """Отправляет тестовое сообщение и пытается добавить реакции (отладка)."""
        try:
            test_msg = await ctx.send("Test reactions: добавляю ✅ и ❌")
            print(f"testreact: sent msg type={type(test_msg)} id={getattr(test_msg,'id',None)} author={getattr(test_msg,'author',None)} webhook_id={getattr(test_msg,'webhook_id',None)}")
        except Exception as e:
            await ctx.send(f"Не удалось отправить тестовое сообщение: {e}")
            print("testreact: send failed", e)
            return

        # fallback fetch
        if not hasattr(test_msg, 'add_reaction') or not callable(getattr(test_msg,'add_reaction',None)):
            try:
                fetched = await ctx.channel.fetch_message(getattr(test_msg,'id',None))
                if fetched:
                    test_msg = fetched
                    print(f"testreact: fetched message id={test_msg.id} type={type(test_msg)})")
            except Exception as e:
                print("testreact: fetch failed", e)

        for emoji in ("✅","❌"):
            try:
                await test_msg.add_reaction(emoji)
                print(f"testreact: added {emoji} to id={getattr(test_msg,'id',None)}")
            except Exception as e:
                await ctx.send(f"Ошибка при добавлении реакции {emoji}: {e}")
                print(f"testreact: failed add {emoji}", e)

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))