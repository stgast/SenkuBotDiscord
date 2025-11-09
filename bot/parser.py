import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict
from deep_translator import GoogleTranslator
import re

MAL_NEWS_URL = 'https://myanimelist.net/news'


def fix_image_url(url: str) -> str:
    """Исправляет уменьшенные картинки MAL до оригинального размера"""
    if not url:
        return url
    # Пример: /r/100x156/s/common/... -> /s/common/...
    if "/r/" in url and "/s/" in url:
        start = url.find("/r/")
        end = url.find("/s/")
        fixed = url[:start] + url[end:]
        return fixed
    return url


def translate_to_ru(text: str) -> str:
    """Переводит текст на русский с помощью Google Translator"""
    try:
        return GoogleTranslator(source="auto", target="ru").translate(text)
    except Exception as e:
        print("Translation failed:", e)
        return text


async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url, timeout=15) as resp:
        resp.raise_for_status()
        return await resp.text()


async def fetch_full_text(session: aiohttp.ClientSession, url: str) -> str:
    """Загружает полный текст новости с отдельной страницы"""
    try:
        html = await fetch_page(session, url)
        soup = BeautifulSoup(html, 'html.parser')

        # Популярные селекторы, где MAL хранит текст новости
        selectors = [
            '.content-news',
            '.news-container',
            '.news-container__content',
            '.text-readability',
            '.content',
            '.news-body',
            '.news-text',
            '.article-body',
            '#content',
            '.js-article-body',
            '.entry-content',
        ]

        content = None
        for sel in selectors:
            content = soup.select_one(sel)
            if content:
                break

        if not content:
            # последний шанс — контейнер с основным содержимым
            content = soup.find('article') or soup.find('div', {'class': 'news'})

        if not content:
            print("⚠️ No content found for:", url)
            return ""

        # Собираем текст из всех <p> внутри найденного блока
        paragraphs = [p.get_text(" ", strip=True) for p in content.find_all('p') if p.get_text(strip=True)]

        # Если есть параграфы, возвращаем только первый (короткое описание)
        if paragraphs:
            first_para = paragraphs[0].strip()
            # если есть дополнительные параграфы — добавим многоточие для обозначения обрезки
            if len(paragraphs) > 1:
                return first_para + "\n\n..."
            return first_para

        # Если нет параграфов — собираем все текстовые фрагменты и возвращаем первую логическую часть
        full_text = " ".join(list(content.stripped_strings))
        if '\n\n' in full_text:
            return full_text.split('\n\n', 1)[0].strip()
        # разбиваем по предложениям в крайнем случае
        sentences = re.split(r'(?<=[.!?])\s+', full_text)
        return sentences[0].strip() if sentences else full_text.strip()

    except Exception as e:
        print("Error fetching full text:", e)
        return ""


async def parse_latest_news(limit: int = 5) -> List[Dict]:
    """Парсит последние новости с MyAnimeList"""
    results = []
    print(f"🔍 Fetching {limit} latest news from MyAnimeList...")
    async with aiohttp.ClientSession() as session:
        html = await fetch_page(session, MAL_NEWS_URL)
        soup = BeautifulSoup(html, 'html.parser')
        news_units = soup.select('.news-unit')

        for unit in news_units[:limit]:
            a = unit.select_one('p.title a')
            if not a:
                continue

            title = a.text.strip()
            link = a['href']

            # 🎯 Извлекаем оригинальное название аниме в одинарных кавычках
            match = re.search(r"'([^']+)'", title)
            anime_name = match.group(1) if match else None

            # Если нашли название в кавычках — используем только его, иначе переводим заголовок
            if anime_name:
                title = f"『{anime_name}』"
            else:
                title = translate_to_ru(title)

            # безопасно получаем изображение
            img = None
            img_tag = unit.select_one('img')
            if img_tag:
                img = img_tag.get('data-src') or img_tag.get('src')
                img = fix_image_url(img)

            # текст новости — пробуем вытянуть полный текст со страницы
            excerpt_tag = unit.select_one('.text')
            excerpt = excerpt_tag.text.strip() if excerpt_tag else ''
            full_text = await fetch_full_text(session, link)
            excerpt = full_text or excerpt  # если получилось достать — используем полный текст

            results.append({
                'id': link,
                'title': title,
                'link': link,
                'image': img,
                'excerpt': excerpt,
            })

    # переводим на русский
    translated_results = []
    for item in results:
        if isinstance(item, dict):
            if item.get("title"):
                item["title"] = item["title"]
            if item.get("excerpt"):
                item["excerpt"] = translate_to_ru(item["excerpt"])
            translated_results.append(item)

    print(f"✅ Parsed {len(results)} news items successfully.")
    return translated_results