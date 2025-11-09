import json
from pathlib import Path
from typing import Set, Dict

DATA_FILE = Path('data/processed.json')

class Storage:
    def __init__(self, path: Path = DATA_FILE):
        self.path = path
        self._seen: Set[str] = set()
        self._published: Set[str] = set()
        self._load()

    def _load(self):
        if not self.path.exists():
            self._seen = set()
            self._published = set()
            return
        try:
            with self.path.open('r', encoding='utf-8') as f:
                data = json.load(f)
            # Поддерживаем старый формат: список id
            if isinstance(data, list):
                self._seen = set(data)
                self._published = set()
            elif isinstance(data, dict):
                self._seen = set(data.get('seen', []))
                self._published = set(data.get('published', []))
            else:
                self._seen = set()
                self._published = set()
        except Exception:
            self._seen = set()
            self._published = set()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, list] = {
            'seen': list(self._seen),
            'published': list(self._published)
        }
        with self.path.open('w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def seen(self, item_id: str) -> bool:
        """Проверяет, есть ли новость уже в базе (отправлена в мод-канал)"""
        return item_id in self._seen

    def add(self, item_id: str):
        """Добавляет новость в базу seen"""
        self._seen.add(item_id)
        self.save()

    def published(self, item_id: str) -> bool:
        """Проверяет, опубликована ли новость (в форуме/approved)."""
        return item_id in self._published

    def mark_published(self, item_id: str):
        """Отмечает новость как опубликованную."""
        self._published.add(item_id)
        self.save()


# глобальный экземпляр
storage = Storage()
